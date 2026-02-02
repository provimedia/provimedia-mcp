"""
CHAINGUARD MCP Server - Memory Module

Long-Term Memory System with ChromaDB for project-specific knowledge persistence.
Provides semantic search, automatic indexing, and smart context injection.

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.

Usage:
    from chainguard.memory import memory_manager, get_project_id

    # Get memory for current project
    project_id = get_project_id("/path/to/project")
    memory = await memory_manager.get_memory(project_id)

    # Query memory
    results = await memory.query("Where is authentication handled?")
"""

import asyncio
import hashlib
import json
import logging
import subprocess
import time

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor

from .config import CHAINGUARD_HOME, STALE_MEMORY_THRESHOLD_DAYS
from .cache import TTLLRUCache, git_cache  # v5.3.1: Bounded cache + git cache
from .embeddings import embedding_engine, KeywordExtractor, detect_task_type

logger = logging.getLogger("chainguard.memory")

# Memory Configuration
MEMORY_HOME = CHAINGUARD_HOME / "memory"
MEMORY_HOME.mkdir(parents=True, exist_ok=True)

# Collection names
COLLECTIONS = [
    "code_structure",      # Files, modules, directories
    "functions",           # Functions, methods, classes
    "database_schema",     # Tables, columns, relations
    "architecture",        # Patterns, frameworks, conventions
    "learnings",           # Insights from work sessions
    "code_summaries",      # Deep logic summaries extracted from code (v5.4)
]

# Scoring weights
SCORING_WEIGHTS = {
    "semantic": 0.60,      # Semantic similarity (main factor)
    "keyword": 0.25,       # Keyword match
    "recency": 0.15,       # Recency bonus
}

# Type bonuses for different task types
TYPE_BONUSES = {
    "bug": {"function": 0.1, "error": 0.15},
    "feature": {"architecture": 0.1, "pattern": 0.1},
    "database": {"table": 0.2, "migration": 0.15},
    "test": {"test": 0.2, "spec": 0.15},
    "refactor": {"function": 0.1, "class": 0.1},
}

# Sensitive file patterns (not indexed)
SENSITIVE_PATTERNS = [
    ".env", "credentials", "secrets",
    "password", "api_key", "private_key",
    ".pem", ".key", "id_rsa",
]

# Excluded directories (not indexed)
EXCLUDED_DIRECTORIES = [
    "node_modules/", "vendor/", ".git/",
    "dist/", "build/", ".next/",
    "__pycache__/", ".cache/", ".venv/",
    "venv/", "coverage/", ".nyc_output/",
    "package-lock.json", "yarn.lock", "composer.lock",
]


