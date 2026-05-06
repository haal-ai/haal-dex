"""RetrievalRouter: routes queries to configured retrieval backends concurrently.

Queries all permitted backends in parallel using ``asyncio.gather``, merges
and deduplicates results by exact ``document_fragment`` content, sorts by
descending score, and injects the final results into the agent system prompt
as structured context.

Access control is enforced via an optional ACL list.  When the ACL is
``None``, all configured backends are queried.  When provided, only
backends whose name matches an ACL entry's ``index_name`` are permitted.

If a Bedrock_Embedding backend fails and a FAISS_Embedding backend is
configured for the same index, the router retries with the FAISS backend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.models.personality import RetrievalACLEntry

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result from any backend."""

    document_fragment: str
    score: float
    source: str
    backend_type: str


class RetrievalRouter:
    """Routes queries to configured retrieval backends concurrently.

    Args:
        backends: List of ``(backend_name, backend_instance)`` tuples.
            Each backend instance must expose an async
            ``query(query_text, top_k)`` method returning objects with
            ``document_fragment``, ``score``, and ``source`` attributes.
        acl: Optional access control list.  When provided, only backends
            whose name matches an ACL entry's ``index_name`` are queried.
            When ``None``, all configured backends are queried.
    """

    def __init__(
        self,
        backends: list[tuple[str, Any]],
        acl: list[RetrievalACLEntry] | None = None,
    ) -> None:
        self._backends: list[tuple[str, Any]] = backends
        self._acl = acl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self, query_text: str, top_k: int = 5
    ) -> list[RetrievalResult]:
        """Query all permitted backends concurrently, merge and deduplicate.

        Args:
            query_text: The search query string.
            top_k: Maximum number of results to return after merging.

        Returns:
            List of :class:`RetrievalResult` ordered by descending score,
            limited to *top_k* entries.  Returns an empty list when no
            backends are configured or all backends fail.
        """
        if not self._backends:
            logger.debug("No retrieval backends configured; skipping retrieval.")
            return []

        permitted = self._filter_permitted_backends()
        if not permitted:
            logger.warning("No permitted retrieval backends after ACL filtering. Backends: %s, ACL: %s",
                          [n for n, _ in self._backends], self._acl)
            return []

        logger.warning("DEBUG: Querying %d permitted backends: %s", len(permitted), [n for n, _ in permitted])

        # Query all permitted backends concurrently.
        tasks = [
            self._query_backend(name, backend, query_text, top_k)
            for name, backend in permitted
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results and track failures for fallback.
        all_results: list[RetrievalResult] = []
        failed_bedrock: list[tuple[str, Any]] = []

        for (name, backend), result in zip(permitted, raw_results):
            if isinstance(result, Exception):
                logger.warning(
                    "Retrieval backend '%s' failed with exception: %s", name, result
                )
                if self._is_bedrock_backend(backend):
                    failed_bedrock.append((name, backend))
            else:
                logger.warning("DEBUG: Backend '%s' returned %d results", name, len(result))
                all_results.extend(result)

        # Bedrock fallback: retry failed Bedrock backends with FAISS if available.
        if failed_bedrock:
            fallback_results = await self._bedrock_fallback(
                failed_bedrock, query_text, top_k
            )
            all_results.extend(fallback_results)

        if not all_results:
            logger.warning(
                "All retrieval backends failed or returned no results."
            )
            return []

        # Deduplicate by exact document_fragment content (keep highest score).
        deduped = self._deduplicate(all_results)

        # Sort by descending score.
        deduped.sort(key=lambda r: r.score, reverse=True)

        return deduped[:top_k]

    def inject_context(
        self, results: list[RetrievalResult], system_prompt: str
    ) -> str:
        """Append retrieval results to the system prompt as structured context.

        Args:
            results: Retrieval results to inject.
            system_prompt: The original system prompt.

        Returns:
            The system prompt with retrieval context appended.  When
            *results* is empty the original prompt is returned unchanged.
        """
        if not results:
            return system_prompt

        sections: list[str] = []
        for i, result in enumerate(results, start=1):
            sections.append(
                f"[Source {i}: {result.source} ({result.backend_type}), "
                f"score={result.score:.4f}]\n{result.document_fragment}"
            )

        context_block = "\n\n".join(sections)
        return (
            f"{system_prompt}\n\n"
            f"--- Retrieved Context ---\n{context_block}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_permitted_backends(
        self,
    ) -> list[tuple[str, Any]]:
        """Return backends permitted by the ACL.

        When the ACL is ``None``, all configured backends are permitted.
        Otherwise only backends whose name matches an ACL entry's
        ``index_name`` are included.
        """
        if self._acl is None:
            return list(self._backends)

        allowed_names = {entry.index_name for entry in self._acl}
        permitted: list[tuple[str, Any]] = []
        for name, backend in self._backends:
            if name in allowed_names:
                permitted.append((name, backend))
            else:
                logger.debug(
                    "Backend '%s' rejected by ACL (not in allowed indexes).",
                    name,
                )
        return permitted

    async def _query_backend(
        self,
        name: str,
        backend: Any,
        query_text: str,
        top_k: int,
    ) -> list[RetrievalResult]:
        """Query a single backend and convert results to RetrievalResult."""
        logger.warning("DEBUG _query_backend: calling %s.query(%r, %d)", name, query_text[:50], top_k)
        logger.warning("DEBUG _query_backend: backend db_path=%s", getattr(backend, "db_path", "N/A"))
        raw = await backend.query(query_text, top_k)
        logger.warning("DEBUG _query_backend: %s returned %d raw items", name, len(raw))
        for i, item in enumerate(raw[:3]):
            logger.warning("DEBUG _query_backend: raw[%d] frag=%s score=%s", i, getattr(item, "document_fragment", "?")[:60], getattr(item, "score", "?"))
        results: list[RetrievalResult] = []
        backend_type = self._detect_backend_type(backend)
        for item in raw:
            # Backend results expose document_fragment, score, source attrs.
            source = getattr(item, "source", None) or getattr(
                item, "source_document", ""
            )
            results.append(
                RetrievalResult(
                    document_fragment=item.document_fragment,
                    score=item.score,
                    source=source,
                    backend_type=backend_type,
                )
            )
        return results

    @staticmethod
    def _deduplicate(
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Deduplicate results by exact ``document_fragment`` content.

        When duplicates exist, the entry with the highest score is kept.
        """
        best: dict[str, RetrievalResult] = {}
        for result in results:
            existing = best.get(result.document_fragment)
            if existing is None or result.score > existing.score:
                best[result.document_fragment] = result
        return list(best.values())

    @staticmethod
    def _is_bedrock_backend(backend: Any) -> bool:
        """Return ``True`` if *backend* is a BedrockEmbeddingBackend."""
        return type(backend).__name__ == "BedrockEmbeddingBackend"

    @staticmethod
    def _is_faiss_backend(backend: Any) -> bool:
        """Return ``True`` if *backend* is a FAISS-based embedding backend."""
        name = type(backend).__name__
        return name in ("FAISSIndexManager", "FAISSEmbeddingBackend")

    @staticmethod
    def _detect_backend_type(backend: Any) -> str:
        """Infer a human-readable backend type string from the instance."""
        name = type(backend).__name__
        type_map = {
            "SQLiteBM25Backend": "sqlite_bm25",
            "BedrockEmbeddingBackend": "bedrock_embedding",
            "FAISSIndexManager": "faiss_embedding",
            "FAISSEmbeddingBackend": "faiss_embedding",
        }
        return type_map.get(name, name)

    def _find_faiss_fallback(
        self, bedrock_name: str
    ) -> tuple[str, Any] | None:
        """Find a FAISS backend configured for the same index as *bedrock_name*.

        The match is by backend name equality — a FAISS backend is
        considered a fallback for a Bedrock backend when both share the
        same name.
        """
        for name, backend in self._backends:
            if name == bedrock_name and self._is_faiss_backend(backend):
                return name, backend
        return None

    async def _bedrock_fallback(
        self,
        failed: list[tuple[str, Any]],
        query_text: str,
        top_k: int,
    ) -> list[RetrievalResult]:
        """Retry failed Bedrock backends using FAISS fallbacks when available."""
        results: list[RetrievalResult] = []
        for bedrock_name, _bedrock_backend in failed:
            fallback = self._find_faiss_fallback(bedrock_name)
            if fallback is None:
                logger.debug(
                    "No FAISS fallback available for Bedrock backend '%s'.",
                    bedrock_name,
                )
                continue

            faiss_name, faiss_backend = fallback
            logger.info(
                "Falling back to FAISS backend '%s' for failed Bedrock backend '%s'.",
                faiss_name,
                bedrock_name,
            )
            try:
                fallback_results = await self._query_backend(
                    faiss_name, faiss_backend, query_text, top_k
                )
                results.extend(fallback_results)
            except Exception as exc:
                logger.warning(
                    "FAISS fallback '%s' also failed: %s", faiss_name, exc
                )
        return results
