"""
CHAINGUARD MCP Server v6.0.0

A high-performance MCP server for tracking development tasks,
validating code syntax, and managing project state.

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.

v6.0.0 Changes:
- XML Response System: Structured XML responses for better Claude comprehension
- Based on research showing +56% accuracy improvement with XML vs JSON
- Feature flag XML_RESPONSES_ENABLED for gradual rollout
- New module: xml_response.py with XMLResponse class and convenience functions

v5.3.0 Changes:
- AST Code Analysis: tree-sitter based code structure extraction
- Architecture Detection: Automatic pattern detection (MVC, Clean, Layered, etc.)
- Framework Detection: Laravel, Django, React, Vue, and more
- Memory Export/Import: Portable JSON/JSONL format for backup and transfer
- New tools: chainguard_analyze_code, chainguard_detect_architecture,
  chainguard_memory_export, chainguard_memory_import, chainguard_list_exports

v5.2.0 Changes:
- Auto-Update Memory: Files are automatically re-indexed when tracked
- Session Consolidation: Learnings from sessions are persisted at finish()
- Proactive Hints: Similar past tasks shown at set_scope
- Non-blocking memory updates for better performance

v5.1.0 Changes:
- Long-Term Memory System: Persistent project knowledge with semantic search
- ChromaDB vector database for embeddings storage
- sentence-transformers (all-MiniLM-L6-v2) for offline embeddings
- Smart Context Injection at set_scope
- New tools: chainguard_memory_init, chainguard_memory_query, chainguard_memory_update, chainguard_memory_status

v5.0.0 Changes:
- Task Mode System: Multi-mode architecture (programming, content, devops, research, generic)
- Mode-specific validation and features
- New mode-specific tools for content, devops, and research workflows

v4.12.0 Changes:
- Database Inspector: Live schema inspection for accurate SQL queries
- MySQL, PostgreSQL, SQLite support
- TTL-cached schema (5 min) to avoid repeated queries
- New tools: chainguard_db_connect, chainguard_db_schema, chainguard_db_table, chainguard_db_disconnect

v4.11.0 Changes:
- Error Memory System: Automatic logging of all changes per scope
- Error Index: Fast lookup of similar errors with known fixes
- Auto-Suggest: When errors occur, suggests fixes from past experience
- New tools: chainguard_recall, chainguard_history, chainguard_learn

v4.10.0 Changes:
- Test Runner: Technology-agnostic test execution (PHPUnit, Jest, pytest, etc.)
- Auto-detection of test framework output
- Test results tracking in project state

v4.8.0 Changes:
- Handler-Registry Pattern for testable, maintainable handlers
- TTL-LRU Cache for memory-bounded caching with expiration
- Full async I/O for JSON validation
- Async ChecklistRunner with parallel execution
- Memory-safe HTTP session management

Modular Architecture:
- config.py: Constants, Enums, Configuration
- cache.py: LRU Cache, TTL-LRU Cache, Async File Locks, Git Cache
- validators.py: Syntax validation (PHP, JS, JSON, Python, TS)
- http_session.py: HTTP session management for testing
- test_runner.py: Test execution and output parsing (v4.10)
- history.py: Error Memory System (v4.11)
- utils.py: Path sanitization utilities
- models.py: Data models (ScopeDefinition, ProjectState)
- project_manager.py: Project state management
- analyzers.py: Code analysis and impact analysis
- checklist.py: Secure async checklist execution
- tools.py: MCP tool definitions
- handlers.py: Handler-Registry with decorated tool handlers
- db_inspector.py: Database schema inspection (v4.12)
- memory.py: Long-Term Memory with ChromaDB (v5.1)
- embeddings.py: Embedding Engine (v5.1)
- ast_analyzer.py: AST Code Analysis (v5.3)
- architecture.py: Architecture Detection (v5.3)
- memory_export.py: Memory Export/Import (v5.3)
- server.py: Main MCP server

Usage:
    python -m chainguard

Or import components:
    from chainguard import project_manager, SyntaxValidator, TestRunner, HistoryManager
"""