@dataclass
class MemoryDocument:
    """A document stored in memory."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class ScoredResult:
    """A search result with relevance score."""
    document: MemoryDocument
    semantic_score: float      # 0.0 - 1.0
    keyword_score: float       # 0.0 - 1.0
    recency_score: float       # 0.0 - 1.0
    final_score: float         # Weighted combination
    collection: str            # Source collection


@dataclass
class MemoryStats:
    """Statistics about project memory."""
    project_id: str
    initialized_at: Optional[str]
    last_update: Optional[str]
    collections: Dict[str, int]  # collection_name -> document_count
    total_documents: int
    storage_size_mb: float


def get_project_id(working_dir: str) -> str:
    """
    Calculate a unique, stable project ID (v5.3.1: with caching).

    Priority:
    1. Git remote URL (if available) -> Same ID across machines
    2. Git root path (if git repo) -> Stable for subdirectories
    3. Working directory path -> Fallback

    Returns:
        16-character hex hash (e.g., "a1b2c3d4e5f6g7h8")

    Note: Uses git_cache to minimize blocking subprocess calls.
    After first call, subsequent calls are instant.
    """
    resolved_path = str(Path(working_dir).resolve())

    # v5.3.1: Check cache first to avoid blocking subprocess calls
    cached = git_cache.get(resolved_path)
    if cached:
        return cached

    # 1. Try git remote URL
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            source = result.stdout.strip()
            project_id = hashlib.sha256(source.encode()).hexdigest()[:16]
            git_cache.set(resolved_path, project_id)
            return project_id
    except Exception:
        pass

    # 2. Try git root path
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            source = result.stdout.strip()
            project_id = hashlib.sha256(source.encode()).hexdigest()[:16]
            git_cache.set(resolved_path, project_id)
            return project_id
    except Exception:
        pass

    # 3. Fallback: Working directory
    project_id = hashlib.sha256(resolved_path.encode()).hexdigest()[:16]
    git_cache.set(resolved_path, project_id)
    return project_id


def validate_project_isolation(requested_project_id: str, working_dir: str) -> bool:
    """
    Validate that only the own project is being accessed.

    Prevents:
    - Access to foreign project_ids
    - Path traversal attacks
    - Project ID manipulation
    """
    # 1. Recalculate project ID from working_dir
    expected_id = get_project_id(working_dir)

    # 2. Must match requested ID
    if requested_project_id != expected_id:
        raise SecurityError(
            f"Project-ID mismatch! Expected {expected_id}, got {requested_project_id}"
        )

    # 3. Validate memory path (no path traversal)
    memory_path = MEMORY_HOME / requested_project_id
    try:
        resolved = memory_path.resolve()
        resolved.relative_to(MEMORY_HOME)
    except ValueError:
        raise SecurityError(f"Invalid memory path: {memory_path}")

    return True


class SecurityError(Exception):
    """Security violation in memory access."""
    pass


class ProjectMemory:
    """
    Memory for a single project.

    Encapsulates all ChromaDB operations for this project.
    Each project has its own SQLite database file.
    """

    def __init__(self, project_id: str, path: Path):
        self.project_id = project_id
        self.path = path
        self.last_access = time.time()
        self._client = None
        self._collections: Dict[str, Any] = {}
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._metadata_path = path / "metadata.json"
        self._initialized = False
        self._init_lock = asyncio.Lock()  # v5.3.1: Fix race condition

    async def _ensure_initialized(self):
        """Lazy initialization of ChromaDB client (thread-safe v5.3.1)."""
        if self._initialized:
            return

        async with self._init_lock:  # v5.3.1: Double-check locking pattern
            if self._initialized:
                return

            try:
                import chromadb
                from chromadb.config import Settings

                # ChromaDB with project-specific path
                self._client = chromadb.PersistentClient(
                    path=str(self.path),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=False,  # Protection against accidental deletion
                        is_persistent=True
                    )
                )

                # Get or create collections
                for name in COLLECTIONS:
                    self._collections[name] = self._client.get_or_create_collection(
                        name=name,
                        metadata={"hnsw:space": "cosine"}
                    )

                self._initialized = True
                logger.info(f"Initialized memory for project {self.project_id}")

            except ImportError:
                logger.error(
                    "chromadb not installed. "
                    "Run: pip install chromadb sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to initialize memory: {e}")
                raise

    async def add(
        self,
        content: str,
        collection: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Add a document to memory.

        Args:
            content: Text content to embed and store
            collection: Target collection name
            metadata: Optional metadata dict
            doc_id: Optional document ID (generated if not provided)

        Returns:
            Document ID
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        # Generate ID if not provided
        if not doc_id:
            doc_id = hashlib.sha256(
                f"{collection}:{content[:100]}".encode()
            ).hexdigest()[:16]

        # Prepare metadata
        meta = metadata or {}
        meta["updated_at"] = datetime.now().isoformat()
        meta["collection"] = collection

        # Generate embedding
        embedding_result = await embedding_engine.encode_single(content)

        # Add to collection (sync operation in thread pool)
        coll = self._collections.get(collection)
        if not coll:
            raise ValueError(f"Unknown collection: {collection}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: coll.add(
                ids=[doc_id],
                embeddings=[embedding_result],
                documents=[content],
                metadatas=[meta]
            )
        )

        return doc_id

    async def upsert(
        self,
        content: str,
        collection: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Add or update a document in memory.

        Same as add() but updates if document exists.
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        # Generate ID if not provided
        if not doc_id:
            doc_id = hashlib.sha256(
                f"{collection}:{content[:100]}".encode()
            ).hexdigest()[:16]

        # Prepare metadata
        meta = metadata or {}
        meta["updated_at"] = datetime.now().isoformat()
        meta["collection"] = collection

        # Generate embedding
        embedding_result = await embedding_engine.encode_single(content)

        # Upsert to collection
        coll = self._collections.get(collection)
        if not coll:
            raise ValueError(f"Unknown collection: {collection}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: coll.upsert(
                ids=[doc_id],
                embeddings=[embedding_result],
                documents=[content],
                metadatas=[meta]
            )
        )

        return doc_id

    async def query(
        self,
        query_text: str,
        collection: str = "all",
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[MemoryDocument, float]]:
        """
        Query memory for relevant documents.

        Args:
            query_text: Natural language query
            collection: Collection to search ("all" for all collections)
            n_results: Maximum results per collection
            where: Optional filter conditions

        Returns:
            List of (document, distance) tuples, sorted by distance
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        # Generate query embedding
        query_embedding = await embedding_engine.encode_single(query_text)

        results: List[Tuple[MemoryDocument, float]] = []

        # Determine which collections to search
        if collection == "all":
            collections_to_search = list(self._collections.items())
        else:
            coll = self._collections.get(collection)
            if not coll:
                return []
            collections_to_search = [(collection, coll)]

        # Search each collection
        loop = asyncio.get_event_loop()
        for coll_name, coll in collections_to_search:
            try:
                hits = await loop.run_in_executor(
                    self._executor,
                    lambda c=coll: c.query(
                        query_embeddings=[query_embedding],
                        n_results=n_results,
                        where=where,
                        include=["documents", "metadatas", "distances"]
                    )
                )

                # Process results
                if hits and hits.get("ids") and hits["ids"][0]:
                    for i, doc_id in enumerate(hits["ids"][0]):
                        doc = MemoryDocument(
                            id=doc_id,
                            content=hits["documents"][0][i] if hits.get("documents") else "",
                            metadata=hits["metadatas"][0][i] if hits.get("metadatas") else {}
                        )
                        doc.metadata["_collection"] = coll_name
                        distance = hits["distances"][0][i] if hits.get("distances") else 1.0
                        results.append((doc, distance))

            except Exception as e:
                logger.warning(f"Query error in {coll_name}: {e}")
                continue

        # Sort by distance (lower is better)
        results.sort(key=lambda x: x[1])
        return results[:n_results * 2]  # Return top results across collections

    async def delete(
        self,
        collection: str,
        doc_ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Delete documents from memory.

        Args:
            collection: Target collection
            doc_ids: Optional list of document IDs to delete
            where: Optional filter conditions

        Returns:
            Number of deleted documents
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        coll = self._collections.get(collection)
        if not coll:
            return 0

        loop = asyncio.get_event_loop()

        if doc_ids:
            await loop.run_in_executor(
                self._executor,
                lambda: coll.delete(ids=doc_ids)
            )
            return len(doc_ids)
        elif where:
            # Get matching IDs first
            results = await loop.run_in_executor(
                self._executor,
                lambda: coll.get(where=where, include=[])
            )
            if results and results.get("ids"):
                ids = results["ids"]
                await loop.run_in_executor(
                    self._executor,
                    lambda: coll.delete(ids=ids)
                )
                return len(ids)

        return 0

    async def get_all(
        self,
        collection: str
    ) -> List[Tuple[MemoryDocument, Optional[List[float]]]]:
        """
        Get all documents from a collection.

        Args:
            collection: Collection name

        Returns:
            List of (document, embedding) tuples
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        coll = self._collections.get(collection)
        if not coll:
            return []

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                self._executor,
                lambda: coll.get(include=["documents", "metadatas", "embeddings"])
            )

            documents = []
            if results and results.get("ids"):
                for i, doc_id in enumerate(results["ids"]):
                    doc = MemoryDocument(
                        id=doc_id,
                        content=results["documents"][i] if results.get("documents") else "",
                        metadata=results["metadatas"][i] if results.get("metadatas") else {}
                    )
                    embedding = None
                    embeddings = results.get("embeddings")
                    if embeddings is not None and len(embeddings) > i:
                        embedding = embeddings[i]
                    documents.append((doc, embedding))

            return documents

        except Exception as e:
            logger.warning(f"get_all error in {collection}: {e}")
            return []

    async def get(
        self,
        doc_id: str,
        collection: str
    ) -> Optional[MemoryDocument]:
        """
        Get a specific document by ID.

        Args:
            doc_id: Document ID
            collection: Collection name

        Returns:
            MemoryDocument or None if not found
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        coll = self._collections.get(collection)
        if not coll:
            return None

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                self._executor,
                lambda: coll.get(ids=[doc_id], include=["documents", "metadatas"])
            )

            if results and results.get("ids") and len(results["ids"]) > 0:
                return MemoryDocument(
                    id=results["ids"][0],
                    content=results["documents"][0] if results.get("documents") else "",
                    metadata=results["metadatas"][0] if results.get("metadatas") else {}
                )
            return None

        except Exception as e:
            logger.warning(f"get error for {doc_id}: {e}")
            return None

    async def clear_collection(self, collection: str) -> int:
        """
        Clear all documents from a collection.

        Args:
            collection: Collection name

        Returns:
            Number of deleted documents
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        coll = self._collections.get(collection)
        if not coll:
            return 0

        loop = asyncio.get_event_loop()
        try:
            # Get all IDs
            results = await loop.run_in_executor(
                self._executor,
                lambda: coll.get(include=[])
            )

            if results and results.get("ids"):
                ids = results["ids"]
                await loop.run_in_executor(
                    self._executor,
                    lambda: coll.delete(ids=ids)
                )
                return len(ids)

            return 0

        except Exception as e:
            logger.warning(f"clear_collection error in {collection}: {e}")
            return 0

    async def add_with_embedding(
        self,
        doc_id: str,
        content: str,
        collection: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: List[float] = None
    ) -> str:
        """
        Add a document with a pre-computed embedding.

        Args:
            doc_id: Document ID
            content: Text content
            collection: Target collection name
            metadata: Optional metadata dict
            embedding: Pre-computed embedding vector

        Returns:
            Document ID
        """
        await self._ensure_initialized()
        self.last_access = time.time()

        # Prepare metadata
        meta = metadata or {}
        meta["updated_at"] = datetime.now().isoformat()
        meta["collection"] = collection

        coll = self._collections.get(collection)
        if not coll:
            raise ValueError(f"Unknown collection: {collection}")

        loop = asyncio.get_event_loop()

        if embedding is not None:
            await loop.run_in_executor(
                self._executor,
                lambda: coll.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[meta]
                )
            )
        else:
            # Generate embedding if not provided
            embedding_result = await embedding_engine.encode_single(content)
            await loop.run_in_executor(
                self._executor,
                lambda: coll.add(
                    ids=[doc_id],
                    embeddings=[embedding_result],
                    documents=[content],
                    metadatas=[meta]
                )
            )

        return doc_id

    async def get_stats(self) -> MemoryStats:
        """Get statistics about this project's memory."""
        await self._ensure_initialized()

        collections_stats = {}
        total = 0

        for name, coll in self._collections.items():
            try:
                count = coll.count()
                collections_stats[name] = count
                total += count
            except Exception:
                collections_stats[name] = 0

        # Load metadata (v5.3.1: async file I/O if available)
        initialized_at = None
        last_update = None
        if self._metadata_path.exists():
            try:
                if AIOFILES_AVAILABLE:
                    async with aiofiles.open(self._metadata_path, 'r') as f:
                        content = await f.read()
                        meta = json.loads(content)
                else:
                    with open(self._metadata_path) as f:
                        meta = json.load(f)
                initialized_at = meta.get("initialized_at")
                last_update = meta.get("last_update")
            except Exception:
                pass

        # Calculate storage size
        storage_size = 0.0
        try:
            for f in self.path.rglob("*"):
                if f.is_file():
                    storage_size += f.stat().st_size
            storage_size /= (1024 * 1024)  # Convert to MB
        except Exception:
            pass

        return MemoryStats(
            project_id=self.project_id,
            initialized_at=initialized_at,
            last_update=last_update,
            collections=collections_stats,
            total_documents=total,
            storage_size_mb=round(storage_size, 2)
        )

    async def save_metadata(self, **kwargs):
        """Save metadata about this memory (v5.3.1: async file I/O)."""
        existing = {}
        if self._metadata_path.exists():
            try:
                if AIOFILES_AVAILABLE:
                    async with aiofiles.open(self._metadata_path, 'r') as f:
                        content = await f.read()
                        existing = json.loads(content)
                else:
                    with open(self._metadata_path) as f:
                        existing = json.load(f)
            except Exception:
                pass

        existing.update(kwargs)
        existing["last_update"] = datetime.now().isoformat()

        if AIOFILES_AVAILABLE:
            async with aiofiles.open(self._metadata_path, 'w') as f:
                await f.write(json.dumps(existing, indent=2))
        else:
            with open(self._metadata_path, "w") as f:
                json.dump(existing, f, indent=2)

    async def get_metadata(self) -> dict:
        """Read stored metadata from metadata.json (v6.8)."""
        if not self._metadata_path.exists():
            return {}
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(self._metadata_path, 'r') as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                with open(self._metadata_path) as f:
                    return json.load(f)
        except Exception:
            return {}

    async def close(self):
        """Release resources properly (v5.3 fix)."""
        # Persist ChromaDB data before closing
        if self._client is not None:
            try:
                # ChromaDB PersistentClient auto-persists, but we ensure cleanup
                self._client = None
            except Exception as e:
                logger.warning(f"Error closing ChromaDB client: {e}")

        self._collections = {}
        self._initialized = False

        # Shutdown executor with wait=True to complete pending tasks
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=True, cancel_futures=False)
            except Exception as e:
                logger.warning(f"Error shutting down executor: {e}")


