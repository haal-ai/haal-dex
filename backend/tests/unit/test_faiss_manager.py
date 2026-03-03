"""Unit tests for FAISSIndexManager.

All heavy dependencies (faiss, sentence-transformers, numpy) are mocked
since they may not be installed in the test environment.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.models.faiss_models import IndexConfig, SimilarityResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(index_id: int = 0, name: str = "test-index") -> IndexConfig:
    return IndexConfig(
        index_id=index_id,
        name=name,
        description=f"Test index {index_id}",
        index_path=f"/fake/path/index_{index_id}.faiss",
        embedding_model="all-MiniLM-L6-v2",
    )


def _make_mock_faiss_module():
    """Return a mock faiss module with a working read_index."""
    mock_faiss = MagicMock()
    mock_index = MagicMock()
    mock_index.ntotal = 10
    mock_faiss.read_index.return_value = mock_index
    return mock_faiss, mock_index


def _make_mock_sentence_transformer():
    """Return a mock SentenceTransformer class."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    return mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Import with mocked dependencies
# ---------------------------------------------------------------------------

@pytest.fixture
def faiss_mocks():
    """Patch faiss and SentenceTransformer at the module level."""
    mock_faiss, mock_index = _make_mock_faiss_module()
    mock_st_cls, mock_st_instance = _make_mock_sentence_transformer()

    with (
        patch("app.engine.faiss_manager.faiss", mock_faiss),
        patch("app.engine.faiss_manager.SentenceTransformer", mock_st_cls),
    ):
        from app.engine.faiss_manager import FAISSIndexManager
        yield {
            "manager_cls": FAISSIndexManager,
            "faiss": mock_faiss,
            "faiss_index": mock_index,
            "st_cls": mock_st_cls,
            "st_instance": mock_st_instance,
        }


@pytest.fixture
def manager(faiss_mocks):
    return faiss_mocks["manager_cls"]()


# ---------------------------------------------------------------------------
# load_indexes
# ---------------------------------------------------------------------------

class TestLoadIndexes:
    @pytest.mark.asyncio
    async def test_load_single_index(self, manager, faiss_mocks):
        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            await manager.load_indexes([config])
        assert manager.get_loaded_indexes() == [0]

    @pytest.mark.asyncio
    async def test_load_up_to_four_indexes(self, manager, faiss_mocks):
        configs = [_make_config(i, f"idx-{i}") for i in range(4)]
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            await manager.load_indexes(configs)
        assert manager.get_loaded_indexes() == [0, 1, 2, 3]

    @pytest.mark.asyncio
    async def test_reject_more_than_four_indexes(self, manager, faiss_mocks):
        configs = [_make_config(i, f"idx-{i}") for i in range(5)]
        with pytest.raises(ValueError, match="Cannot load more than 4"):
            await manager.load_indexes(configs)

    @pytest.mark.asyncio
    async def test_error_when_index_file_unreadable(self, faiss_mocks):
        manager = faiss_mocks["manager_cls"]()
        faiss_mocks["faiss"].read_index.side_effect = RuntimeError("file not found")
        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            with pytest.raises(ValueError, match="is unavailable"):
                await manager.load_indexes([config])

    @pytest.mark.asyncio
    async def test_error_when_embedding_model_unavailable(self, faiss_mocks):
        manager = faiss_mocks["manager_cls"]()
        faiss_mocks["st_cls"].side_effect = RuntimeError("model not found")
        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            with pytest.raises(ValueError, match="is unavailable"):
                await manager.load_indexes([config])


# ---------------------------------------------------------------------------
# load_indexes — missing libraries
# ---------------------------------------------------------------------------

class TestLoadIndexesMissingLibs:
    @pytest.mark.asyncio
    async def test_error_when_faiss_not_installed(self):
        with (
            patch("app.engine.faiss_manager.faiss", None),
            patch("app.engine.faiss_manager.SentenceTransformer", MagicMock()),
        ):
            from app.engine.faiss_manager import FAISSIndexManager
            mgr = FAISSIndexManager()
            with pytest.raises(ValueError, match="faiss-cpu is not installed"):
                await mgr.load_indexes([_make_config(0)])

    @pytest.mark.asyncio
    async def test_error_when_sentence_transformers_not_installed(self):
        with (
            patch("app.engine.faiss_manager.faiss", MagicMock()),
            patch("app.engine.faiss_manager.SentenceTransformer", None),
        ):
            from app.engine.faiss_manager import FAISSIndexManager
            mgr = FAISSIndexManager()
            with pytest.raises(ValueError, match="sentence-transformers is not installed"):
                await mgr.load_indexes([_make_config(0)])


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

class TestQuery:
    @pytest.mark.asyncio
    async def test_query_returns_results_ranked_by_score(self, manager, faiss_mocks):
        """Validates: Requirements 5.3 — results ranked by descending similarity score."""
        import numpy as np

        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=(
            ["doc A", "doc B", "doc C"],
            ["src A", "src B", "src C"],
        )):
            await manager.load_indexes([config])

        # Mock the FAISS search to return 3 results with known distances
        mock_index = faiss_mocks["faiss_index"]
        mock_index.ntotal = 3
        mock_index.search.return_value = (
            np.array([[0.3, 0.9, 0.6]], dtype=np.float32),
            np.array([[0, 1, 2]], dtype=np.int64),
        )
        faiss_mocks["st_instance"].encode.return_value = np.array(
            [[0.1] * 384], dtype=np.float32
        )

        results = await manager.query(0, "test query", top_k=3)

        assert len(results) == 3
        # Verify descending order
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0].score == pytest.approx(0.9)
        assert results[0].document_fragment == "doc B"
        assert results[0].source_document == "src B"
        assert results[0].index_id == 0

    @pytest.mark.asyncio
    async def test_query_unloaded_index_raises(self, manager, faiss_mocks):
        """Validates: Requirements 5.4 — error for unavailable index."""
        with pytest.raises(ValueError, match="FAISS index 2 is not loaded"):
            await manager.query(2, "test query")

    @pytest.mark.asyncio
    async def test_query_empty_index_returns_empty(self, manager, faiss_mocks):
        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            await manager.load_indexes([config])

        faiss_mocks["faiss_index"].ntotal = 0

        results = await manager.query(0, "test query", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_query_top_k_clamped_to_index_size(self, manager, faiss_mocks):
        import numpy as np

        config = _make_config(0)
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=(
            ["doc A", "doc B"],
            ["src A", "src B"],
        )):
            await manager.load_indexes([config])

        faiss_mocks["faiss_index"].ntotal = 2
        faiss_mocks["faiss_index"].search.return_value = (
            np.array([[0.8, 0.5]], dtype=np.float32),
            np.array([[0, 1]], dtype=np.int64),
        )
        faiss_mocks["st_instance"].encode.return_value = np.array(
            [[0.1] * 384], dtype=np.float32
        )

        results = await manager.query(0, "test", top_k=100)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# get_loaded_indexes
# ---------------------------------------------------------------------------

class TestGetLoadedIndexes:
    def test_empty_initially(self, manager):
        assert manager.get_loaded_indexes() == []

    @pytest.mark.asyncio
    async def test_returns_sorted_ids(self, manager, faiss_mocks):
        configs = [_make_config(3, "c"), _make_config(1, "a")]
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            await manager.load_indexes(configs)
        assert manager.get_loaded_indexes() == [1, 3]


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------

class TestErrorReporting:
    @pytest.mark.asyncio
    async def test_unavailable_index_error_identifies_index(self, manager, faiss_mocks):
        """Validates: Requirements 5.4 — error identifies the missing index."""
        with pytest.raises(ValueError) as exc_info:
            await manager.query(7, "hello")
        assert "7" in str(exc_info.value)
        assert "not loaded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_load_failure_identifies_index(self, faiss_mocks):
        """Validates: Requirements 5.4 — load error identifies the failing index."""
        manager = faiss_mocks["manager_cls"]()
        faiss_mocks["faiss"].read_index.side_effect = FileNotFoundError("no such file")
        config = _make_config(2, "my-corpus")
        with patch("app.engine.faiss_manager.FAISSIndexManager._load_metadata", return_value=([], [])):
            with pytest.raises(ValueError, match="FAISS index 2.*'my-corpus'.*unavailable"):
                await manager.load_indexes([config])
