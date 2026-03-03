# Feature: intent, Property 9: FAISS index count constraint
# Feature: intent, Property 10: FAISS similarity results are ranked by score
"""Property 9 & 10: FAISS index count constraint and similarity ranking.

**Validates: Requirements 5.1, 5.3**
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from app.models.faiss_models import IndexConfig


def _cfg(index_id):
    return IndexConfig(
        index_id=index_id,
        name=f"index-{index_id}",
        description=f"Test index {index_id}",
        index_path=f"/fake/path/index_{index_id}.faiss",
        embedding_model="all-MiniLM-L6-v2",
    )


def _mocks():
    mf = MagicMock()
    mi = MagicMock()
    mi.ntotal = 10
    mf.read_index.return_value = mi
    sc = MagicMock()
    si = MagicMock()
    sc.return_value = si
    return mf, mi, sc, si


@given(count=st.integers(min_value=1, max_value=4))
@settings(max_examples=100, deadline=None)
def test_faiss_accepts_1_to_4_indexes(count):
    """Property 9: Accept 1-4 indexes.

    **Validates: Requirements 5.1**
    """
    mf, mi, sc, si = _mocks()
    with patch("app.engine.faiss_manager.faiss", mf):
        with patch("app.engine.faiss_manager.SentenceTransformer", sc):
            from app.engine.faiss_manager import FAISSIndexManager
            mgr = FAISSIndexManager()
            cfgs = [_cfg(i) for i in range(count)]
            with patch.object(FAISSIndexManager, "_load_metadata", return_value=([], [])):
                asyncio.run(mgr.load_indexes(cfgs))
            assert len(mgr.get_loaded_indexes()) == count


@given(count=st.integers(min_value=5, max_value=20))
@settings(max_examples=100, deadline=None)
def test_faiss_rejects_more_than_4_indexes(count):
    """Property 9: Reject >4 indexes.

    **Validates: Requirements 5.1**
    """
    mf, mi, sc, si = _mocks()
    with patch("app.engine.faiss_manager.faiss", mf):
        with patch("app.engine.faiss_manager.SentenceTransformer", sc):
            from app.engine.faiss_manager import FAISSIndexManager
            mgr = FAISSIndexManager()
            cfgs = [_cfg(i) for i in range(count)]
            with pytest.raises(ValueError, match="Cannot load more than 4"):
                asyncio.run(mgr.load_indexes(cfgs))


@given(scores=st.lists(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    min_size=1, max_size=20,
))
@settings(max_examples=100, deadline=None)
def test_faiss_results_ranked_by_descending_score(scores):
    """Property 10: Results ordered by descending similarity score.

    **Validates: Requirements 5.3**
    """
    mf, mi, sc, si = _mocks()
    n = len(scores)
    docs = [f"doc-{i}" for i in range(n)]
    srcs = [f"src-{i}" for i in range(n)]
    with patch("app.engine.faiss_manager.faiss", mf):
        with patch("app.engine.faiss_manager.SentenceTransformer", sc):
            from app.engine.faiss_manager import FAISSIndexManager
            mgr = FAISSIndexManager()
            with patch.object(FAISSIndexManager, "_load_metadata", return_value=(docs, srcs)):
                asyncio.run(mgr.load_indexes([_cfg(0)]))
            mi.ntotal = n
            mi.search.return_value = (
                np.array([scores], dtype=np.float32),
                np.array([list(range(n))], dtype=np.int64),
            )
            si.encode.return_value = np.array([[0.1] * 384], dtype=np.float32)
            results = asyncio.run(mgr.query(0, "test query", top_k=n))
            assert len(results) == n
            result_scores = [r.score for r in results]
            assert result_scores == sorted(result_scores, reverse=True)