class RelevanceScorer:
    """Calculates relevance scores for memory results."""

    @classmethod
    def score(
        cls,
        document: MemoryDocument,
        semantic_distance: float,
        keywords: List[str],
        task_type: str = "general",
        collection: str = "unknown"
    ) -> ScoredResult:
        """
        Calculate final relevance score.

        Args:
            document: The memory document
            semantic_distance: ChromaDB distance (0 = identical, 2 = opposite)
            keywords: Extracted keywords from scope description
            task_type: Type of task (bug, feature, database, etc.)
            collection: Source collection name
        """
        # 1. Semantic score (convert distance to similarity)
        # ChromaDB cosine distance: 0 = same, 2 = opposite
        semantic_score = 1.0 - (semantic_distance / 2.0)

        # 2. Keyword score
        doc_text = f"{document.content} {document.metadata.get('name', '')}".lower()
        matched = sum(1 for kw in keywords if kw in doc_text)
        keyword_score = matched / max(len(keywords), 1)

        # 3. Recency score
        updated_at = document.metadata.get("updated_at", "")
        recency_score = cls._calculate_recency(updated_at)

        # 4. Type bonus
        doc_type = document.metadata.get("type", "")
        type_bonus = TYPE_BONUSES.get(task_type, {}).get(doc_type, 0)

        # 5. Calculate final score
        final_score = (
            SCORING_WEIGHTS["semantic"] * semantic_score +
            SCORING_WEIGHTS["keyword"] * keyword_score +
            SCORING_WEIGHTS["recency"] * recency_score +
            type_bonus
        )

        # Normalize to 0-1
        final_score = min(1.0, max(0.0, final_score))

        return ScoredResult(
            document=document,
            semantic_score=semantic_score,
            keyword_score=keyword_score,
            recency_score=recency_score,
            final_score=final_score,
            collection=collection
        )

    @staticmethod
    def _calculate_recency(updated_at: str) -> float:
        """
        Calculate recency score based on timestamp.

        Last 24h: 1.0
        Last week: 0.8
        Last month: 0.5
        Older: 0.2
        """
        if not updated_at:
            return 0.5  # Default for unknown

        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age = datetime.now() - updated.replace(tzinfo=None)

            if age.days < 1:
                return 1.0
            elif age.days < 7:
                return 0.8
            elif age.days < 30:
                return 0.5
            else:
                return 0.2
        except Exception:
            return 0.5


