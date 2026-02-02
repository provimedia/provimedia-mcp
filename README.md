# Chainguard - MCP Server for Claude Code

[![License: Polyform Noncommercial](https://img.shields.io/badge/License-Polyform%20NC-blue.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

**Chainguard** is a Model Context Protocol (MCP) server that enhances Claude Code with task tracking, syntax validation, long-term memory, and intelligent context management.

## Features

### Core Features
- **Task Scope Management** - Define task boundaries, acceptance criteria, and track progress
- **Automatic Syntax Validation** - PHP, JavaScript, JSON, Python, TypeScript validation on file changes
- **PHPStan Integration (v6.3)** - Static analysis catches runtime errors BEFORE execution (null access, type errors)
- **Smart Context Tracking** - Canary-based context refresh ensures Claude never loses important instructions
- **HTTP Endpoint Testing** - Test endpoints with session support and automatic auth detection

### Long-Term Memory (v5.1+, rewritten in v6.6)
- **Semantic Code Search** - Natural language queries like "Where is authentication handled?"
- **Lightweight Vector Store** - fastembed (ONNX Runtime) + numpy + sqlite3, ~500 MB RAM (replaced ChromaDB)
- **Multilingual Embeddings** - `paraphrase-multilingual-MiniLM-L12-v2` supports 50+ languages including German
- **6 Knowledge Collections** - code_structure, functions, database_schema, architecture, learnings, code_summaries
- **RAG Pipeline** - Hybrid retrieval with semantic similarity (60%), keyword matching (25%), and recency scoring (15%)
- **Automatic Context Injection** - UserPromptSubmit hook injects relevant memory context before every LLM call
- **Auto-Refresh Stale Memory (v6.8)** - Detects memory older than 30 days at `set_scope` and incrementally re-indexes changed files
- **Project Isolation** - Security-validated isolation prevents cross-project access
- **Export/Import** - Portable JSON/JSONL export with optional gzip compression

> **Note:** Long-Term Memory is now enabled by default (`MEMORY_ENABLED=True`) since v6.6 reduced RAM usage from ~3.8 GB to ~500 MB.

### TOON Encoder (v6.0)
- **Token-Oriented Object Notation** - Compact data format for 30-60% token savings
- **Optimized for Arrays** - Best for lists of files, tables, history entries
- **Automatic Formatting** - Tools like `chainguard_projects`, `chainguard_history` use TOON by default

### Hallucination Prevention (v6.1+)
- **Symbol Validation** - Detects hallucinated function/method calls with confidence scoring
- **PHP Builtins Database** - 11,000+ PHP functions/classes/methods from JetBrains phpstorm-stubs (v6.3.1)
- **Slopsquatting Detection** - Catches typosquatted package names (e.g., `requets` instead of `requests`)
- **7-Language Support** - PHP, JavaScript, TypeScript, Python, C#, Go, Rust
- **Package Registry Validation** - Checks imports against composer.json, package.json, requirements.txt
- **Adaptive Mode** - Auto-adjusts sensitivity based on false positive rate

| Mode | Behavior |
|------|----------|
| `OFF` | Disable validation |
| `WARN` | Show warnings only (default) |
| `STRICT` | Block high-confidence issues |
| `ADAPTIVE` | Auto-adjust based on FP rate |

### Deep Logic Summaries (v5.4)
- **Code Understanding** - Extracts human-readable summaries of what code actually does
- **Purpose Inference** - Recognizes patterns from docstrings, comments, and naming conventions
- **Multi-Language Support** - Python, PHP, JavaScript, TypeScript

### Architecture Analysis (v5.3+)
- **Pattern Detection** - MVC, MVVM, Clean Architecture, Hexagonal, Layered, API-first
- **Framework Recognition** - Laravel, Django, React, Vue, Angular, FastAPI, and more
- **AST Analysis** - Tree-sitter based code parsing with regex fallback

### PRD Auto-Detection (v6.7)
- **Automatic PRD Discovery** - Detects PRD/requirements documents at `set_scope`
- **16 Filename Patterns** - `PRD.md`, `REQUIREMENTS.md`, `SPEC.md`, `SPECIFICATION.md`, and more
- **7 Search Directories** - Root, `docs/`, `doc/`, `.claude/`, `requirements/`, `specs/`, `.github/`
- **Workflow Reminders** - Reminds to check PRDs before implementation and update them at `finish`

### Kanban System (v6.5)
- **Persistent Task Management** - Track complex, multi-day projects with a visual board
- **Smart Kanban Suggestion** - Automatically recommends Kanban for ≥5 criteria or complexity keywords
- **7 Column Presets** - default, programming, content, devops, research, agile, simple
- **Custom Columns** - Define task-specific columns via LLM prompt injection
- **Dependency Tracking** - Cards can depend on other cards, blocked cards are highlighted
- **Linked Detail Files** - Each card can have a linked markdown file with detailed instructions
- **Archive System** - Completed cards can be archived for history
- **Graphical Board View** - ASCII art visualization with progress bar

### Task Modes
| Mode | Use Case |
|------|----------|
| `programming` | Code, bugs, features (default) |
| `content` | Books, articles, documentation |
| `devops` | Server admin, CLI tools, WordPress |
| `research` | Analysis, information gathering |
| `generic` | Minimal tracking |

### Feature Flags

Configure in `~/.chainguard/chainguard/config.py`:

| Flag | Default | Description |
|------|---------|-------------|
| `TOON_ENABLED` | `True` | TOON format for array outputs (30-60% token savings) |
| `MEMORY_ENABLED` | `True` | Long-Term Memory (fastembed + numpy + sqlite3, ~500 MB RAM) |
| `AUTO_REFRESH_STALE_MEMORY` | `True` | Auto-refresh memory older than 30 days at `set_scope` |
| `XML_RESPONSES_ENABLED` | `False` | Structured XML responses |
| `PHPSTAN_ENABLED` | `True` | PHPStan static analysis for PHP files |
| `PHPSTAN_LEVEL` | `8` | Analysis level 0-9 (5+ catches null errors, 8 recommended) |

## Installation

### Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/provimedia/chainguard/main/installer/install.sh | bash
```

The installer creates a Python virtual environment at `~/.chainguard/venv/` and installs all dependencies into it (PEP 668 compliant).

### Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/provimedia/chainguard.git
cd chainguard
```

2. Run the installer:
```bash
./installer/install.sh
```

3. Restart Claude Code

### Updating Dependencies

```bash
~/.chainguard/venv/bin/pip install --upgrade fastembed numpy mcp aiofiles aiohttp aiomysql pyyaml
```

### Requirements

- Python 3.9+
- Claude Code CLI
- `fastembed` and `numpy` for Long-Term Memory (installed automatically via venv)
- Optional: `phpstan` for PHP static analysis (catches runtime errors before execution)

## Usage

### Basic Workflow

```python
# 1. Start a task (REQUIRED)
chainguard_set_scope(
    description="Implement user login",
    mode="programming",
    acceptance_criteria=["Login works", "Tests pass"]
)

# 2. Track changes (auto-validates syntax)
chainguard_track(file="src/AuthController.php", ctx="🔗")

# 3. Check status
chainguard_status(ctx="🔗")

# 4. Complete task
chainguard_finish(confirmed=True)
```

### Long-Term Memory

```python
# Initialize memory (once per project, auto-refreshes stale data on set_scope)
chainguard_memory_init()

# Semantic search (supports 50+ languages)
chainguard_memory_query(query="Where is authentication handled?")
chainguard_memory_query(query="Wo wird Validierung gemacht?")

# Filter by type: all, code, functions, database, architecture
chainguard_memory_query(query="user table", filter_type="database")

# Generate deep logic summaries
chainguard_memory_summarize()                    # All new files
chainguard_memory_summarize(file="src/auth.py")  # Specific file

# Add learnings for future sessions
chainguard_memory_update(action="add_learning", learning="Auth uses JWT with 24h expiry")

# Check memory health
chainguard_memory_status()

# Export/Import for backup or transfer
chainguard_memory_export(format="json", compress=True)
chainguard_memory_import(file="path/to/export.json")
```

### Database Schema Inspection

```python
# Connect to database
chainguard_db_connect(
    host="localhost",
    user="root",
    password="...",
    database="myapp"
)

# Get schema (prevents SQL field name guessing)
chainguard_db_schema()
```

## Memory System Deep Dive

### RAG Pipeline

When a query is made via `chainguard_memory_query`, the following pipeline runs:

```
Query → Keyword Extraction → Keyword Expansion → Embedding (384-dim)
  → Vector Search (6 collections) → Scoring → Deduplication → Formatting
```

1. **Keyword Extraction** - Extracts up to 10 keywords, removes English + German stop words
2. **Keyword Expansion** - Expands with 30 synonym groups (e.g., `login` → `auth`, `authentication`, `signin`, `session`, `jwt`, `token`)
3. **Embedding** - Converts to 384-dimensional vector via fastembed (ONNX Runtime)
4. **Vector Search** - Queries all 6 collections using cosine distance
5. **Scoring** - Calculates weighted relevance score:
   - Semantic similarity: **60%**
   - Keyword match: **25%**
   - Recency bonus: **15%** (last 24h: 1.0, last week: 0.8, last month: 0.5)
   - Task-type bonus: 0-20% (e.g., `database` tasks boost table/migration results)
   - Source-type weight: test files 0.7x, config 0.8x, migrations 0.85x
6. **Deduplication** - Keeps only the best result per file path
7. **Collection Balancing** - Respects per-collection limits (code_structure: 4, functions: 3, architecture: 2, etc.)
8. **Filtering** - Only results with score > 0.4 are returned
9. **Caching** - Results cached for 5 minutes (TTLLRUCache, max 100 entries)

### Collections

| Collection | Content | Limit |
|------------|---------|-------|
| `code_structure` | File paths, classes, imports | 4 |
| `code_summaries` | Deep logic summaries of what code does | 3 |
| `functions` | Function/method signatures and purposes | 3 |
| `architecture` | Detected patterns (MVC, layered, etc.) | 2 |
| `learnings` | Developer insights stored via `memory_update` | 2 |
| `database_schema` | Table structures, columns, relationships | 2 |

### Automatic Context Injection

The `chainguard_memory_inject.py` hook runs on every `UserPromptSubmit` event:

- Extracts keywords from the user's prompt (max 10)
- Queries memory using fast **keyword-based LIKE queries** against sqlite3 (avoids fastembed cold-start)
- Returns relevant code locations, functions, and structure grouped by type
- **3-second timeout** to prevent hanging Claude Code
- **File-based cache** with 5-minute TTL for repeated queries
- Prompts shorter than 20 characters are skipped

### Multilingual Support

**Model:** `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions)

Supports 50+ languages including German, English, Spanish, French, Italian, Dutch, Portuguese, Polish, Russian, Chinese, Japanese, Korean, and more. Both queries and indexed content can be in any supported language.

Stop words are filtered for both English and German (100+ words).

### Auto-Refresh (v6.8)

When `chainguard_set_scope()` is called:

1. Checks if memory is older than 30 days (`STALE_MEMORY_THRESHOLD_DAYS`)
2. Finds changed files via git log (fast) or mtime fallback (capped at 1000 files)
3. Re-indexes up to 30 changed files incrementally (`STALE_MEMORY_MAX_FILES`)
4. Only saves metadata when all files succeed (error protection)

### Vector Store Architecture

The lightweight vector store (`vectorstore.py`) replaces ChromaDB:

- **Storage:** Single `vectors.sqlite3` file per project (~3 MB for 1700 docs)
- **Vectors in RAM:** All vectors loaded as numpy arrays for fast cosine similarity
- **Thread safety:** Thread-local sqlite3 connections, WAL mode for concurrent reads
- **ChromaDB-compatible API:** Drop-in replacement (add, upsert, query, get, delete, count)
- **WHERE filters:** Supports `$eq` and `$ne` operators on metadata

### Export & Import

```python
# Export memory (JSON or JSONL, optional gzip compression)
chainguard_memory_export(format="json", compress=True, include_embeddings=False)

# Import memory (merge or replace)
chainguard_memory_import(file="path/to/export.json", merge=True, skip_existing=True)

# List available exports
chainguard_list_exports()
```

- **Max 10,000 documents** per export file
- **Formats:** JSON (single file) or JSONL (streaming, better for large datasets)
- **Merge mode:** Combine with existing data or clear and replace
- Exports stored in `~/.chainguard/exports/`

### Memory Configuration

All constants in `~/.chainguard/chainguard/config.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MEMORY_ENABLED` | `True` | Enable/disable memory system |
| `AUTO_REFRESH_STALE_MEMORY` | `True` | Auto-refresh at `set_scope` |
| `STALE_MEMORY_THRESHOLD_DAYS` | `30` | Days before memory is considered stale |
| `STALE_MEMORY_MAX_FILES` | `30` | Max files per auto-refresh |
| `MTIME_FALLBACK_MAX_FILES` | `1000` | Cap for mtime-based file scanning |
| `SCORING_WEIGHTS` | `semantic: 0.6, keyword: 0.25, recency: 0.15` | Relevance scoring weights |
| `SOURCE_TYPE_WEIGHTS` | `test: 0.7, config: 0.8, migration: 0.85` | Source penalty multipliers |
| `COLLECTION_LIMITS` | per-collection max results | Balances results across collections |

## Available Tools

### Core Tools
| Tool | Description |
|------|-------------|
| `chainguard_set_scope` | Define task scope and criteria |
| `chainguard_track` | Track file changes with syntax validation |
| `chainguard_status` | Ultra-compact status line |
| `chainguard_finish` | Complete task with validation |

### Memory Tools
| Tool | Description |
|------|-------------|
| `chainguard_memory_init` | Initialize project memory (indexes code, functions, summaries) |
| `chainguard_memory_query` | Semantic code search (multilingual, 50+ languages) |
| `chainguard_memory_summarize` | Generate deep logic summaries for code files |
| `chainguard_memory_update` | Re-index file, add learning, or cleanup stale entries |
| `chainguard_memory_status` | Show memory statistics (docs, storage size, staleness) |
| `chainguard_memory_export` | Export memory to portable JSON/JSONL file |
| `chainguard_memory_import` | Import memory from exported file |
| `chainguard_list_exports` | List available memory export files |

### Analysis Tools
| Tool | Description |
|------|-------------|
| `chainguard_analyze` | Pre-flight code analysis |
| `chainguard_analyze_code` | AST-based code analysis |
| `chainguard_detect_architecture` | Detect architecture patterns |

### Hallucination Prevention Tools
| Tool | Description |
|------|-------------|
| `chainguard_symbol_mode` | Set symbol validation mode (OFF/WARN/STRICT/ADAPTIVE) |
| `chainguard_validate_symbols` | Validate function/method calls against codebase |
| `chainguard_validate_packages` | Validate imports against project dependencies |

### Database Tools
| Tool | Description |
|------|-------------|
| `chainguard_db_connect` | Connect to database |
| `chainguard_db_schema` | Get database schema |
| `chainguard_db_table` | Get table details |

### HTTP Testing Tools
| Tool | Description |
|------|-------------|
| `chainguard_set_base_url` | Set base URL for tests |
| `chainguard_test_endpoint` | Test HTTP endpoint |
| `chainguard_login` | Login and store session |

### Kanban Tools
| Tool | Description |
|------|-------------|
| `chainguard_kanban_init` | Initialize board with preset or custom columns |
| `chainguard_kanban` | Show compact board view |
| `chainguard_kanban_show` | Full graphical board view |
| `chainguard_kanban_add` | Add card with priority, tags, detail |
| `chainguard_kanban_move` | Move card to column |
| `chainguard_kanban_detail` | Get card details |
| `chainguard_kanban_update` | Update card properties |
| `chainguard_kanban_delete` | Delete card |
| `chainguard_kanban_archive` | Archive completed card |
| `chainguard_kanban_history` | Show archived cards |

## Architecture

```
~/.chainguard/
├── venv/                 # Python virtual environment (v6.6+)
├── chainguard/           # MCP Server Package (34 modules)
│   ├── handlers.py       # Tool handlers (224 KB)
│   ├── tools.py          # Tool definitions
│   ├── models.py         # Data models
│   ├── config.py         # Configuration & feature flags
│   ├── kanban.py         # Kanban System (v6.5)
│   ├── memory.py         # Long-Term Memory
│   ├── vectorstore.py    # Lightweight vector store (sqlite3 + numpy)
│   ├── embeddings.py     # fastembed integration
│   ├── code_summarizer.py # Deep Logic Extraction
│   ├── ast_analyzer.py   # AST Analysis
│   ├── architecture.py   # Pattern Detection
│   ├── symbol_validator.py # Hallucination Prevention
│   ├── symbol_patterns.py  # Language-specific patterns
│   ├── package_validator.py # Slopsquatting Detection
│   ├── db_inspector.py   # Database inspector (MySQL/PG/SQLite)
│   ├── db_credentials.py # Persistent DB credentials
│   ├── http_session.py   # HTTP session management
│   ├── test_runner.py    # Test execution runner
│   ├── history.py        # Error/change history
│   ├── memory_export.py  # Memory import/export
│   ├── toon.py           # TOON encoder
│   └── ...
├── chainguard_mcp.py     # MCP Entry Point
├── hooks/                # Claude Code Hooks
│   ├── chainguard_enforcer.py      # PreToolUse: Block Edit/Write violations
│   ├── chainguard_memory_inject.py # UserPromptSubmit: Memory context injection
│   └── chainguard_scope_reminder.py # UserPromptSubmit: Scope reminder (v6.1)
├── projects/             # Project State Storage
├── memory/               # sqlite3 Vector Storage
└── templates/            # CLAUDE.md Templates
```

### Hooks

Chainguard uses Claude Code hooks for automatic enforcement:

| Hook | Type | Purpose |
|------|------|---------|
| `chainguard_scope_reminder.py` | UserPromptSubmit | Reminds to set scope before starting work |
| `chainguard_enforcer.py` | PreToolUse | Blocks Edit/Write on rule violations |
| `chainguard_memory_inject.py` | UserPromptSubmit | Injects relevant memory context |

## Documentation

- [Usage Guide](docs/USAGE.md)
- [Testing Guide](docs/TESTING.md)
- [Long-Term Memory Concept](docs/LONG-TERM-MEMORY-CONCEPT.md)
- [Sync & Install Checklist](SYNCINSTALL.md)

## Development

### Running Tests

```bash
cd src/mcp-server
python3 -m pytest tests/ -v
```

### Test Coverage

| Module | Tests |
|--------|-------|
| Core (cache, models, handlers) | 88 |
| Validators | 48 |
| Analyzers | 46 |
| Memory System | 103 |
| Memory Integration (PRD, refresh) | 24+ |
| Vector Store (sqlite3 + numpy) | 50+ |
| Code Summarizer | 45 |
| TOON Encoder | 63 |
| Hallucination Prevention | 71 |
| Symbol Validation | 47 |
| DB Credentials | 30 |
| Kanban System | 50 |
| **Total** | **1300+** |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the **Polyform Noncommercial License 1.0.0**.

**You may:**
- Use this software for any noncommercial purpose
- Modify and create derivative works
- Share and distribute the software

**You may not:**
- Sell this software or use it for commercial purposes
- Only Provimedia GmbH is authorized to sell this software

See the [LICENSE](LICENSE) file for full details.

### Third-Party Licenses

This project includes data derived from the following open source projects:

| Component | License | Copyright |
|-----------|---------|-----------|
| [JetBrains phpstorm-stubs](https://github.com/JetBrains/phpstorm-stubs) | Apache-2.0 | © 2010-2024 JetBrains s.r.o. |

The PHP builtins database (`data/php_builtins.json`) is generated from phpstorm-stubs and used for hallucination prevention in symbol validation.

## Credits

Created and maintained by **[Provimedia GmbH](https://provimedia.de)**

## Changelog

### v6.8.1
- **Partial-Refresh Timestamp Protection** - Only saves memory metadata when all files succeed (errors==0)
- **PRD File Caching** - PRD files detected at `set_scope` are cached in `ProjectState.prd_files`
- **mtime Fallback Limit** - Caps `os.walk()` to 1000 files for monorepo protection

### v6.8.0
- **Auto-Refresh Stale Memory** - Detects memory older than 30 days at `set_scope` and incrementally re-indexes changed files
  - Git log-based discovery (fast path) with mtime-based fallback
  - New config: `AUTO_REFRESH_STALE_MEMORY`, `STALE_MEMORY_THRESHOLD_DAYS`, `STALE_MEMORY_MAX_FILES`
- New `ProjectMemory.get_metadata()` method for reading metadata.json

### v6.7.0
- **PRD Auto-Detection** - Automatically detects PRD/requirements documents at `set_scope`
  - 16 filename patterns: `PRD.md`, `REQUIREMENTS.md`, `SPEC.md`, `SPECIFICATION.md`, etc.
  - Searches 7 directories: root, `docs/`, `doc/`, `.claude/`, `requirements/`, `specs/`, `.github/`
  - Workflow reminders at `set_scope` (check PRD) and `finish` (update PRD if >=3 files changed)

### v6.6.0
- **Memory System Overhaul** - Replaced ChromaDB + sentence-transformers with fastembed + numpy + sqlite3
  - RAM usage reduced from ~3.8 GB to ~500 MB (7.6x reduction)
  - New `vectorstore.py` module: lightweight vector store with sqlite3 backend + RAM vectors
  - New `embeddings.py` module: fastembed (ONNX Runtime) integration
  - Drop-in replacement maintains ChromaDB Collection API
  - `MEMORY_ENABLED` now defaults to `True`
- **Multilingual Embeddings** - Switched from `all-MiniLM-L6-v2` (English-only) to `paraphrase-multilingual-MiniLM-L12-v2` (50+ languages)
  - Same 384 dimensions, no storage migration needed
  - Auto-force re-init on model change
- **Python venv Installation** - Replaced `pip install --user` with dedicated venv at `~/.chainguard/venv/`
  - Fixes PEP 668 compatibility on modern macOS/Linux
  - Updated installer, verifier, and uninstaller
- **Context Injection Quality** - Source-type weighting (test files 0.7x), per-file deduplication, lower relevance threshold (0.5 -> 0.4)

### v6.5.0
- **Kanban System** - Persistent task management for complex, multi-day projects
  - New `kanban.py` module with KanbanCard, KanbanBoard, KanbanManager classes
  - 10 new tools for full Kanban workflow
  - 7 column presets: default, programming, content, devops, research, agile, simple
  - Custom columns via LLM prompt injection in tool description
  - YAML persistence in `.claude/kanban.yaml`
  - Linked markdown files for card details in `.claude/cards/`
  - Archive system for completed cards
  - Graphical board view with progress bar and blocked card highlighting
  - Dependency tracking between cards
  - 50 new unit tests
- **Smart Kanban Suggestion** - Automatically recommends Kanban when ≥5 acceptance criteria or complexity keywords detected ("mehrtägig", "komplex", "pipeline", etc.)

### v6.4.6
- **String-Content Stripping for False Positive Prevention** - Prevents hallucination warnings for text inside strings
  - HTML placeholders: `placeholder="Max Mustermann (optional)"` no longer triggers warnings
  - SQL in strings: `"SELECT * FROM table_name WHERE..."` no longer detects table names as calls
  - Preserves interpolated strings (f-strings, $-strings, template literals) since they contain real code
  - 9 new tests for string-content false positive prevention

### v6.4.5
- **Symbol-Warnings Block Finish** - `chainguard_finish()` is blocked when symbol warnings exist (unless `force=True`)
- **Docstring/Multi-line Comment Skipping** - Function calls in docstrings and comments are no longer detected
- **Python Stdlib Extended** - Added `field`, `dataclass`, `Optional`, `Path`, `Any`, `List`, `Dict`, etc.

### v6.4.4
- **Extended Builtins: JS Web APIs + SQL Functions** - Fixes false positives
  - JavaScript: Added `IntersectionObserver`, `MutationObserver`, `ResizeObserver`, `FormData`, `AbortController`, `WebSocket`, `Worker`, and 30+ more Web APIs
  - PHP: Added SQL functions that appear in PHP code: `CURDATE`, `NOW`, `COALESCE`, `CONCAT`, `GROUP_CONCAT`, `SUM`, `AVG`, and 50+ more
  - 10 new tests for Web APIs and SQL functions

### v6.4.3
- **PHP Case-Insensitive Builtin Check** - Fixes false positives for uppercase PHP functions
  - `MAX()`, `DATE()`, `COUNT()`, `StrLen()` etc. now correctly recognized as builtins
  - PHP is case-insensitive, so `is_builtin()` now compares lowercase for PHP
  - Reduces false positives from SQL functions used in PHP code
  - 4 new tests for case-insensitivity

### v6.4.2
- **Action-Required Context Injection** - Forces LLM to actively check hallucination warnings
  - `<action-required>` XML tags wrap symbol warnings at `chainguard_finish()`
  - Prominent "🔴 AKTION ERFORDERLICH" messaging instead of subtle warnings
  - Clear 3-step instructions: Check existence → Check imports → Ignore if false positive
  - Warning: "NICHT IGNORIEREN - Halluzinierte Funktionen führen zu Runtime-Fehlern!"
  - Prevents warnings from being overlooked in long sessions with many tasks

### v6.4.1
- **Symbol Warning Aggregation** - Hallucination warnings are now collected during session
  - Warnings are stored in `state.symbol_warnings` instead of being shown only once
  - All collected warnings are displayed at `chainguard_finish()` - prevents them from being lost
  - Useful for long sessions with 40+ tasks where warnings would otherwise be ignored
- Better visibility for potential hallucinated function calls

### v6.4.0
- **Persistent DB Credentials** - Database credentials saved per project (obfuscated)
  - Call `chainguard_db_connect()` without parameters to use saved credentials
  - Credentials are XOR + Base64 obfuscated (machine-specific key)
  - Auto-saved after successful connection, auto-deleted on failure
  - New `chainguard_db_forget` tool to delete saved credentials
  - New `db_credentials.py` module with `CredentialStore` class
  - 30 new tests for credential handling
- New `remember` parameter for `chainguard_db_connect` (default: True)

### v6.3.1
- **PHP Builtins Database** - 11,000+ PHP functions/classes/methods from JetBrains phpstorm-stubs
  - Dramatically reduces false positives in symbol validation (from 170+ to near zero)
  - Includes: Core functions (5,028), classes (1,035), methods (10,039)
  - Lazy-loaded on first PHP validation for zero startup cost
  - Generator script to update from latest phpstorm-stubs
- New `generate_php_builtins.py` script for updating the database

### v6.3.0
- **PHPStan Integration** - Static analysis for PHP files catches runtime errors BEFORE execution
  - Detects null access errors (`$user['id']` on null)
  - Type mismatches (string vs int)
  - Undefined methods and properties
  - Configurable analysis level (0-9, default: 8)
  - Smart project root detection (composer.json, vendor/, phpstan.neon)
- Automatic PHPStan detection (global, vendor/bin, or composer global)
- New config flags: `PHPSTAN_ENABLED`, `PHPSTAN_LEVEL`

### v6.1.0
- **Hallucination Prevention** - Detects LLM-hallucinated function calls and package imports
  - `chainguard_validate_symbols` - Validates function/method calls against codebase
  - `chainguard_validate_packages` - Slopsquatting detection for typosquatted packages
  - 7-language support: PHP, JavaScript, TypeScript, Python, C#, Go, Rust
  - Adaptive mode auto-adjusts based on false positive rate
- **Scope Reminder Hook** - New UserPromptSubmit hook that reminds to set scope
- Fixes the gap where pure analysis tasks (Task/Explore) could bypass scope enforcement
- 30-minute cooldown to prevent spam
- 118 new tests (symbol_validation: 47, package_validator: 71)

### v6.0.0
- **TOON Encoder** - Token-Oriented Object Notation for 30-60% token savings
- New `toon.py` module with `encode_toon`, `toon_array`, `toon_object` functions
- Integrated into `chainguard_projects` and `chainguard_history`
- **Memory disabled by default** - Prevents RAM issues on low-memory systems
- Feature flags: `TOON_ENABLED=True`, `MEMORY_ENABLED=False`, `XML_RESPONSES_ENABLED=False`
- 63 new tests for TOON encoder, 764+ total tests

### v5.4.0
- Deep Logic Summaries with `code_summarizer.py`
- New `chainguard_memory_summarize` tool
- `code_summaries` collection for semantic code understanding
- 45 new tests for code summarizer

### v5.3.0
- AST Analysis with tree-sitter
- Architecture Pattern Detection
- Framework Recognition
- Memory Export/Import

### v5.2.0
- Smart Context Injection
- Automatic memory updates on track/finish

### v5.1.0
- Long-Term Memory with ChromaDB
- Semantic code search
- Project isolation

### v5.0.0
- Task Mode System (programming, content, devops, research)
- Mode-specific tools

---

**Made with care by Provimedia GmbH**