from .config import (
    VERSION,
    Phase,
    ValidationStatus,
    CONFIG,
    CHAINGUARD_HOME,
    XML_RESPONSES_ENABLED,
    logger
)

# XML Response System (v6.0)
from .xml_response import (
    XMLResponse,
    ResponseStatus,
    xml_response,
    xml_success,
    xml_error,
    xml_warning,
    xml_info,
    xml_blocked,
    build_context,
    is_valid_xml,
    parse_xml_response
)

from .models import (
    ScopeDefinition,
    ProjectState
)

from .project_manager import (
    ProjectManager,
    project_manager
)

from .validators import SyntaxValidator
from .checklist import ChecklistRunner
from .analyzers import CodeAnalyzer, ImpactAnalyzer
from .http_session import HTTPSessionManager, http_session_manager
from .utils import sanitize_path, is_path_safe
from .cache import LRUCache, TTLLRUCache, AsyncFileLock, GitCache, git_cache
from .handlers import HandlerRegistry
from .test_runner import TestRunner, TestConfig, TestResult
from .history import HistoryManager, HistoryEntry, ErrorEntry, format_auto_suggest
from .db_inspector import DBInspector, DBConfig, get_inspector, clear_inspector

# Memory imports are optional (require 'chromadb' and 'sentence-transformers' packages)
try:
    from .memory import (
        ProjectMemoryManager, ProjectMemory, memory_manager,
        SmartContextInjector, context_injector,
        get_project_id, MemoryDocument, ScoredResult, MemoryStats,
        RelevanceScorer, ContextFormatter
    )
    from .embeddings import (
        EmbeddingEngine, embedding_engine,
        KeywordExtractor, EmbeddingResult,
        EMBEDDING_DIMENSIONS, DEFAULT_MODEL
    )
    _HAS_MEMORY = True
except ImportError:
    ProjectMemoryManager = None
    ProjectMemory = None
    memory_manager = None
    SmartContextInjector = None
    context_injector = None
    get_project_id = None
    MemoryDocument = None
    ScoredResult = None
    MemoryStats = None
    RelevanceScorer = None
    ContextFormatter = None
    EmbeddingEngine = None
    embedding_engine = None
    KeywordExtractor = None
    EmbeddingResult = None
    EMBEDDING_DIMENSIONS = None
    DEFAULT_MODEL = None
    _HAS_MEMORY = False

# AST Analyzer imports (no extra dependencies, always available)
try:
    from .ast_analyzer import (
        ASTAnalyzer, ast_analyzer,
        CodeSymbol, FileAnalysis, FileRelation,
        SymbolType, RelationType
    )
    _HAS_AST = True
except ImportError:
    ASTAnalyzer = None
    ast_analyzer = None
    CodeSymbol = None
    FileAnalysis = None
    FileRelation = None
    SymbolType = None
    RelationType = None
    _HAS_AST = False

# Architecture Detector imports (no extra dependencies)
try:
    from .architecture import (
        ArchitectureDetector, architecture_detector,
        ArchitecturePattern, FrameworkType,
        ArchitectureAnalysis
    )
    _HAS_ARCH = True
except ImportError:
    ArchitectureDetector = None
    architecture_detector = None
    ArchitecturePattern = None
    FrameworkType = None
    ArchitectureAnalysis = None
    _HAS_ARCH = False

# Memory Export/Import imports (no extra dependencies)
try:
    from .memory_export import (
        MemoryExporter, MemoryImporter,
        memory_exporter, memory_importer,
        ExportResult, ImportResult,
        ExportMetadata, ExportDocument,
        list_exports
    )
    _HAS_EXPORT = True