class ContextFormatter:
    """Formats memory results for context injection."""

    MAX_RESULTS_PER_CATEGORY = 3

    CATEGORY_ICONS = {
        "authentication": "🔐",
        "database": "📊",
        "api": "🌐",
        "config": "⚙️",
        "test": "🧪",
        "model": "📦",
        "view": "🖼️",
        "controller": "🎮",
        "service": "⚡",
        "util": "🔧",
        "recent": "🕐",
        "other": "📄",
    }

    @classmethod
    def format(
        cls,
        results: List[ScoredResult],
        scope_description: str,
        max_tokens: int = 500
    ) -> str:
        """
        Format results for context injection.

        Args:
            results: Sorted list of ScoredResults
            scope_description: Original description
            max_tokens: Maximum token count for context

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        # Group by categories
        categories = cls._categorize_results(results)

        # Build output
        lines = ["", "📚 **Relevanter Kontext aus Memory:**", ""]

        for category, items in categories.items():
            if not items:
                continue

            icon = cls.CATEGORY_ICONS.get(category, "📄")
            lines.append(f"{icon} **{category.title()}:**")

            for result in items[:cls.MAX_RESULTS_PER_CATEGORY]:
                doc = result.document
                path = doc.metadata.get("path", doc.metadata.get("name", "unknown"))
                lines.append(f"• {path}")

                summary = cls._get_summary(doc)
                if summary:
                    lines.append(f"  └─ {summary}")

            lines.append("")  # Blank line between categories

        # Add recent changes if relevant
        recent = cls._get_recent_changes(results)
        if recent:
            lines.append("💡 **Letzte relevante Änderungen:**")
            for change in recent[:2]:
                lines.append(f"• {change}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def _categorize_results(
        cls,
        results: List[ScoredResult]
    ) -> Dict[str, List[ScoredResult]]:
        """Group results by categories."""
        categories: Dict[str, List[ScoredResult]] = defaultdict(list)

        for result in results:
            doc_type = result.document.metadata.get("type", "other")
            path = result.document.metadata.get("path", "").lower()

            # Determine category
            if "auth" in path or doc_type == "auth":
                categories["authentication"].append(result)
            elif doc_type == "table" or "migration" in path:
                categories["database"].append(result)
            elif "controller" in path or doc_type == "controller":
                categories["controller"].append(result)
            elif "model" in path or doc_type == "model":
                categories["model"].append(result)
            elif "config" in path or doc_type == "config":
                categories["config"].append(result)
            elif "test" in path or doc_type == "test":
                categories["test"].append(result)
            elif "api" in path or "route" in path:
                categories["api"].append(result)
            else:
                categories["other"].append(result)

        # Remove "other" if too large
        if len(categories.get("other", [])) > 5:
            del categories["other"]

        return dict(categories)

    @classmethod
    def _get_summary(cls, doc: MemoryDocument) -> str:
        """Create a short summary of the document."""
        metadata = doc.metadata

        if metadata.get("type") == "function":
            params = metadata.get("params", [])
            returns = metadata.get("returns", "void")
            name = metadata.get("name", "?")
            return f"{name}({', '.join(params[:3])}) → {returns}"

        elif metadata.get("type") == "table":
            columns = metadata.get("columns", [])[:4]
            more = "..." if len(metadata.get("columns", [])) > 4 else ""
            return f"Columns: {', '.join(columns)}{more}"

        elif metadata.get("type") == "file":
            functions = metadata.get("functions", [])[:3]
            if functions:
                return f"Functions: {', '.join(functions)}"

        # Fallback: First sentence
        content = doc.content
        if ". " in content:
            return content.split(". ")[0] + "."
        return content[:80] + "..." if len(content) > 80 else content

    @classmethod
    def _get_recent_changes(cls, results: List[ScoredResult]) -> List[str]:
        """Find recently changed relevant files."""
        recent = []

        for result in results:
            updated = result.document.metadata.get("updated_at", "")
            if result.recency_score >= 0.8 and updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    age = datetime.now() - dt.replace(tzinfo=None)
                    if age.days < 7:
                        path = result.document.metadata.get("path", "?")
                        ago = f"{age.days}d ago" if age.days > 0 else "today"
                        recent.append(f"{ago}: {path}")
                except Exception:
                    pass

        return recent


class ProjectMemoryManager:
    """
    Manages memory instances with strict project isolation.

    GUARANTEES:
    - Each project has its own ChromaDB instance
    - No cross-project queries possible
    - Automatic cleanup of inactive instances
    """

    def __init__(self):
        self._instances: Dict[str, ProjectMemory] = {}
        self._lock = asyncio.Lock()

    async def get_memory(self, project_id: str, working_dir: Optional[str] = None) -> ProjectMemory:
        """
        Get or create memory instance for a project.

        IMPORTANT: Each project_id gets its own instance!

        Args:
            project_id: The project identifier
            working_dir: Optional working directory for validation

        Returns:
            ProjectMemory instance
        """
        # Validate isolation if working_dir provided
        if working_dir:
            validate_project_isolation(project_id, working_dir)

        async with self._lock:
            if project_id not in self._instances:
                # Create new instance
                memory_path = MEMORY_HOME / project_id
                memory_path.mkdir(parents=True, exist_ok=True)

                self._instances[project_id] = ProjectMemory(
                    project_id=project_id,
                    path=memory_path
                )

            return self._instances[project_id]

    async def memory_exists(self, project_id: str) -> bool:
        """Check if memory exists for a project."""
        memory_path = MEMORY_HOME / project_id
        return memory_path.exists() and (memory_path / "chroma.sqlite3").exists()

    async def cleanup_inactive(self, max_age_seconds: int = 3600):
        """Remove inactive memory instances from RAM (v5.3.1: safe iteration)."""
        async with self._lock:
            now = time.time()
            # v5.3.1: Create copy of items to prevent RuntimeError during iteration
            to_remove = [
                pid for pid, mem in list(self._instances.items())
                if (now - mem.last_access) > max_age_seconds
            ]
            for pid in to_remove:
                await self._instances[pid].close()
                del self._instances[pid]
                logger.info(f"Cleaned up inactive memory: {pid}")

    async def list_projects(self) -> List[str]:
        """List all projects with memory."""
        projects = []
        try:
            for path in MEMORY_HOME.iterdir():
                if path.is_dir() and (path / "metadata.json").exists():
                    projects.append(path.name)
        except Exception:
            pass
        return projects


class SmartContextInjector:
    """
    Smart Context Injection for set_scope.

    Automatically retrieves relevant context from memory
    based on the task description.
    """

    # v5.3.1: Cache configuration
    CACHE_MAX_SIZE = 100
    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, memory_manager: ProjectMemoryManager):
        self.memory_manager = memory_manager
        # v5.3.1: Use bounded TTLLRUCache instead of unbounded dict
        self._cache: TTLLRUCache[str] = TTLLRUCache(
            maxsize=self.CACHE_MAX_SIZE,
            ttl_seconds=self.CACHE_TTL_SECONDS
        )

    async def get_context(
        self,
        project_id: str,
        description: str,
        max_results: int = 8
    ) -> str:
        """
        Get relevant context for a task description.

        Args:
            project_id: The project identifier
            description: Task description
            max_results: Maximum results to include

        Returns:
            Formatted context string
        """
        # Check if memory exists
        if not await self.memory_manager.memory_exists(project_id):
            return self._get_init_hint()

        # Check cache (v5.3.1: TTLLRUCache handles TTL automatically)
        cache_key = f"{project_id}:{description[:50]}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Get memory instance
        memory = await self.memory_manager.get_memory(project_id)

        # Extract and expand keywords
        original_keywords, expanded_keywords = KeywordExtractor.extract_and_expand(description)

        # Detect task type
        task_type = detect_task_type(description)

        # Build query text
        query_text = " ".join(original_keywords + [description])

        # Query memory
        raw_results = await memory.query(
            query_text=query_text,
            collection="all",
            n_results=max_results
        )

        if not raw_results:
            return "\n📚 Memory: Keine stark relevanten Einträge gefunden."

        # Score results
        scored_results = []
        for doc, distance in raw_results:
            scored = RelevanceScorer.score(
                document=doc,
                semantic_distance=distance,
                keywords=expanded_keywords,
                task_type=task_type,
                collection=doc.metadata.get("_collection", "unknown")
            )
            scored_results.append(scored)

        # Sort by score
        scored_results.sort(key=lambda x: x.final_score, reverse=True)

        # Filter by relevance threshold
        relevant_results = [r for r in scored_results if r.final_score > 0.5]

        if not relevant_results:
            return "\n📚 Memory: Keine stark relevanten Einträge gefunden."

        # Format context
        context = ContextFormatter.format(
            results=relevant_results[:max_results],
            scope_description=description
        )

        # Cache result (v5.3.1: TTLLRUCache.set handles timestamp)
        self._cache.set(cache_key, context)

        return context

    def _get_init_hint(self) -> str:
        """Get hint for initializing memory."""
        return """

