"""
Tests for chainguard.vectorstore module.

Tests the LightVectorStore and LightCollection classes that replace ChromaDB.
"""

import json
import os
import tempfile

import numpy as np
import pytest

from chainguard.vectorstore import LightCollection, LightVectorStore, DB_FILENAME


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def store(temp_dir):
    """Create a LightVectorStore in a temporary directory."""
    return LightVectorStore(temp_dir)


@pytest.fixture
def collection(store):
    """Create a test collection."""
    return store.get_or_create_collection("test_collection")


def _random_embedding(dim=384):
    """Generate a random normalized embedding vector."""
    vec = np.random.randn(dim).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


class TestLightVectorStore:
    """Tests for LightVectorStore."""

    def test_create_store(self, temp_dir):
        """Test creating a vector store."""
        store = LightVectorStore(temp_dir)
        assert store is not None
        assert store.path == temp_dir

    def test_creates_directory(self):
        """Test that store creates the directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = os.path.join(tmpdir, "subdir", "store")
            store = LightVectorStore(new_path)
            assert os.path.isdir(new_path)

    def test_get_or_create_collection(self, store):
        """Test getting or creating a collection."""
        coll = store.get_or_create_collection("test")
        assert coll is not None
        assert coll.name == "test"

    def test_get_same_collection(self, store):
        """Test that getting the same collection returns the same instance."""
        coll1 = store.get_or_create_collection("test")
        coll2 = store.get_or_create_collection("test")
        assert coll1 is coll2

    def test_multiple_collections(self, store):
        """Test creating multiple collections."""
        coll1 = store.get_or_create_collection("coll_a")
        coll2 = store.get_or_create_collection("coll_b")
        assert coll1.name == "coll_a"
        assert coll2.name == "coll_b"
        assert coll1 is not coll2

    def test_close(self, store):
        """Test closing the store."""
        store.get_or_create_collection("test")
        store.close()
        # After close, collections should be cleared

    def test_db_file_created(self, temp_dir):
        """Test that the sqlite3 database file is created."""
        store = LightVectorStore(temp_dir)
        coll = store.get_or_create_collection("test")
        coll.add(ids=["1"], embeddings=[_random_embedding()], documents=["test"])
        assert os.path.exists(os.path.join(temp_dir, DB_FILENAME))


class TestLightCollectionAdd:
    """Tests for LightCollection.add()."""

    def test_add_single(self, collection):
        """Test adding a single document."""
        emb = _random_embedding()
        collection.add(
            ids=["doc1"],
            embeddings=[emb],
            documents=["Hello world"],
            metadatas=[{"type": "test"}]
        )
        assert collection.count() == 1

    def test_add_multiple(self, collection):
        """Test adding multiple documents."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()],
            documents=["First", "Second", "Third"],
            metadatas=[{"i": 1}, {"i": 2}, {"i": 3}]
        )
        assert collection.count() == 3

    def test_add_without_metadata(self, collection):
        """Test adding documents without metadata."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            documents=["Hello"]
        )
        assert collection.count() == 1

    def test_add_without_documents(self, collection):
        """Test adding embeddings without documents."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()]
        )
        assert collection.count() == 1

    def test_add_duplicate_ignored(self, collection):
        """Test that adding a duplicate ID is ignored (INSERT OR IGNORE)."""
        emb = _random_embedding()
        collection.add(ids=["doc1"], embeddings=[emb], documents=["First"])
        collection.add(ids=["doc1"], embeddings=[emb], documents=["Second"])
        assert collection.count() == 1

        # Original document should be preserved
        result = collection.get(ids=["doc1"], include=["documents"])
        assert result["documents"][0] == "First"


class TestLightCollectionUpsert:
    """Tests for LightCollection.upsert()."""

    def test_upsert_new(self, collection):
        """Test upserting a new document."""
        collection.upsert(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            documents=["Hello"],
            metadatas=[{"key": "value"}]
        )
        assert collection.count() == 1

    def test_upsert_existing(self, collection):
        """Test upserting updates an existing document."""
        emb = _random_embedding()
        collection.add(ids=["doc1"], embeddings=[emb], documents=["First"])

        new_emb = _random_embedding()
        collection.upsert(ids=["doc1"], embeddings=[new_emb], documents=["Updated"])
        assert collection.count() == 1

        result = collection.get(ids=["doc1"], include=["documents"])
        assert result["documents"][0] == "Updated"


