"""
CHAINGUARD MCP Server - Embeddings Module

Local embedding generation using fastembed (ONNX Runtime).
Falls back to sentence-transformers if fastembed is not installed.
No API calls required - runs completely offline.

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.

Usage:
    from chainguard.embeddings import EmbeddingEngine, embedding_engine

    # Generate embeddings
    embeddings = await embedding_engine.encode(["Hello world", "Code example"])

    # Check if model is loaded
    if embedding_engine.is_loaded:
        ...
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("chainguard.embeddings")

# Model configuration
DEFAULT_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
MAX_TOKENS = 256


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    embeddings: List[List[float]]
    model: str
    dimensions: int
    count: int


class KeywordExtractor:
    """
    Extracts and expands keywords from text for search enhancement.

    Used for Smart Context Injection - expands search queries with
    related terms to improve recall.
    """

    # Synonyms and related terms
    KEYWORD_EXPANSIONS: Dict[str, List[str]] = {
        "login": ["auth", "authentication", "signin", "session", "jwt", "token"],
        "logout": ["signout", "session", "auth"],
        "user": ["account", "profile", "member", "customer"],
        "database": ["db", "sql", "table", "schema", "migration"],
        "api": ["endpoint", "route", "controller", "rest", "request"],
        "bug": ["fix", "error", "issue", "problem", "debug"],
        "feature": ["implement", "add", "create", "new"],
        "test": ["spec", "unit", "integration", "phpunit", "jest", "pytest"],
        "payment": ["stripe", "checkout", "billing", "invoice", "cart"],
        "email": ["mail", "notification", "smtp", "newsletter"],
        "upload": ["file", "image", "storage", "s3", "media"],
        "search": ["query", "find", "filter", "index"],
        "cache": ["redis", "memcached", "store", "ttl"],
        "config": ["settings", "env", "environment", "configuration"],
        "model": ["entity", "orm", "eloquent", "schema"],
        "view": ["template", "blade", "component", "frontend"],
        "controller": ["handler", "action", "endpoint"],
        "middleware": ["filter", "guard", "interceptor"],
        "validation": ["validate", "check", "verify", "sanitize"],
        "security": ["auth", "permission", "role", "access"],
    }

    # Stop words to ignore (English + German)
    STOP_WORDS: Set[str] = {
        # English
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "do", "does", "did", "will", "would", "could", "should", "may",
        "might", "must", "shall", "can", "need", "dare", "ought", "used",
        "this", "that", "these", "those", "it", "its", "they", "their",
        "with", "from", "by", "about", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "again", "further",
        "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "each", "few", "more", "most", "other", "some", "such",
        "no", "nor", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "also", "now", "new", "get", "set", "make",
        # German
        "den", "die", "das", "der", "ein", "eine", "und", "oder", "für",
        "mit", "von", "zu", "auf", "bei", "nach", "aus", "über", "wie",
        "als", "auch", "noch", "nur", "aber", "wenn", "weil", "dass",
        "sich", "ich", "du", "er", "sie", "es", "wir", "ihr", "sein",
        "haben", "werden", "können", "müssen", "sollen", "wollen",
    }

    @classmethod
    def extract(cls, text: str) -> List[str]:
        """
        Extract keywords from text.

        Args:
            text: "Login-Bug fixen und Session-Handling verbessern"

        Returns:
            ["login", "bug", "session", "handling", "verbessern"]
        """
        # Normalize
        text = text.lower()

        # Replace special characters with spaces
        text = re.sub(r'[^a-zäöüß0-9\s]', ' ', text)

        # Tokenize
        words = text.split()

        # Remove stop words and short words
        keywords = [
            w for w in words
            if w not in cls.STOP_WORDS and len(w) > 2
        ]

        return list(set(keywords))

    @classmethod
    def expand(cls, keywords: List[str]) -> List[str]:
        """
        Expand keywords with related terms.

        Args:
            keywords: ["login", "bug"]

        Returns:
            ["login", "bug", "auth", "authentication", "signin",
             "session", "jwt", "token", "fix", "error", "issue"]
        """
        expanded = set(keywords)

        for keyword in keywords:
            if keyword in cls.KEYWORD_EXPANSIONS:
                expanded.update(cls.KEYWORD_EXPANSIONS[keyword])

        return list(expanded)

    @classmethod
    def extract_and_expand(cls, text: str) -> Tuple[List[str], List[str]]:
        """
        Extract and expand keywords in one call.

        Returns:
            (original_keywords, expanded_keywords)
        """
        original = cls.extract(text)
        expanded = cls.expand(original)
        return original, expanded


class EmbeddingEngine:
    """
    Local embedding engine using fastembed (ONNX Runtime).

    Falls back to sentence-transformers if fastembed is not installed.

    Features:
    - Lazy loading (model loaded on first use)
    - Thread-safe async execution
    - Normalized embeddings for cosine similarity
    - Batched processing for efficiency
    - ~1.3 GB less RAM than sentence-transformers/PyTorch
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None
        self._backend: Optional[str] = None  # "fastembed" or "sentence-transformers"
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = asyncio.Lock()
        self._load_error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def dimensions(self) -> int:
        """Get embedding dimensions."""
        return EMBEDDING_DIMENSIONS

    def _load_model_sync(self):
        """Load model synchronously (called in thread pool). Tries fastembed first."""
        # 1. Try fastembed (ONNX Runtime - lightweight)
        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
            self._backend = "fastembed"
            logger.info(f"Loaded embedding model via fastembed: {self.model_name}")
            return
        except ImportError:
            logger.debug("fastembed not available, trying sentence-transformers")
        except Exception as e:
            logger.debug(f"fastembed failed for {self.model_name}: {e}, trying sentence-transformers")

        # 2. Fallback: sentence-transformers (PyTorch - heavier)
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._backend = "sentence-transformers"
            logger.info(f"Loaded embedding model via sentence-transformers: {self.model_name}")
            return
        except ImportError:
            pass
        except Exception as e:
            self._load_error = f"Failed to load model {self.model_name}: {e}"
            logger.error(self._load_error)
            raise

        # Neither available
        self._load_error = (
            "No embedding backend installed. "
            "Run: pip install fastembed numpy"
        )
        logger.error(self._load_error)
        raise ImportError(self._load_error)

    async def _ensure_loaded(self):
        """Ensure model is loaded (lazy loading)."""
        if self._model is None:
            async with self._lock:
                if self._model is None:  # Double-check after acquiring lock
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._executor, self._load_model_sync)

    def _encode_sync(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32
    ) -> List[List[float]]:
        """Encode texts synchronously (called in thread pool)."""
        if self._model is None:
            raise RuntimeError("Model not loaded")

        if self._backend == "fastembed":
            # fastembed API: model.embed() returns a generator of numpy arrays
            embeddings_list = list(self._model.embed(texts, batch_size=batch_size))
            # Each element is already a numpy array; convert to list of lists
            return [emb.tolist() for emb in embeddings_list]
        else:
            # sentence-transformers API
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=normalize,
                batch_size=batch_size,
                show_progress_bar=False
            )
            return embeddings.tolist()

    async def encode(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32
    ) -> EmbeddingResult:
        """
        Generate embeddings for texts.

        Args:
            texts: List of texts to embed
            normalize: Normalize vectors for cosine similarity
            batch_size: Batch size for processing

        Returns:
            EmbeddingResult with embeddings and metadata
        """
        if not texts:
            return EmbeddingResult(
                embeddings=[],
                model=self.model_name,
                dimensions=EMBEDDING_DIMENSIONS,
                count=0
            )

        await self._ensure_loaded()

        # Truncate long texts (model has max token limit)
        truncated_texts = [self._truncate_text(t) for t in texts]

        # Run encoding in thread pool
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            self._executor,
            self._encode_sync,
            truncated_texts,
            normalize,
            batch_size
        )

        return EmbeddingResult(
            embeddings=embeddings,
            model=self.model_name,
            dimensions=EMBEDDING_DIMENSIONS,
            count=len(embeddings)
        )

    async def encode_single(self, text: str, normalize: bool = True) -> List[float]:
        """
        Generate embedding for a single text.

        Convenience method for single queries.

        Returns:
            Single embedding vector
        """
        result = await self.encode([text], normalize=normalize)
        return result.embeddings[0] if result.embeddings else []

    def _truncate_text(self, text: str, max_chars: int = 1000) -> str:
        """
        Truncate text to roughly fit within token limit.

        The model has a 256 token limit. We use character count as
        a rough approximation (1 token ~ 4 chars average).
        """
        if len(text) <= max_chars:
            return text

        # Try to truncate at sentence boundary
        truncated = text[:max_chars]
        last_period = truncated.rfind('. ')
        if last_period > max_chars // 2:
            return truncated[:last_period + 1]

        return truncated + "..."

    async def get_model_info(self) -> Dict[str, any]:
        """Get information about the loaded model."""
        await self._ensure_loaded()

        info = {
            "model": self.model_name,
            "dimensions": EMBEDDING_DIMENSIONS,
            "max_seq_length": MAX_TOKENS,
            "loaded": self.is_loaded,
            "backend": self._backend,
        }

        # Try to get actual dimensions from the model
        if self._backend == "sentence-transformers":
            try:
                info["dimensions"] = self._model.get_sentence_embedding_dimension()
                info["max_seq_length"] = getattr(self._model, 'max_seq_length', MAX_TOKENS)
            except Exception:
                pass

        return info

    def close(self):
        """Release resources properly (v5.3 fix)."""
        self._model = None
        self._backend = None
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=True, cancel_futures=False)
            except Exception as e:
                logger.warning(f"Error shutting down embedding executor: {e}")


# Global embedding engine instance
embedding_engine = EmbeddingEngine()


def detect_task_type(description: str) -> str:
    """
    Detect task type from description for relevance scoring.

    Used by Smart Context Injection to apply type-specific bonuses.

    Returns: "bug", "feature", "database", "test", "refactor", or "general"
    """
    description = description.lower()

    if any(w in description for w in ["bug", "fix", "fehler", "error", "issue", "broken"]):
        return "bug"
    elif any(w in description for w in ["feature", "implement", "add", "neu", "create", "build"]):
        return "feature"
    elif any(w in description for w in ["database", "db", "migration", "table", "schema", "sql"]):
        return "database"
    elif any(w in description for w in ["test", "spec", "unit", "integration", "e2e"]):
        return "test"
    elif any(w in description for w in ["refactor", "cleanup", "optimize", "improve", "restructure"]):
        return "refactor"
    else:
        return "general"