💡 **Long-Term Memory verfügbar!**
   Führe `chainguard_memory_init()` aus für:
   - Automatischen Kontext bei jedem Task
   - Semantische Code-Suche
   - Persistentes Projekt-Wissen
"""

    def invalidate_cache(self, project_id: str):
        """Invalidate cache for a project (v5.3.1: TTLLRUCache API)."""
        prefix = f"{project_id}:"
        keys_to_remove = [k for k, _ in self._cache.items() if k.startswith(prefix)]
        for key in keys_to_remove:
            self._cache.invalidate(key)

    async def get_memory_health(self, project_id: str) -> dict:
        """
        Get memory health status for a project (v6.6).

        Returns:
            dict with keys: initialized, total_docs, last_updated, stale, days_since_update
        """
        defaults = {
            "initialized": False,
            "total_docs": 0,
            "last_updated": None,
            "stale": False,
            "days_since_update": -1,
        }

        try:
            if not await self.memory_manager.memory_exists(project_id):
                return defaults

            memory = await self.memory_manager.get_memory(project_id)
            stats = await memory.get_stats()

            last_updated = stats.last_update
            days_since = -1
            stale = False

            if last_updated:
                try:
                    dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    age = datetime.now() - dt.replace(tzinfo=None)
                    days_since = age.days
                    stale = days_since > STALE_MEMORY_THRESHOLD_DAYS
                except Exception:
                    pass

            return {
                "initialized": True,
                "total_docs": stats.total_documents,
                "last_updated": last_updated,
                "stale": stale,
                "days_since_update": days_since,
            }

        except Exception as e:
            logger.warning(f"get_memory_health failed: {e}")
            return defaults


# Global instances
memory_manager = ProjectMemoryManager()
context_injector = SmartContextInjector(memory_manager)


def should_index_file(file_path: str) -> bool:
    """
    Check if a file should be indexed.

    Excludes:
    - Sensitive files (.env, credentials, secrets, etc.)
    - Non-source directories (node_modules, vendor, dist, build, etc.)
    - Lock files (package-lock.json, yarn.lock, composer.lock)
    """
    path_lower = file_path.lower()

    # Check sensitive patterns
    if any(pattern in path_lower for pattern in SENSITIVE_PATTERNS):
        return False

    # Check excluded directories
    if any(excl in path_lower for excl in EXCLUDED_DIRECTORIES):
        return False

    return True