class TestLightCollectionQuery:
    """Tests for LightCollection.query()."""

    def test_query_empty_collection(self, collection):
        """Test querying an empty collection."""
        result = collection.query(query_embeddings=[_random_embedding()], n_results=5)
        assert result["ids"] == [[]]
        assert result["documents"] == [[]]
        assert result["distances"] == [[]]

    def test_query_returns_results(self, collection):
        """Test querying returns results in ChromaDB format."""
        # Add some documents
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()],
            documents=["First doc", "Second doc"],
            metadatas=[{"type": "a"}, {"type": "b"}]
        )

        result = collection.query(query_embeddings=[_random_embedding()], n_results=5)

        # Check ChromaDB-compatible format
        assert "ids" in result
        assert "documents" in result
        assert "metadatas" in result
        assert "distances" in result

        # Results are wrapped in outer list
        assert isinstance(result["ids"][0], list)
        assert len(result["ids"][0]) == 2

    def test_query_returns_sorted_by_distance(self, collection):
        """Test that query results are sorted by distance (closest first)."""
        # Create a known vector and a similar one
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        similar = np.array([0.9] + [0.1] * 383, dtype=np.float32)
        different = np.array([0.0] * 383 + [1.0], dtype=np.float32)

        collection.add(
            ids=["similar", "different"],
            embeddings=[similar.tolist(), different.tolist()],
            documents=["Similar", "Different"]
        )

        result = collection.query(query_embeddings=[base.tolist()], n_results=2)
        distances = result["distances"][0]

        # First result should have lower distance
        assert distances[0] <= distances[1]

    def test_query_n_results_limit(self, collection):
        """Test that n_results limits the output."""
        for i in range(10):
            collection.add(
                ids=[f"doc{i}"],
                embeddings=[_random_embedding()],
                documents=[f"Doc {i}"]
            )

        result = collection.query(query_embeddings=[_random_embedding()], n_results=3)
        assert len(result["ids"][0]) == 3

    def test_query_with_include(self, collection):
        """Test that include parameter controls output fields."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            documents=["Hello"],
            metadatas=[{"key": "val"}]
        )

        # Only request distances
        result = collection.query(
            query_embeddings=[_random_embedding()],
            n_results=1,
            include=["distances"]
        )
        assert "distances" in result
        assert "documents" not in result
        assert "metadatas" not in result


class TestLightCollectionGet:
    """Tests for LightCollection.get()."""

    def test_get_by_ids(self, collection):
        """Test getting documents by IDs."""
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()],
            documents=["First", "Second"],
            metadatas=[{"key": "a"}, {"key": "b"}]
        )

        result = collection.get(ids=["doc1"])
        assert result["ids"] == ["doc1"]
        assert result["documents"] == ["First"]
        assert result["metadatas"] == [{"key": "a"}]

    def test_get_all(self, collection):
        """Test getting all documents."""
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()],
            documents=["First", "Second"]
        )

        result = collection.get(include=["documents"])
        assert len(result["ids"]) == 2

    def test_get_nonexistent(self, collection):
        """Test getting a nonexistent document."""
        result = collection.get(ids=["nonexistent"])
        assert result["ids"] == []

    def test_get_with_embeddings(self, collection):
        """Test getting documents with embeddings included."""
        emb = _random_embedding()
        collection.add(ids=["doc1"], embeddings=[emb], documents=["Test"])

        result = collection.get(ids=["doc1"], include=["documents", "embeddings"])
        assert "embeddings" in result
        assert len(result["embeddings"]) == 1
        np.testing.assert_array_almost_equal(result["embeddings"][0], emb, decimal=5)


class TestLightCollectionDelete:
    """Tests for LightCollection.delete()."""

    def test_delete_single(self, collection):
        """Test deleting a single document."""
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()],
            documents=["First", "Second"]
        )
        assert collection.count() == 2

        collection.delete(ids=["doc1"])
        assert collection.count() == 1

        result = collection.get(ids=["doc1"])
        assert result["ids"] == []

    def test_delete_multiple(self, collection):
        """Test deleting multiple documents."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()],
            documents=["First", "Second", "Third"]
        )
        collection.delete(ids=["doc1", "doc3"])
        assert collection.count() == 1

    def test_delete_nonexistent(self, collection):
        """Test deleting a nonexistent document (no error)."""
        collection.delete(ids=["nonexistent"])
        assert collection.count() == 0

    def test_delete_none(self, collection):
        """Test delete with None ids."""
        collection.add(ids=["doc1"], embeddings=[_random_embedding()])
        collection.delete(ids=None)
        assert collection.count() == 1  # Nothing deleted


