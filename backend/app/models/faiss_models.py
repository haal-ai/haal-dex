from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndexConfig:
    index_id: int  # 0-3
    name: str
    description: str
    index_path: str  # path to FAISS index file
    embedding_model: str  # model used for vectorization


@dataclass
class SimilarityResult:
    document_fragment: str
    score: float
    source_document: str
    index_id: int