except ImportError:
    MemoryExporter = None
    MemoryImporter = None
    memory_exporter = None
    memory_importer = None
    ExportResult = None
    ImportResult = None
    ExportMetadata = None
    ExportDocument = None
    list_exports = None
    _HAS_EXPORT = False

# Code Summarizer imports (v5.4 - no extra dependencies)
try:
    from .code_summarizer import (
        CodeSummarizer, code_summarizer,
        FileSummary, FunctionInfo, ClassInfo
    )
    _HAS_SUMMARIZER = True
except ImportError:
    CodeSummarizer = None
    code_summarizer = None
    FileSummary = None
    FunctionInfo = None
    ClassInfo = None
    _HAS_SUMMARIZER = False

# Server imports are optional (require 'mcp' package)
# Import explicitly when needed: from chainguard.server import main, run, server
try:
    from .server import main, run, server
    _HAS_SERVER = True
except (ImportError, SystemExit):
    main = None
    run = None
    server = None
    _HAS_SERVER = False

__version__ = VERSION
__all__ = [
    # Version
    "VERSION",
    "__version__",

    # Enums
    "Phase",
    "ValidationStatus",
    "ResponseStatus",

    # Config
    "CONFIG",
    "CHAINGUARD_HOME",
    "XML_RESPONSES_ENABLED",
    "logger",

    # XML Response System (v6.0)
    "XMLResponse",
    "xml_response",
    "xml_success",
    "xml_error",
    "xml_warning",
    "xml_info",
    "xml_blocked",
    "build_context",
    "is_valid_xml",
    "parse_xml_response",

    # Models
    "ScopeDefinition",
    "ProjectState",

    # Managers
    "ProjectManager",
    "project_manager",
    "HTTPSessionManager",
    "http_session_manager",

    # Validators & Analyzers
    "SyntaxValidator",
    "ChecklistRunner",
    "CodeAnalyzer",
    "ImpactAnalyzer",

    # Utilities
    "sanitize_path",
    "is_path_safe",

    # Cache
    "LRUCache",
    "TTLLRUCache",
    "AsyncFileLock",
    "GitCache",
    "git_cache",

    # Handlers
    "HandlerRegistry",

    # Test Runner (v4.10)
    "TestRunner",
    "TestConfig",
    "TestResult",

    # Error Memory / History (v4.11)
    "HistoryManager",
    "HistoryEntry",
    "ErrorEntry",
    "format_auto_suggest",

    # Database Inspector (v4.12)
    "DBInspector",
    "DBConfig",
    "get_inspector",
    "clear_inspector",

    # Long-Term Memory (v5.1)
    "ProjectMemoryManager",
    "ProjectMemory",
    "memory_manager",
    "SmartContextInjector",
    "context_injector",
    "get_project_id",
    "MemoryDocument",
    "ScoredResult",
    "MemoryStats",
    "RelevanceScorer",
    "ContextFormatter",

    # Embeddings (v5.1)
    "EmbeddingEngine",
    "embedding_engine",
    "KeywordExtractor",
    "EmbeddingResult",
    "EMBEDDING_DIMENSIONS",
    "DEFAULT_MODEL",

    # AST Analysis (v5.3)
    "ASTAnalyzer",
    "ast_analyzer",
    "CodeSymbol",
    "FileAnalysis",
    "SymbolType",

    # Architecture Detection (v5.3)
    "ArchitectureDetector",
    "architecture_detector",
    "ArchitecturePattern",
    "FrameworkType",
    "ArchitectureAnalysis",

    # Memory Export/Import (v5.3)
    "MemoryExporter",
    "MemoryImporter",
    "memory_exporter",
    "memory_importer",
    "ExportResult",
    "ImportResult",

    # Code Summarizer (v5.4)
    "CodeSummarizer",
    "code_summarizer",
    "FileSummary",
    "FunctionInfo",
    "ClassInfo",

    # Server
    "main",
    "run",
    "server",
]