class TestLightCollectionCount:
    """Tests for LightCollection.count()."""

    def test_count_empty(self, collection):
        """Test count on empty collection."""
        assert collection.count() == 0

    def test_count_after_add(self, collection):
        """Test count after adding documents."""
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()]
        )
        assert collection.count() == 2

    def test_count_after_delete(self, collection):
        """Test count after deleting documents."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()]
        )
        collection.delete(ids=["doc2"])
        assert collection.count() == 2


class TestWhereFilter:
    """Tests for WHERE filter functionality."""

    def test_simple_equality(self, collection):
        """Test simple equality WHERE filter."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()],
            documents=["First", "Second", "Third"],
            metadatas=[{"type": "a"}, {"type": "b"}, {"type": "a"}]
        )

        result = collection.get(where={"type": "a"}, include=["documents"])
        assert len(result["ids"]) == 2

    def test_eq_operator(self, collection):
        """Test $eq operator in WHERE filter."""
        collection.add(
            ids=["doc1", "doc2"],
            embeddings=[_random_embedding(), _random_embedding()],
            metadatas=[{"status": "active"}, {"status": "inactive"}]
        )

        result = collection.get(where={"status": {"$eq": "active"}})
        assert len(result["ids"]) == 1
        assert result["ids"][0] == "doc1"

    def test_ne_operator(self, collection):
        """Test $ne operator in WHERE filter."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()],
            metadatas=[{"status": "active"}, {"status": "inactive"}, {"status": "active"}]
        )

        result = collection.get(where={"status": {"$ne": "active"}})
        assert len(result["ids"]) == 1
        assert result["ids"][0] == "doc2"

    def test_where_filter_in_query(self, collection):
        """Test WHERE filter in query method."""
        collection.add(
            ids=["doc1", "doc2", "doc3"],
            embeddings=[_random_embedding(), _random_embedding(), _random_embedding()],
            documents=["First", "Second", "Third"],
            metadatas=[{"type": "code"}, {"type": "doc"}, {"type": "code"}]
        )

        result = collection.query(
            query_embeddings=[_random_embedding()],
            n_results=5,
            where={"type": "code"}
        )
        assert len(result["ids"][0]) == 2

    def test_where_no_match(self, collection):
        """Test WHERE filter with no matches."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            metadatas=[{"type": "a"}]
        )

        result = collection.get(where={"type": "nonexistent"})
        assert result["ids"] == []


class TestPersistence:
    """Tests for data persistence across store instances."""

    def test_data_persists(self, temp_dir):
        """Test that data survives closing and reopening the store."""
        # Write data
        store1 = LightVectorStore(temp_dir)
        coll1 = store1.get_or_create_collection("persist_test")
        emb = _random_embedding()
        coll1.add(
            ids=["doc1"],
            embeddings=[emb],
            documents=["Persisted text"],
            metadatas=[{"key": "value"}]
        )
        store1.close()

        # Read data in new store instance
        store2 = LightVectorStore(temp_dir)
        coll2 = store2.get_or_create_collection("persist_test")

        assert coll2.count() == 1

        result = coll2.get(ids=["doc1"], include=["documents", "metadatas"])
        assert result["ids"] == ["doc1"]
        assert result["documents"] == ["Persisted text"]
        assert result["metadatas"] == [{"key": "value"}]
        store2.close()

    def test_vectors_persist(self, temp_dir):
        """Test that vectors are correctly persisted and reloaded."""
        emb = _random_embedding()

        store1 = LightVectorStore(temp_dir)
        coll1 = store1.get_or_create_collection("vec_test")
        coll1.add(ids=["doc1"], embeddings=[emb], documents=["Test"])
        store1.close()

        store2 = LightVectorStore(temp_dir)
        coll2 = store2.get_or_create_collection("vec_test")

        # Query should work after reload
        result = coll2.query(query_embeddings=[emb], n_results=1)
        assert len(result["ids"][0]) == 1
        assert result["ids"][0][0] == "doc1"
        # Distance to self should be very close to 0
        assert result["distances"][0][0] < 0.01
        store2.close()


class TestChromaDBCompatibility:
    """Tests ensuring ChromaDB-compatible result format."""

    def test_query_result_format(self, collection):
        """Test that query results match ChromaDB format."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            documents=["Test"],
            metadatas=[{"key": "val"}]
        )

        result = collection.query(
            query_embeddings=[_random_embedding()],
            n_results=5,
            include=["documents", "metadatas", "distances"]
        )

        # ChromaDB wraps in outer list for batch queries
        assert isinstance(result["ids"], list)
        assert isinstance(result["ids"][0], list)
        assert isinstance(result["documents"], list)
        assert isinstance(result["documents"][0], list)
        assert isinstance(result["metadatas"], list)
        assert isinstance(result["metadatas"][0], list)
        assert isinstance(result["distances"], list)
        assert isinstance(result["distances"][0], list)

    def test_get_result_format(self, collection):
        """Test that get results match ChromaDB format."""
        collection.add(
            ids=["doc1"],
            embeddings=[_random_embedding()],
            documents=["Test"],
            metadatas=[{"key": "val"}]
        )

        result = collection.get(ids=["doc1"], include=["documents", "metadatas"])

        # ChromaDB get() returns flat lists (not nested)
        assert isinstance(result["ids"], list)
        assert isinstance(result["documents"], list)
        assert isinstance(result["metadatas"], list)
        assert result["ids"][0] == "doc1"  # Direct access, not [0][0]

    def test_empty_query_format(self, collection):
        """Test empty query result format."""
        result = collection.query(query_embeddings=[_random_embedding()], n_results=5)

        assert result == {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }
