"""
CHAINGUARD MCP Server - Lightweight Vector Store

Drop-in replacement for ChromaDB using sqlite3 + numpy.
Provides the same API surface (add, upsert, query, get, delete, count)
but with ~400 MB less RAM usage.

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.

Usage:
    from chainguard.vectorstore import LightVectorStore

    store = LightVectorStore("/path/to/storage")
    coll = store.get_or_create_collection("my_collection")
    coll.add(ids=["1"], embeddings=[[0.1, 0.2, ...]], documents=["text"], metadatas=[{...}])
    results = coll.query(query_embeddings=[[0.1, 0.2, ...]], n_results=5)
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("chainguard.vectorstore")

DB_FILENAME = "vectors.sqlite3"


class LightCollection:
    """
    A vector collection backed by sqlite3 + numpy.

    API is compatible with ChromaDB Collection for seamless migration.
    Vectors are kept in RAM as numpy arrays for fast cosine similarity search.
    Metadata and documents are stored in sqlite3 for persistence.
    """

    def __init__(self, name: str, db_path: Path, lock: threading.Lock):
        self._name = name
        self._db_path = db_path
        self._lock = lock

        # In-memory vectors: {doc_id: numpy array}
        self._vectors: Dict[str, np.ndarray] = {}

        self._init_table()
        self._load_vectors()

    @property
    def name(self) -> str:
        return self._name

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new connection (sqlite3 connections are not thread-safe)."""
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_table(self):
        """Create the collection table if it doesn't exist."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS "{self._name}" (
                        id TEXT PRIMARY KEY,
                        embedding BLOB NOT NULL,
                        document TEXT,
                        metadata TEXT
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def _load_vectors(self):
        """Load all vectors from sqlite3 into RAM."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(f'SELECT id, embedding FROM "{self._name}"')
                for row in cursor:
                    doc_id = row[0]
                    embedding_bytes = row[1]
                    self._vectors[doc_id] = np.frombuffer(embedding_bytes, dtype=np.float32)
            finally:
                conn.close()

        logger.debug(f"Loaded {len(self._vectors)} vectors for collection '{self._name}'")

    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ):
        """Add documents with embeddings to the collection."""
        documents = documents or [None] * len(ids)
        metadatas = metadatas or [None] * len(ids)

        with self._lock:
            conn = self._get_conn()
            try:
                for i, doc_id in enumerate(ids):
                    vec = np.array(embeddings[i], dtype=np.float32)
                    meta_json = json.dumps(metadatas[i]) if metadatas[i] else None

                    conn.execute(
                        f'INSERT OR IGNORE INTO "{self._name}" (id, embedding, document, metadata) VALUES (?, ?, ?, ?)',
                        (doc_id, vec.tobytes(), documents[i], meta_json),
                    )
                    self._vectors[doc_id] = vec

                conn.commit()
            finally:
                conn.close()

    def upsert(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ):
        """Add or update documents in the collection."""
        documents = documents or [None] * len(ids)
        metadatas = metadatas or [None] * len(ids)

        with self._lock:
            conn = self._get_conn()
            try:
                for i, doc_id in enumerate(ids):
                    vec = np.array(embeddings[i], dtype=np.float32)
                    meta_json = json.dumps(metadatas[i]) if metadatas[i] else None

                    conn.execute(
                        f'INSERT OR REPLACE INTO "{self._name}" (id, embedding, document, metadata) VALUES (?, ?, ?, ?)',
                        (doc_id, vec.tobytes(), documents[i], meta_json),
                    )
                    self._vectors[doc_id] = vec

                conn.commit()
            finally:
                conn.close()

    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, List[List]]:
        """
        Query the collection for similar vectors.

        Returns ChromaDB-compatible result format:
            {
                "ids": [[id1, id2, ...]],
                "documents": [[doc1, doc2, ...]],
                "metadatas": [[meta1, meta2, ...]],
                "distances": [[dist1, dist2, ...]]
            }

        Distances are cosine distances (0 = identical, 2 = opposite).
        """
        include = include or ["documents", "metadatas", "distances"]

        if not self._vectors:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        query_vec = np.array(query_embeddings[0], dtype=np.float32)

        # Normalize query vector
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm

        # Calculate cosine distances for all vectors
        scored: List[tuple] = []  # (doc_id, distance)

        for doc_id, vec in self._vectors.items():
            vec_norm = np.linalg.norm(vec)
            if vec_norm > 0:
                similarity = np.dot(query_vec, vec / vec_norm)
            else:
                similarity = 0.0
            # Cosine distance: 0 = identical, 2 = opposite (ChromaDB convention)
            distance = float(1.0 - similarity)
            scored.append((doc_id, distance))

        # Sort by distance (lower is better)
        scored.sort(key=lambda x: x[1])

        # Apply WHERE filter if provided, then take top n_results
        if where:
            scored = self._apply_where_filter(scored, where)

        top = scored[:n_results]

        if not top:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        # Fetch documents and metadata from sqlite3
        top_ids = [t[0] for t in top]
        top_distances = [t[1] for t in top]

        docs, metas = self._fetch_docs_meta(top_ids)

        result: Dict[str, List[List]] = {"ids": [top_ids]}

        if "documents" in include:
            result["documents"] = [docs]
        if "metadatas" in include:
            result["metadatas"] = [metas]
        if "distances" in include:
            result["distances"] = [top_distances]

        return result

    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """
        Get documents by IDs or filter.

        Returns ChromaDB-compatible format:
            {
                "ids": [id1, id2, ...],
                "documents": [doc1, doc2, ...],
                "metadatas": [meta1, meta2, ...],
                "embeddings": [emb1, emb2, ...]
            }
        """
        include = include or ["documents", "metadatas"]

        with self._lock:
            conn = self._get_conn()
            try:
                if ids:
                    placeholders = ",".join("?" * len(ids))
                    cursor = conn.execute(
                        f'SELECT id, embedding, document, metadata FROM "{self._name}" WHERE id IN ({placeholders})',
                        ids,
                    )
                else:
                    cursor = conn.execute(
                        f'SELECT id, embedding, document, metadata FROM "{self._name}"'
                    )

                rows = cursor.fetchall()
            finally:
                conn.close()

        # Apply WHERE filter on metadata if provided
        if where:
            rows = [r for r in rows if self._match_where(r[3], where)]

        result_ids = []
        result_docs = []
        result_metas = []
        result_embeddings = []

        for row in rows:
            result_ids.append(row[0])

            if "documents" in include:
                result_docs.append(row[2])
            if "metadatas" in include:
                meta = json.loads(row[3]) if row[3] else {}
                result_metas.append(meta)
            if "embeddings" in include:
                emb = np.frombuffer(row[1], dtype=np.float32).tolist()
                result_embeddings.append(emb)

        result: Dict[str, List] = {"ids": result_ids}
        if "documents" in include:
            result["documents"] = result_docs
        if "metadatas" in include:
            result["metadatas"] = result_metas
        if "embeddings" in include:
            result["embeddings"] = result_embeddings

        return result

    def delete(self, ids: Optional[List[str]] = None):
        """Delete documents by IDs."""
        if not ids:
            return

        with self._lock:
            conn = self._get_conn()
            try:
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f'DELETE FROM "{self._name}" WHERE id IN ({placeholders})',
                    ids,
                )
                conn.commit()

                for doc_id in ids:
                    self._vectors.pop(doc_id, None)
            finally:
                conn.close()

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return len(self._vectors)

    def _apply_where_filter(
        self, scored: List[tuple], where: Dict[str, Any]
    ) -> List[tuple]:
        """Apply a WHERE filter on scored results by checking metadata in sqlite3."""
        if not where:
            return scored

        doc_ids = [s[0] for s in scored]
        dist_map = {s[0]: s[1] for s in scored}

        with self._lock:
            conn = self._get_conn()
            try:
                placeholders = ",".join("?" * len(doc_ids))
                cursor = conn.execute(
                    f'SELECT id, metadata FROM "{self._name}" WHERE id IN ({placeholders})',
                    doc_ids,
                )
                rows = cursor.fetchall()
            finally:
                conn.close()

        filtered = []
        for row in rows:
            doc_id = row[0]
            if self._match_where(row[1], where):
                filtered.append((doc_id, dist_map[doc_id]))

        # Preserve original sort order
        filtered.sort(key=lambda x: x[1])
        return filtered

    @staticmethod
    def _match_where(metadata_json: Optional[str], where: Dict[str, Any]) -> bool:
        """
        Check if metadata matches a WHERE filter.

        Supports:
        - Simple equality: {"key": "value"}
        - $eq operator: {"key": {"$eq": "value"}}
        - $ne operator: {"key": {"$ne": "value"}}
        """
        if not metadata_json:
            return False

        try:
            meta = json.loads(metadata_json)
        except (json.JSONDecodeError, TypeError):
            return False

        for key, condition in where.items():
            meta_value = meta.get(key)

            if isinstance(condition, dict):
                if "$eq" in condition:
                    if meta_value != condition["$eq"]:
                        return False
                elif "$ne" in condition:
                    if meta_value == condition["$ne"]:
                        return False
            else:
                # Simple equality
                if meta_value != condition:
                    return False

        return True

    def _fetch_docs_meta(
        self, doc_ids: List[str]
    ) -> tuple:
        """Fetch documents and metadata for given IDs, preserving order."""
        if not doc_ids:
            return [], []

        with self._lock:
            conn = self._get_conn()
            try:
                placeholders = ",".join("?" * len(doc_ids))
                cursor = conn.execute(
                    f'SELECT id, document, metadata FROM "{self._name}" WHERE id IN ({placeholders})',
                    doc_ids,
                )
                rows = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
            finally:
                conn.close()

        docs = []
        metas = []
        for doc_id in doc_ids:
            if doc_id in rows:
                doc, meta_json = rows[doc_id]
                docs.append(doc or "")
                metas.append(json.loads(meta_json) if meta_json else {})
            else:
                docs.append("")
                metas.append({})

        return docs, metas


class LightVectorStore:
    """
    Lightweight vector store using sqlite3 + numpy.

    Drop-in replacement for ChromaDB PersistentClient.
    All collections share a single sqlite3 database file.
    Vectors are loaded into RAM as numpy arrays on startup (~3 MB for 1700 docs).

    Usage:
        store = LightVectorStore("/path/to/storage")
        coll = store.get_or_create_collection("my_collection")
    """

    def __init__(self, path: str):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._db_path = self._path / DB_FILENAME
        self._lock = threading.Lock()
        self._collections: Dict[str, LightCollection] = {}

    def get_or_create_collection(
        self, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> LightCollection:
        """
        Get or create a named collection.

        Args:
            name: Collection name
            metadata: Optional metadata (ignored, kept for API compat)

        Returns:
            LightCollection instance
        """
        if name not in self._collections:
            self._collections[name] = LightCollection(
                name=name, db_path=self._db_path, lock=self._lock
            )
        return self._collections[name]

    def close(self):
        """Release resources. Safe to call multiple times."""
        self._collections.clear()

    @property
    def path(self) -> str:
        return str(self._path)
