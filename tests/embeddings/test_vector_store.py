"""Tests for VectorDatabase (InMemoryVectorDB)."""

import numpy as np
import pytest

from src.embeddings.vector_store import InMemoryVectorDB, VectorDBEntry, VectorSearchResult


@pytest.fixture
def db() -> InMemoryVectorDB:
    return InMemoryVectorDB()


def make_entry(vid: str, vec: list, **meta: object) -> VectorDBEntry:
    """Helper to create a VectorDBEntry."""
    return VectorDBEntry(vector_id=vid, embedding=vec, metadata=dict(meta))


class TestUpsert:
    """Tests for upsert."""

    def test_upsert_single(self, db: InMemoryVectorDB) -> None:
        count = db.upsert([make_entry("v1", [1.0, 0.0, 0.0])])
        assert count == 1
        assert db.count() == 1

    def test_upsert_multiple(self, db: InMemoryVectorDB) -> None:
        entries = [
            make_entry("v1", [1.0, 0.0]),
            make_entry("v2", [0.0, 1.0]),
        ]
        count = db.upsert(entries)
        assert count == 2
        assert db.count() == 2

    def test_upsert_overwrites(self, db: InMemoryVectorDB) -> None:
        db.upsert([make_entry("v1", [1.0, 0.0], label="old")])
        db.upsert([make_entry("v1", [0.0, 1.0], label="new")])
        assert db.count() == 1
        results = db.query([0.0, 1.0], top_k=1)
        assert results[0].metadata["label"] == "new"


class TestQuery:
    """Tests for query."""

    def test_query_empty_db(self, db: InMemoryVectorDB) -> None:
        results = db.query([1.0, 0.0, 0.0])
        assert results == []

    def test_query_finds_similar(self, db: InMemoryVectorDB) -> None:
        db.upsert([
            make_entry("v1", [1.0, 0.0, 0.0]),
            make_entry("v2", [0.0, 1.0, 0.0]),
        ])
        results = db.query([0.9, 0.1, 0.0], top_k=1)
        assert len(results) == 1
        assert results[0].vector_id == "v1"
        assert results[0].score > 0.9

    def test_query_top_k(self, db: InMemoryVectorDB) -> None:
        for i in range(10):
            vec = [0.0] * 3
            vec[i % 3] = 1.0
            db.upsert([make_entry(f"v{i}", vec)])
        results = db.query([1.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3

    def test_query_sorted_by_score(self, db: InMemoryVectorDB) -> None:
        db.upsert([
            make_entry("exact", [1.0, 0.0]),
            make_entry("opposite", [-1.0, 0.0]),
            make_entry("similar", [0.8, 0.2]),
        ])
        results = db.query([1.0, 0.0], top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_query_with_filter(self, db: InMemoryVectorDB) -> None:
        db.upsert([
            make_entry("v1", [1.0, 0.0], task="faq"),
            make_entry("v2", [0.9, 0.1], task="coding"),
        ])
        results = db.query([1.0, 0.0], top_k=5, filter={"task": "coding"})
        assert len(results) == 1
        assert results[0].vector_id == "v2"

    def test_query_returns_search_results(self, db: InMemoryVectorDB) -> None:
        db.upsert([make_entry("v1", [1.0, 0.0])])
        results = db.query([1.0, 0.0])
        assert isinstance(results[0], VectorSearchResult)


class TestDelete:
    """Tests for delete."""

    def test_delete_existing(self, db: InMemoryVectorDB) -> None:
        db.upsert([make_entry("v1", [1.0, 0.0])])
        count = db.delete(["v1"])
        assert count == 1
        assert db.count() == 0

    def test_delete_nonexistent(self, db: InMemoryVectorDB) -> None:
        count = db.delete(["nonexistent"])
        assert count == 0

    def test_delete_partial(self, db: InMemoryVectorDB) -> None:
        db.upsert([
            make_entry("v1", [1.0, 0.0]),
            make_entry("v2", [0.0, 1.0]),
        ])
        count = db.delete(["v1", "nonexistent"])
        assert count == 1
        assert db.count() == 1


class TestCount:
    """Tests for count."""

    def test_empty(self, db: InMemoryVectorDB) -> None:
        assert db.count() == 0

    def test_after_upsert(self, db: InMemoryVectorDB) -> None:
        db.upsert([make_entry("v1", [1.0])])
        assert db.count() == 1
