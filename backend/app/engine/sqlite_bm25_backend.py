"""SQLiteBM25Backend: queries SQLite FTS5 tables with BM25 ranking.

Executes full-text search against a SQLite database using FTS5 virtual
tables and returns document fragments ranked by descending BM25 score.
Supports both BM25 Okapi (default ``bm25()``) and BM25F (column-weighted
``bm25()``) ranking algorithms.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FTS5 availability check — some SQLite builds omit FTS5 support.
# ---------------------------------------------------------------------------
_FTS5_AVAILABLE = False
try:
    _test_conn = sqlite3.connect(":memory:")
    _test_conn.execute(
        "CREATE VIRTUAL TABLE _fts5_check USING fts5(content)"
    )
    _test_conn.close()
    _FTS5_AVAILABLE = True
except Exception:
    logger.warning(
        "SQLite FTS5 extension is not available in this build; "
        "SQLiteBM25Backend will be disabled."
    )


@dataclass
class BM25Result:
    """A single BM25-ranked search result."""

    document_fragment: str
    score: float
    source: str


class SQLiteBM25Backend:
    """Queries SQLite FTS5 tables with BM25 ranking.

    Args:
        db_path: Path to the SQLite database file.
        fts_table: Name of the FTS5 virtual table to query.
        ranking_algorithm: ``"bm25_okapi"`` for default ``bm25()`` or
            ``"bm25f"`` for column-weighted ``bm25()`` with per-column
            boost parameters.
        column_weights: Optional per-column boost weights for BM25F.
            Each weight corresponds to a column in the FTS5 table in
            declaration order.  Ignored when *ranking_algorithm* is
            ``"bm25_okapi"``.
    """

    def __init__(
        self,
        db_path: str,
        fts_table: str,
        ranking_algorithm: str = "bm25_okapi",
        column_weights: list[float] | None = None,
    ) -> None:
        self.db_path = db_path
        self.fts_table = fts_table
        self.ranking_algorithm = ranking_algorithm
        self.column_weights = column_weights

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self, query_text: str, top_k: int = 5
    ) -> list[BM25Result]:
        """Execute FTS5 search with BM25 ranking, return top-k results.

        Args:
            query_text: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of :class:`BM25Result` ordered by descending BM25 score,
            limited to *top_k* entries.  Returns a list containing a single
            error-result when the database or FTS5 table is unavailable.
        """
        if not query_text or not query_text.strip():
            logger.warning("DEBUG query: empty query_text, returning []")
            return []

        logger.warning("DEBUG query: FTS5=%s, db_path=%s, exists=%s", _FTS5_AVAILABLE, self.db_path, os.path.exists(self.db_path))

        if not _FTS5_AVAILABLE:
            msg = (
                "SQLite FTS5 extension is not available in this build. "
                "SQLiteBM25Backend is disabled."
            )
            logger.warning(msg)
            return [BM25Result(document_fragment=msg, score=0.0, source=self.db_path)]

        if not os.path.exists(self.db_path):
            msg = (
                f"SQLite database not found at '{self.db_path}'. "
                "The database is unavailable."
            )
            logger.warning(msg)
            return [BM25Result(document_fragment=msg, score=0.0, source=self.db_path)]

        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error as exc:
            msg = f"Failed to connect to SQLite database at '{self.db_path}': {exc}"
            logger.error(msg)
            return [BM25Result(document_fragment=msg, score=0.0, source=self.db_path)]

        try:
            if not self._fts_table_exists(conn):
                msg = (
                    f"FTS5 table '{self.fts_table}' not found in database "
                    f"'{self.db_path}'. The index is not initialized."
                )
                logger.warning(msg)
                return [
                    BM25Result(
                        document_fragment=msg, score=0.0, source=self.db_path
                    )
                ]

            results = self._execute_query(conn, query_text, top_k)
            logger.warning("DEBUG: _execute_query returned %d results", len(results))
            return results
        except sqlite3.Error as exc:
            msg = f"FTS5 query failed on '{self.fts_table}': {exc}"
            logger.error(msg)
            return [BM25Result(document_fragment=msg, score=0.0, source=self.db_path)]
        except Exception as exc:
            msg = f"Unexpected error querying '{self.fts_table}': {exc}"
            logger.error(msg, exc_info=True)
            return [BM25Result(document_fragment=msg, score=0.0, source=self.db_path)]
        finally:
            conn.close()

    def is_available(self) -> bool:
        """Check if the database file exists and the FTS5 table is queryable.

        Returns:
            ``True`` when FTS5 is supported by the SQLite build, the
            database file exists, and the FTS5 table is present.
            ``False`` otherwise.
        """
        if not _FTS5_AVAILABLE:
            return False

        if not os.path.exists(self.db_path):
            return False

        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error:
            return False

        try:
            return self._fts_table_exists(conn)
        except sqlite3.Error:
            return False
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fts_table_exists(self, conn: sqlite3.Connection) -> bool:
        """Return ``True`` if *self.fts_table* exists as an FTS5 virtual table."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (self.fts_table,),
        )
        return cursor.fetchone() is not None

    def _execute_query(
        self,
        conn: sqlite3.Connection,
        query_text: str,
        top_k: int,
    ) -> list[BM25Result]:
        """Run the FTS5 MATCH query and return ranked results."""
        # Sanitize the query for FTS5 — wrap each token in double quotes
        # to avoid syntax errors from special characters.
        sanitized = self._sanitize_query(query_text)
        if not sanitized:
            return []

        bm25_expr = self._build_bm25_expression()

        # FTS5 bm25() returns *negative* scores (lower = better match).
        # We negate them so that higher values represent better matches,
        # then sort descending.
        sql = (
            f"SELECT *, -{bm25_expr} AS rank "
            f"FROM [{self.fts_table}] "
            f"WHERE [{self.fts_table}] MATCH ? "
            f"ORDER BY rank DESC "
            f"LIMIT ?"
        )

        logger.warning("DEBUG SQL: %s | params=(%r, %d) | bm25_expr=%s", sql, sanitized, top_k, bm25_expr)

        cursor = conn.execute(sql, (sanitized, top_k))
        columns = [desc[0] for desc in cursor.description]

        results: list[BM25Result] = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            score = row_dict.get("rank", 0.0)
            # Build the document fragment from all non-rank columns
            fragment = self._build_fragment(row_dict, columns)
            results.append(
                BM25Result(
                    document_fragment=fragment,
                    score=float(score),
                    source=self.db_path,
                )
            )

        return results

    def _build_bm25_expression(self) -> str:
        """Build the ``bm25()`` SQL expression based on the ranking algorithm."""
        if self.ranking_algorithm == "bm25f" and self.column_weights:
            weights = ", ".join(str(w) for w in self.column_weights)
            return f"bm25([{self.fts_table}], {weights})"
        # Default: BM25 Okapi — use bm25() with no extra arguments.
        return f"bm25([{self.fts_table}])"

    @staticmethod
    def _sanitize_query(query_text: str) -> str:
        """Sanitize a user query for safe use in FTS5 MATCH expressions.

        Wraps each whitespace-delimited token in double quotes so that
        special FTS5 operators (``AND``, ``OR``, ``NOT``, ``NEAR``, etc.)
        and punctuation are treated as literal search terms.  Tokens are
        joined with ``OR`` so that documents matching *any* query term
        are returned (ranked by BM25 relevance).
        """
        tokens = query_text.strip().split()
        if not tokens:
            return ""
        # Escape any embedded double quotes within tokens
        escaped = [t.replace('"', '""') for t in tokens]
        return " OR ".join(f'"{t}"' for t in escaped)

    @staticmethod
    def _build_fragment(
        row_dict: dict[str, object], columns: list[str]
    ) -> str:
        """Combine non-internal columns into a single document fragment string."""
        skip = {"rank"}
        parts: list[str] = []
        for col in columns:
            if col in skip:
                continue
            value = row_dict.get(col)
            if value is not None:
                parts.append(str(value))
        return " | ".join(parts) if parts else ""
