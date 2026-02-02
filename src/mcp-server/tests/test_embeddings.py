"""
Tests for chainguard.embeddings module.

Tests KeywordExtractor and basic EmbeddingEngine functionality.
Note: Full embedding tests require sentence-transformers which may not be installed.
"""

import pytest


class TestKeywordExtractor:
    """Tests for KeywordExtractor class."""

    def test_import_extractor(self):
        """Test that KeywordExtractor can be imported."""
        from chainguard.embeddings import KeywordExtractor
        assert KeywordExtractor is not None

    def test_extract_basic(self):
        """Test basic keyword extraction."""
        from chainguard.embeddings import KeywordExtractor

        text = "Fix the login bug in authentication"
        keywords = KeywordExtractor.extract(text)

        assert isinstance(keywords, list)
        assert "login" in keywords
        assert "bug" in keywords
        assert "authentication" in keywords
        # Stop words should be removed
        assert "the" not in keywords
        assert "in" not in keywords

    def test_extract_with_special_chars(self):
        """Test extraction with special characters."""
        from chainguard.embeddings import KeywordExtractor

        text = "Login-Bug fixen! Test@User #hashtag"
        keywords = KeywordExtractor.extract(text)

        assert "login" in keywords
        assert "bug" in keywords
        assert "fixen" in keywords

    def test_extract_german(self):
        """Test extraction of German text."""
        from chainguard.embeddings import KeywordExtractor

        text = "Benutzer-Authentifizierung und Datenbank-Migration"
        keywords = KeywordExtractor.extract(text)

        assert "benutzer" in keywords
        assert "authentifizierung" in keywords
        assert "datenbank" in keywords
        assert "migration" in keywords
        # German stop words removed
        assert "und" not in keywords

    def test_extract_removes_short_words(self):
        """Test that short words (<=2 chars) are removed."""
        from chainguard.embeddings import KeywordExtractor

        text = "I am a go at it"
        keywords = KeywordExtractor.extract(text)

        # All words are <= 2 chars or stop words
        assert len(keywords) == 0

    def test_expand_keywords(self):
        """Test keyword expansion with synonyms."""
        from chainguard.embeddings import KeywordExtractor

        keywords = ["login", "bug"]
        expanded = KeywordExtractor.expand(keywords)

        assert isinstance(expanded, list)
        # Original keywords preserved
        assert "login" in expanded
        assert "bug" in expanded
        # Related terms added
        assert "auth" in expanded or "authentication" in expanded
        assert "fix" in expanded or "error" in expanded

    def test_expand_unknown_keyword(self):
        """Test expansion of unknown keyword (no expansion)."""
        from chainguard.embeddings import KeywordExtractor

        keywords = ["foobar", "unknown"]
        expanded = KeywordExtractor.expand(keywords)

        # Only original keywords returned
        assert "foobar" in expanded
        assert "unknown" in expanded
        assert len(expanded) == 2

    def test_extract_and_expand(self):
        """Test combined extract and expand."""
        from chainguard.embeddings import KeywordExtractor

        text = "Login-Bug im User-Management"
        original, expanded = KeywordExtractor.extract_and_expand(text)

        assert isinstance(original, list)
        assert isinstance(expanded, list)
        assert len(expanded) >= len(original)
        assert "login" in original
        assert "bug" in original
        # Expanded should include related terms
        assert len(expanded) > len(original)

    def test_empty_input(self):
        """Test extraction from empty string."""
        from chainguard.embeddings import KeywordExtractor

        keywords = KeywordExtractor.extract("")
        assert keywords == []

    def test_stop_words_only(self):
        """Test text with only stop words."""
        from chainguard.embeddings import KeywordExtractor

        text = "the a an in on at to for"
        keywords = KeywordExtractor.extract(text)
        assert keywords == []


