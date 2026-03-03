"""FAISSIndexManager: manages up to 4 concurrent FAISS vector indexes.

Loads FAISS indexes from disk, embeds queries via sentence-transformers,
and returns document fragments ranked by descending similarity score.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.models.faiss_models import IndexConfig, SimilarityResult

# Try importing optional heavy dependencies; fall back to None if unavailable.
try:
    import faiss  # type: ignore[import-untyped]
except ImportError:
    faiss = None  # type: ignore[assignment]

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

MAX_INDEXES = 4


@dataclass
class _LoadedIndex:
    """Internal representation of a loaded FAISS index with its metadata."""

    config: IndexConfig
    index: object  # faiss.Index
    embedding_model: object  # SentenceTransformer instance
    documents: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class FAISSIndexManager:
    """Manages up to 4 concurrent FAISS vector indexes per pipeline execution.

    Provides loading, querying (ranked by similarity score), and status
    inspection for FAISS indexes referenced in a pipeline configuration.
    """

    def __init__(self) -> None:
        self._indexes: dict[int, _LoadedIndex] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_indexes(self, index_configs: list[IndexConfig]) -> None:
        """Load FAISS indexes concurrently (up to 4).

        Args:
            index_configs: List of index configurations to load.

        Raises:
            ValueError: If more than 4 indexes are requested or required
                libraries are not installed.
        """
        if len(index_configs) > MAX_INDEXES:
            raise ValueError(
                f"Cannot load more than {MAX_INDEXES} concurrent FAISS indexes. "
                f"Requested: {len(index_configs)}."
            )

        if faiss is None:
            raise ValueError(
                "faiss-cpu is not installed. Install it to use FAISS indexes."
            )
        if SentenceTransformer is None:
            raise ValueError(
                "sentence-transformers is not installed. Install it to use FAISS indexes."
            )

        tasks = [self._load_single(cfg) for cfg in index_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cfg, result in zip(index_configs, results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to load FAISS index %d ('%s'): %s",
                    cfg.index_id,
                    cfg.name,
                    result,
                )
                raise ValueError(
                    f"FAISS index {cfg.index_id} ('{cfg.name}') is unavailable: {result}"
                )

    async def query(
        self,
        index_id: int,
        query_text: str,
        top_k: int = 5,
    ) -> list[SimilarityResult]:
        """Query a loaded FAISS index and return fragments ranked by descending similarity score.

        Args:
            index_id: The ID of the index to query (0-3).
            query_text: The text to search for.
            top_k: Maximum number of results to return.

        Returns:
            List of SimilarityResult ordered by descending similarity score.

        Raises:
            ValueError: If the requested index is not loaded.
        """
        if index_id not in self._indexes:
            available = list(self._indexes.keys())
            raise ValueError(
                f"FAISS index {index_id} is not loaded. "
                f"Loaded indexes: {available}"
            )

        loaded = self._indexes[index_id]
        results = await asyncio.to_thread(
            self._query_sync, loaded, query_text, top_k
        )
        # Sort by descending similarity score
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def get_loaded_indexes(self) -> list[int]:
        """Return the IDs of all currently loaded indexes."""
        return sorted(self._indexes.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_single(self, config: IndexConfig) -> None:
        """Load a single FAISS index from disk in a thread."""
        await asyncio.to_thread(self._load_single_sync, config)

    def _load_single_sync(self, config: IndexConfig) -> None:
        """Synchronous index loading (runs in a thread)."""
        try:
            index = faiss.read_index(config.index_path)
        except Exception as exc:
            raise ValueError(
                f"Could not read FAISS index file at '{config.index_path}': {exc}"
            ) from exc

        try:
            model = SentenceTransformer(config.embedding_model)
        except Exception as exc:
            raise ValueError(
                f"Could not load embedding model '{config.embedding_model}': {exc}"
            ) from exc

        # Load associated document fragments if a metadata sidecar exists.
        documents, sources = self._load_metadata(config)

        self._indexes[config.index_id] = _LoadedIndex(
            config=config,
            index=index,
            embedding_model=model,
            documents=documents,
            sources=sources,
        )
        logger.info(
            "Loaded FAISS index %d ('%s') with %d vectors",
            config.index_id,
            config.name,
            index.ntotal,
        )

    def _query_sync(
        self,
        loaded: _LoadedIndex,
        query_text: str,
        top_k: int,
    ) -> list[SimilarityResult]:
        """Synchronous query against a loaded FAISS index."""
        import numpy as np  # local import — only needed at query time

        embedding = loaded.embedding_model.encode([query_text])
        embedding = np.array(embedding, dtype=np.float32)

        # Clamp top_k to the number of vectors in the index
        n_vectors = loaded.index.ntotal
        effective_k = min(top_k, n_vectors) if n_vectors > 0 else 0
        if effective_k == 0:
            return []

        distances, indices = loaded.index.search(embedding, effective_k)

        results: list[SimilarityResult] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            fragment = (
                loaded.documents[idx]
                if idx < len(loaded.documents)
                else f"[fragment {idx}]"
            )
            source = (
                loaded.sources[idx]
                if idx < len(loaded.sources)
                else loaded.config.name
            )
            results.append(
                SimilarityResult(
                    document_fragment=fragment,
                    score=float(dist),
                    source_document=source,
                    index_id=loaded.config.index_id,
                )
            )
        return results

    @staticmethod
    def _load_metadata(config: IndexConfig) -> tuple[list[str], list[str]]:
        """Attempt to load document fragments and source names from a JSON sidecar.

        Expected sidecar path: ``<index_path>.meta.json`` with structure:
        ``{"documents": [...], "sources": [...]}``

        Returns empty lists if the sidecar does not exist.
        """
        import json
        import os

        meta_path = config.index_path + ".meta.json"
        if not os.path.exists(meta_path):
            return [], []

        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get("documents", []), data.get("sources", [])
        except Exception as exc:
            logger.warning(
                "Could not load metadata for index %d from '%s': %s",
                config.index_id,
                meta_path,
                exc,
            )
            return [], []
