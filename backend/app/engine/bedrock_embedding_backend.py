"""BedrockEmbeddingBackend: generates embeddings via Bedrock and searches FAISS indexes.

Uses Amazon Bedrock embedding models (Titan Text Embeddings V2 or Nova
Multimodal Embeddings) to generate query embeddings, then searches a FAISS
index for nearest neighbours.  Results are returned as dataclass objects
ranked by descending similarity score.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

# Optional heavy dependencies — fall back to ``None`` when unavailable.
try:
    import boto3  # type: ignore[import-untyped]
    from botocore.exceptions import (  # type: ignore[import-untyped]
        BotoCoreError,
        ClientError,
    )
except ImportError:
    boto3 = None  # type: ignore[assignment]
    BotoCoreError = None  # type: ignore[assignment,misc]
    ClientError = None  # type: ignore[assignment,misc]

try:
    import faiss  # type: ignore[import-untyped]
except ImportError:
    faiss = None  # type: ignore[assignment]

try:
    import numpy as np  # type: ignore[import-untyped]
except ImportError:
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Log module-level warnings for missing optional dependencies.
if boto3 is None:
    logger.warning(
        "boto3 is not installed; BedrockEmbeddingBackend will be disabled."
    )
if faiss is None:
    logger.warning(
        "faiss is not installed; BedrockEmbeddingBackend will be disabled."
    )
if np is None:
    logger.warning(
        "numpy is not installed; BedrockEmbeddingBackend will be disabled."
    )

# Supported Bedrock embedding model IDs.
SUPPORTED_MODEL_IDS = {
    "amazon.titan-embed-text-v2:0",
    "amazon.nova-embed-multimodal-v1:0",
}


@dataclass
class BedrockEmbeddingResult:
    """A single embedding-based similarity search result."""

    document_fragment: str
    score: float
    source: str


class BedrockEmbeddingBackend:
    """Generates embeddings via Amazon Bedrock and searches FAISS indexes.

    Args:
        model_id: Bedrock embedding model identifier, e.g.
            ``"amazon.titan-embed-text-v2:0"`` or
            ``"amazon.nova-embed-multimodal-v1:0"``.
        index_path: Path to the FAISS index file on disk.
        region: AWS region for the Bedrock client.  When ``None`` the
            default boto3 region resolution is used.
        top_k: Default number of results to return from a query.
    """

    def __init__(
        self,
        model_id: str,
        index_path: str,
        region: str | None = None,
        top_k: int = 5,
    ) -> None:
        self.model_id = model_id
        self.index_path = index_path
        self.region = region
        self.default_top_k = top_k

        self._client: Any | None = None
        self._index: Any | None = None
        self._documents: list[str] = []
        self._sources: list[str] = []

        # Eagerly load the FAISS index and metadata if possible.
        self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self, query_text: str, top_k: int = 5
    ) -> list[BedrockEmbeddingResult]:
        """Generate an embedding via Bedrock and search the FAISS index.

        Args:
            query_text: The text to embed and search for.
            top_k: Maximum number of results to return.

        Returns:
            List of :class:`BedrockEmbeddingResult` ordered by descending
            similarity score, limited to *top_k* entries.  On failure a
            list containing a single error-result is returned.
        """
        if not query_text or not query_text.strip():
            return []

        if self._index is None:
            msg = (
                f"FAISS index not loaded from '{self.index_path}'. "
                "The index is unavailable."
            )
            logger.warning(msg)
            return [
                BedrockEmbeddingResult(
                    document_fragment=msg, score=0.0, source=self.index_path
                )
            ]

        # Generate the query embedding via Bedrock.
        embedding = await self._generate_embedding(query_text)
        if embedding is None:
            # _generate_embedding already logged the error and returns None
            # on failure; the error result is returned from there.
            return self._last_error_results

        # Search the FAISS index in a thread to avoid blocking the event loop.
        results = await asyncio.to_thread(
            self._search_index, embedding, top_k
        )

        # Sort by descending similarity score.
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def is_available(self) -> bool:
        """Check if Bedrock credentials are usable and the FAISS index exists.

        Returns:
            ``True`` when boto3 is installed, a Bedrock client can be
            created, and the FAISS index file exists on disk.
        """
        if boto3 is None:
            logger.warning(
                "boto3 is not installed; BedrockEmbeddingBackend disabled."
            )
            return False

        if faiss is None:
            logger.warning(
                "faiss is not installed; BedrockEmbeddingBackend disabled."
            )
            return False

        if np is None:
            logger.warning(
                "numpy is not installed; BedrockEmbeddingBackend disabled."
            )
            return False

        if not os.path.exists(self.index_path):
            logger.warning(
                "FAISS index file not found at '%s'; "
                "BedrockEmbeddingBackend disabled.",
                self.index_path,
            )
            return False

        # Verify that we can create a Bedrock client (credentials check).
        try:
            client = self._get_client()
            if client is None:
                logger.warning(
                    "Could not create Bedrock client; "
                    "BedrockEmbeddingBackend disabled (credentials not configured)."
                )
                return False
            return True
        except Exception as exc:
            logger.warning(
                "Bedrock credentials not configured or invalid: %s; "
                "BedrockEmbeddingBackend disabled.",
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Return a cached ``bedrock-runtime`` boto3 client."""
        if self._client is not None:
            return self._client

        if boto3 is None:
            return None

        kwargs: dict[str, Any] = {}
        if self.region:
            kwargs["region_name"] = self.region

        session = boto3.Session(**kwargs)
        self._client = session.client("bedrock-runtime", **kwargs)
        return self._client

    def _load_index(self) -> None:
        """Attempt to load the FAISS index and its metadata sidecar."""
        if faiss is None:
            logger.warning("faiss is not installed; BedrockEmbeddingBackend disabled.")
            return

        if not os.path.exists(self.index_path):
            logger.warning(
                "FAISS index file not found at '%s'; "
                "BedrockEmbeddingBackend will be unavailable until the file exists.",
                self.index_path,
            )
            return

        try:
            self._index = faiss.read_index(self.index_path)
        except Exception as exc:
            logger.error(
                "Could not read FAISS index at '%s': %s", self.index_path, exc
            )
            return

        self._documents, self._sources = self._load_metadata()
        logger.info(
            "Loaded FAISS index from '%s' with %d vectors",
            self.index_path,
            self._index.ntotal,
        )

    def _load_metadata(self) -> tuple[list[str], list[str]]:
        """Load document fragments and source names from a JSON sidecar.

        Expected sidecar path: ``<index_path>.meta.json`` with structure:
        ``{"documents": [...], "sources": [...]}``
        """
        meta_path = self.index_path + ".meta.json"
        if not os.path.exists(meta_path):
            return [], []

        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get("documents", []), data.get("sources", [])
        except Exception as exc:
            logger.warning(
                "Could not load metadata from '%s': %s", meta_path, exc
            )
            return [], []

    async def _generate_embedding(
        self, text: str
    ) -> "np.ndarray | None":
        """Call Bedrock ``invoke_model`` to generate an embedding vector.

        Returns the embedding as a numpy array, or ``None`` on failure
        (with ``self._last_error_results`` populated).
        """
        self._last_error_results: list[BedrockEmbeddingResult] = []

        client = self._get_client()
        if client is None:
            msg = "boto3 is not installed; cannot generate Bedrock embeddings."
            logger.warning(msg)
            self._last_error_results = [
                BedrockEmbeddingResult(
                    document_fragment=msg, score=0.0, source=self.index_path
                )
            ]
            return None

        request_body = self._build_request_body(text)

        try:
            response = await asyncio.to_thread(
                client.invoke_model,
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body),
            )
        except Exception as exc:
            error_detail = self._extract_error_detail(exc)
            msg = (
                f"Bedrock embedding API call failed for model "
                f"'{self.model_id}': {error_detail}"
            )
            logger.error(msg)
            self._last_error_results = [
                BedrockEmbeddingResult(
                    document_fragment=msg, score=0.0, source=self.index_path
                )
            ]
            return None

        try:
            response_body = json.loads(response["body"].read())
            embedding = self._extract_embedding(response_body)
            return np.array([embedding], dtype=np.float32)
        except Exception as exc:
            msg = (
                f"Failed to parse Bedrock embedding response for model "
                f"'{self.model_id}': {exc}"
            )
            logger.error(msg)
            self._last_error_results = [
                BedrockEmbeddingResult(
                    document_fragment=msg, score=0.0, source=self.index_path
                )
            ]
            return None

    def _build_request_body(self, text: str) -> dict[str, Any]:
        """Build the JSON request body for the configured embedding model."""
        if self.model_id.startswith("amazon.titan-embed-text"):
            return {"inputText": text}
        elif self.model_id.startswith("amazon.nova-embed-multimodal"):
            return {"inputText": text}
        else:
            # Generic fallback — Titan-style payload.
            return {"inputText": text}

    def _extract_embedding(self, response_body: dict[str, Any]) -> list[float]:
        """Extract the embedding vector from the Bedrock response body."""
        if self.model_id.startswith("amazon.titan-embed-text"):
            return response_body["embedding"]
        elif self.model_id.startswith("amazon.nova-embed-multimodal"):
            return response_body["embedding"]
        else:
            # Generic fallback.
            return response_body.get("embedding", response_body.get("embeddings", []))

    def _search_index(
        self, embedding: Any, top_k: int
    ) -> list[BedrockEmbeddingResult]:
        """Synchronous FAISS index search (runs in a thread)."""
        n_vectors = self._index.ntotal
        effective_k = min(top_k, n_vectors) if n_vectors > 0 else 0
        if effective_k == 0:
            return []

        distances, indices = self._index.search(embedding, effective_k)

        results: list[BedrockEmbeddingResult] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            fragment = (
                self._documents[idx]
                if idx < len(self._documents)
                else f"[fragment {idx}]"
            )
            source = (
                self._sources[idx]
                if idx < len(self._sources)
                else self.index_path
            )
            results.append(
                BedrockEmbeddingResult(
                    document_fragment=fragment,
                    score=float(dist),
                    source=source,
                )
            )
        return results

    @staticmethod
    def _extract_error_detail(exc: Exception) -> str:
        """Extract a human-readable error detail from a Bedrock exception."""
        # Handle botocore ClientError with structured response.
        if ClientError is not None and isinstance(exc, ClientError):
            error_response = getattr(exc, "response", {})
            error_info = error_response.get("Error", {})
            code = error_info.get("Code", "Unknown")
            message = error_info.get("Message", str(exc))
            return f"{code}: {message}"

        return str(exc)