class TestDetectTaskType:
    """Tests for detect_task_type function."""

    def test_import(self):
        """Test that detect_task_type can be imported."""
        from chainguard.embeddings import detect_task_type
        assert detect_task_type is not None

    def test_detect_bug(self):
        """Test detection of bug-related tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("Fix the login bug") == "bug"
        assert detect_task_type("Error in user authentication") == "bug"
        assert detect_task_type("Fehler im System beheben") == "bug"
        assert detect_task_type("Issue with session handling") == "bug"

    def test_detect_feature(self):
        """Test detection of feature-related tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("Implement new search feature") == "feature"
        assert detect_task_type("Add dark mode toggle") == "feature"
        assert detect_task_type("Create user profile page") == "feature"
        assert detect_task_type("Neue Funktion implementieren") == "feature"

    def test_detect_database(self):
        """Test detection of database-related tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("database migration erstellen") == "database"
        assert detect_task_type("Update users table schema") == "database"
        assert detect_task_type("sql query optimieren") == "database"
        assert detect_task_type("db backup erstellen") == "database"

    def test_detect_test(self):
        """Test detection of test-related tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("Write test for login") == "test"
        assert detect_task_type("spec file erstellen") == "test"
        assert detect_task_type("unit test for user module") == "test"

    def test_detect_refactor(self):
        """Test detection of refactoring tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("refactor authentication module") == "refactor"
        assert detect_task_type("cleanup old code") == "refactor"
        assert detect_task_type("optimize queries") == "refactor"

    def test_detect_general(self):
        """Test detection of general/unknown tasks."""
        from chainguard.embeddings import detect_task_type

        assert detect_task_type("Random task description") == "general"
        assert detect_task_type("Some other work") == "general"
        assert detect_task_type("") == "general"


class TestEmbeddingConstants:
    """Tests for embedding configuration constants."""

    def test_constants_exist(self):
        """Test that embedding constants are defined."""
        from chainguard.embeddings import (
            DEFAULT_MODEL,
            EMBEDDING_DIMENSIONS,
            MAX_TOKENS
        )

        assert DEFAULT_MODEL == "paraphrase-multilingual-MiniLM-L12-v2"
        assert EMBEDDING_DIMENSIONS == 384
        assert MAX_TOKENS == 256


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_create_result(self):
        """Test creating an EmbeddingResult."""
        from chainguard.embeddings import EmbeddingResult

        result = EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="paraphrase-multilingual-MiniLM-L12-v2",
            dimensions=384,
            count=1
        )

        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.model == "paraphrase-multilingual-MiniLM-L12-v2"
        assert result.dimensions == 384
        assert result.count == 1

    def test_empty_result(self):
        """Test creating an empty EmbeddingResult."""
        from chainguard.embeddings import EmbeddingResult

        result = EmbeddingResult(
            embeddings=[],
            model="paraphrase-multilingual-MiniLM-L12-v2",
            dimensions=384,
            count=0
        )

        assert result.embeddings == []
        assert result.count == 0


class TestEmbeddingEngine:
    """Tests for EmbeddingEngine class (without model loading)."""

    def test_create_engine(self):
        """Test creating an EmbeddingEngine instance."""
        from chainguard.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()
        assert engine is not None
        assert engine.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert engine.is_loaded is False
        assert engine.dimensions == 384

    def test_create_engine_custom_model(self):
        """Test creating engine with custom model name."""
        from chainguard.embeddings import EmbeddingEngine

        engine = EmbeddingEngine(model_name="custom-model")
        assert engine.model_name == "custom-model"
        assert engine.is_loaded is False

    def test_global_engine_exists(self):
        """Test that global embedding_engine instance exists."""
        from chainguard.embeddings import embedding_engine

        assert embedding_engine is not None
        assert embedding_engine.model_name == "paraphrase-multilingual-MiniLM-L12-v2"


# Integration tests (require sentence-transformers)
@pytest.mark.skipif(
    True,  # Change to False to run integration tests locally
    reason="Requires sentence-transformers package"
)
class TestEmbeddingEngineIntegration:
    """Integration tests that require sentence-transformers."""

    @pytest.mark.asyncio
    async def test_encode_single(self):
        """Test encoding a single text."""
        from chainguard.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()
        embedding = await engine.encode_single("Hello world")

        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(v, float) for v in embedding)

    @pytest.mark.asyncio
    async def test_encode_multiple(self):
        """Test encoding multiple texts."""
        from chainguard.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()
        result = await engine.encode(["Hello", "World"])

        assert result.count == 2
        assert len(result.embeddings) == 2
        assert all(len(e) == 384 for e in result.embeddings)

    @pytest.mark.asyncio
    async def test_encode_empty_list(self):
        """Test encoding empty list."""
        from chainguard.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()
        result = await engine.encode([])

        assert result.count == 0
        assert result.embeddings == []
