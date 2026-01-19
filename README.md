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

### Long-Term Memory (v5.1+)
- **Semantic Code Search** - Natural language queries like "Where is authentication handled?"
- **ChromaDB Integration** - Local vector database, 100% offline
- **Automatic Indexing** - Code structure, functions, database schema, architecture patterns
- **Project Isolation** - Each project has its own isolated memory

> **Note:** Long-Term Memory is disabled by default (`MEMORY_ENABLED=False`) to prevent high RAM usage. Enable it in `~/.chainguard/chainguard/config.py` if you have 8GB+ RAM.

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

### Kanban System (v6.5)
- **Persistent Task Management** - Track complex, multi-day projects with a visual board
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
| `MEMORY_ENABLED` | `False` | Long-Term Memory (requires chromadb, high RAM) |
| `XML_RESPONSES_ENABLED` | `False` | Structured XML responses |
| `PHPSTAN_ENABLED` | `True` | PHPStan static analysis for PHP files |
| `PHPSTAN_LEVEL` | `8` | Analysis level 0-9 (5+ catches null errors, 8 recommended) |

## Installation

### Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/provimedia/chainguard/main/installer/install.sh | bash
```

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

### Requirements

- Python 3.9+
- Claude Code CLI
- Optional: `chromadb` and `sentence-transformers` for Long-Term Memory
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
# Initialize memory (once per project)
chainguard_memory_init()

# Semantic search
chainguard_memory_query(query="Where is authentication handled?")

# Generate deep logic summaries
chainguard_memory_summarize()
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
| `chainguard_memory_init` | Initialize project memory |
| `chainguard_memory_query` | Semantic code search |
| `chainguard_memory_summarize` | Generate deep logic summaries |
| `chainguard_memory_status` | Show memory statistics |

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
├── chainguard/           # MCP Server Package (24 modules)
│   ├── handlers.py       # Tool handlers
│   ├── kanban.py         # Kanban System (v6.5)
│   ├── memory.py         # Long-Term Memory
│   ├── code_summarizer.py # Deep Logic Extraction
│   ├── ast_analyzer.py   # AST Analysis
│   ├── architecture.py   # Pattern Detection
│   ├── symbol_validator.py # Hallucination Prevention
│   ├── symbol_patterns.py  # Language-specific patterns
│   ├── package_validator.py # Slopsquatting Detection
│   └── ...
├── chainguard_mcp.py     # MCP Entry Point
├── hooks/                # Claude Code Hooks
│   ├── chainguard_enforcer.py      # PreToolUse: Block Edit/Write violations
│   ├── chainguard_memory_inject.py # UserPromptSubmit: Memory context injection
│   └── chainguard_scope_reminder.py # UserPromptSubmit: Scope reminder (v6.1)
├── projects/             # Project State Storage
├── memory/               # ChromaDB Vector Storage
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
| Code Summarizer | 45 |
| TOON Encoder | 63 |
| Hallucination Prevention | 71 |
| Symbol Validation | 47 |
| DB Credentials | 30 |
| Kanban System | 50 |
| **Total** | **1195+** |

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
