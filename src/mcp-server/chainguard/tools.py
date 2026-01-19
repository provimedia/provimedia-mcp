"""
CHAINGUARD MCP Server - Tool Definitions Module

Contains: Tool definitions for MCP

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.
"""

from typing import List

try:
    from mcp.types import Tool
except ImportError:
    Tool = None  # Will fail at runtime if mcp not installed


async def get_tool_definitions() -> List[Tool]:
    """Return all tool definitions."""
    return [
        # CORE: Scope Definition with Mode Selection
        Tool(
            name="chainguard_set_scope",
            description="""Define task scope at start with MODE selection.

**mode** - Choose based on WHAT you're building:
- "programming" (DEFAULT): Writing code, fixing bugs, implementing features
- "content": Writing books, articles, documentation, creative text
- "devops": Server admin, CLI tools, WordPress, infrastructure setup
- "research": Research, analysis, information gathering
- "generic": Minimal tracking without validation

Examples:
- "Implementiere Login-Feature" → programming
- "Schreibe Kapitel 3 meines Buches" → content
- "Richte Nginx-Server ein" → devops
- "Analysiere Konkurrenz-Produkte" → research

The mode determines which features are active (syntax validation, HTTP tests, etc.).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "description": {"type": "string", "description": "What you're building"},
                    "mode": {
                        "type": "string",
                        "enum": ["programming", "content", "devops", "research", "generic"],
                        "description": "Task mode - determines active features",
                        "default": "programming"
                    },
                    "modules": {"type": "array", "items": {"type": "string"}, "description": "File patterns in scope"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "checklist": {"type": "array", "items": {"type": "object"}}
                },
                "required": ["description"]
            }
        ),

        # CORE: Silent Tracking with Syntax Validation
        Tool(
            name="chainguard_track",
            description="Track file change + AUTO-VALIDATE syntax (PHP/JS/JSON/Python/TS). Returns errors immediately. Silent if OK.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "file": {"type": "string", "description": "Changed file path"},
                    "action": {"type": "string", "description": "Brief action: 'edit', 'create', 'delete'"},
                    "skip_validation": {"type": "boolean", "description": "Skip syntax check (default: false)"},
                    "ctx": {"type": "string", "description": "Context marker - always pass ctx='🔗'"}
                },
                "required": []
            }
        ),

        # CORE: Batch Tracking
        Tool(
            name="chainguard_track_batch",
            description="Track multiple files at once with syntax validation. More efficient than multiple track calls.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "List of changed file paths"},
                    "action": {"type": "string", "description": "Brief action: 'edit', 'create', 'delete'", "default": "edit"},
                    "skip_validation": {"type": "boolean", "description": "Skip syntax checks (default: false)"}
                },
                "required": ["files"]
            }
        ),

        # CORE: Minimal Status
        Tool(
            name="chainguard_status",
            description="Ultra-compact one-line status. USE THIS for quick checks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "ctx": {"type": "string", "description": "Context marker - always pass ctx='🔗'"}
                },
                "required": []
            }
        ),

        # SECONDARY: Full Context
        Tool(
            name="chainguard_context",
            description="Full context - USE SPARINGLY. Only when you need details.",
            inputSchema={
                "type": "object",
                "properties": {"working_dir": {"type": "string"}},
                "required": []
            }
        ),

        # CORE: Phase Management
        Tool(
            name="chainguard_set_phase",
            description="Set phase: planning, implementation, testing, review, done",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "phase": {"type": "string", "enum": ["planning", "implementation", "testing", "review", "done"]},
                    "task": {"type": "string"}
                },
                "required": ["phase"]
            }
        ),

        # CORE: Run Checklist
        Tool(
            name="chainguard_run_checklist",
            description="Execute all checklist checks. Returns pass/fail summary.",
            inputSchema={
                "type": "object",
                "properties": {"working_dir": {"type": "string"}},
                "required": []
            }
        ),

        # CORE: Mark Criteria
        Tool(
            name="chainguard_check_criteria",
            description="Mark acceptance criterion as done or view all criteria status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "criterion": {"type": "string"},
                    "fulfilled": {"type": "boolean"}
                },
                "required": []
            }
        ),

        # SECONDARY: Validation Record
        Tool(
            name="chainguard_validate",
            description="Record validation result. Resets change counter.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "status": {"type": "string", "enum": ["PASS", "FAIL"]},
                    "note": {"type": "string"}
                },
                "required": ["status"]
            }
        ),

        # UTILITY: Alert
        Tool(
            name="chainguard_alert",
            description="Add alert for issues that need attention.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["message"]
            }
        ),

        # UTILITY: Clear Alerts
        Tool(
            name="chainguard_clear_alerts",
            description="Acknowledge all alerts.",
            inputSchema={
                "type": "object",
                "properties": {"working_dir": {"type": "string"}},
                "required": []
            }
        ),

        # ADMIN: List Projects
        Tool(
            name="chainguard_projects",
            description="List all tracked projects.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),

        # ADMIN: Config
        Tool(
            name="chainguard_config",
            description="View or set config.",
            inputSchema={
                "type": "object",
                "properties": {
                    "validation_threshold": {"type": "integer"}
                },
                "required": []
            }
        ),

        # HTTP Testing
        Tool(
            name="chainguard_test_endpoint",
            description="Test HTTP endpoint with session support. Detects auth requirements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "url": {"type": "string", "description": "Full URL or path"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
                    "data": {"type": "object", "description": "Request body/form data"},
                    "headers": {"type": "object", "description": "Additional headers"}
                },
                "required": ["url"]
            }
        ),

        Tool(
            name="chainguard_login",
            description="Login to application and store session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "login_url": {"type": "string", "description": "Login page URL"},
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                    "username_field": {"type": "string", "default": "email"},
                    "password_field": {"type": "string", "default": "password"}
                },
                "required": ["login_url", "username", "password"]
            }
        ),

        Tool(
            name="chainguard_set_base_url",
            description="Set base URL for HTTP tests",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "base_url": {"type": "string", "description": "Base URL for all requests"}
                },
                "required": ["base_url"]
            }
        ),

        Tool(
            name="chainguard_clear_session",
            description="Clear stored session/cookies.",
            inputSchema={
                "type": "object",
                "properties": {"working_dir": {"type": "string"}},
                "required": []
            }
        ),

        # Code Analysis
        Tool(
            name="chainguard_analyze",
            description="Pre-flight check for code analysis. Returns metrics, patterns, hotspots, and a tailored checklist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "target": {"type": "string", "description": "File path to analyze"}
                },
                "required": ["target"]
            }
        ),

        # Test Runner (v4.10)
        Tool(
            name="chainguard_test_config",
            description="Configure test command. Stores command for chainguard_run_tests.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "command": {"type": "string", "description": "Test command (e.g. './vendor/bin/phpunit')"},
                    "args": {"type": "string", "description": "Additional arguments (e.g. 'tests/ --colors=never')"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)", "default": 300}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_run_tests",
            description="Run tests using configured command. Auto-detects PHPUnit/Jest/pytest output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_test_status",
            description="Show last test run status with errors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # Complete Task
        Tool(
            name="chainguard_finish",
            description="Complete task with FULL validation. 2-step process with impact-check.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "confirmed": {"type": "boolean", "description": "Confirm impact-check was reviewed"},
                    "force": {"type": "boolean", "description": "Force completion despite open issues"}
                },
                "required": []
            }
        ),

        # Error Memory / History (v4.11)
        Tool(
            name="chainguard_recall",
            description="Search error history for similar issues and fixes. Use when encountering a problem.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "query": {"type": "string", "description": "Search query (e.g. 'php syntax Controller')"},
                    "limit": {"type": "integer", "description": "Max results (default: 5)", "default": 5}
                },
                "required": ["query"]
            }
        ),

        Tool(
            name="chainguard_history",
            description="View recent change history for the project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max entries (default: 20)", "default": 20},
                    "scope_only": {"type": "boolean", "description": "Only show current scope", "default": False}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_learn",
            description="Document a fix/resolution for the most recent error. Teaches the system for future Auto-Suggest.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "resolution": {"type": "string", "description": "How the error was fixed"},
                    "file_pattern": {"type": "string", "description": "File pattern (auto-detected if not given)"},
                    "error_type": {"type": "string", "description": "Error type (auto-detected if not given)"}
                },
                "required": ["resolution"]
            }
        ),

        # Database Inspector (v4.12, v6.4: persistent credentials)
        Tool(
            name="chainguard_db_connect",
            description="Connect to database. v6.4: Credentials are saved (obfuscated) per project after successful connection. Call without params to use saved credentials.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "host": {"type": "string", "description": "Database host", "default": "localhost"},
                    "port": {"type": "integer", "description": "Database port", "default": 3306},
                    "user": {"type": "string", "description": "Database user (optional if saved)"},
                    "password": {"type": "string", "description": "Database password (optional if saved)"},
                    "database": {"type": "string", "description": "Database name (optional if saved)"},
                    "db_type": {"type": "string", "enum": ["mysql", "postgres", "sqlite"], "default": "mysql"},
                    "remember": {"type": "boolean", "description": "Save credentials for next session", "default": True}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_db_schema",
            description="Get database schema (tables, columns, types, keys). Cached for 5 minutes. Use before writing SQL queries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "refresh": {"type": "boolean", "description": "Force refresh cache", "default": False}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_db_table",
            description="Get detailed info for a single table including optional sample data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "table": {"type": "string", "description": "Table name"},
                    "sample": {"type": "boolean", "description": "Show 5 sample rows", "default": False}
                },
                "required": ["table"]
            }
        ),

        Tool(
            name="chainguard_db_disconnect",
            description="Disconnect from database and clear schema cache.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_db_forget",
            description="Delete saved DB credentials for this project. Use when password changed or to remove stored credentials.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # =====================================================================
        # MODE-SPECIFIC TOOLS (v5.0)
        # =====================================================================

        # CONTENT MODE TOOLS
        Tool(
            name="chainguard_word_count",
            description="Get word count statistics (CONTENT mode). Shows total words and chapter progress.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "file": {"type": "string", "description": "Optional: count words in specific file"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_track_chapter",
            description="Track chapter progress (CONTENT mode). Set chapter status: draft, review, done.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "chapter": {"type": "string", "description": "Chapter name or number"},
                    "status": {"type": "string", "enum": ["draft", "review", "done"], "description": "Chapter status"},
                    "word_count": {"type": "integer", "description": "Optional: word count for this chapter"}
                },
                "required": ["chapter", "status"]
            }
        ),

        # DEVOPS MODE TOOLS
        Tool(
            name="chainguard_log_command",
            description="Log executed command (DEVOPS mode). Tracks CLI commands for audit trail.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "command": {"type": "string", "description": "The executed command"},
                    "result": {"type": "string", "enum": ["success", "failed"], "default": "success"},
                    "output": {"type": "string", "description": "Optional: command output (truncated to 500 chars)"}
                },
                "required": ["command"]
            }
        ),

        Tool(
            name="chainguard_checkpoint",
            description="Create rollback checkpoint (DEVOPS mode). Save state before critical changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "name": {"type": "string", "description": "Checkpoint name (e.g. 'before-nginx-config')"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "Files to note for potential rollback"}
                },
                "required": ["name"]
            }
        ),

        Tool(
            name="chainguard_health_check",
            description="Run health checks (DEVOPS mode). Quick status of endpoints and services.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "endpoints": {"type": "array", "items": {"type": "string"}, "description": "URLs to check"},
                    "services": {"type": "array", "items": {"type": "string"}, "description": "Systemd services to check"}
                },
                "required": []
            }
        ),

        # RESEARCH MODE TOOLS
        Tool(
            name="chainguard_add_source",
            description="Track research source (RESEARCH mode). Log URLs and documents for later reference.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "url": {"type": "string", "description": "Source URL"},
                    "title": {"type": "string", "description": "Source title"},
                    "relevance": {"type": "string", "enum": ["high", "medium", "low"], "default": "medium"}
                },
                "required": ["url"]
            }
        ),

        Tool(
            name="chainguard_index_fact",
            description="Index discovered fact (RESEARCH mode). Store findings with confidence level.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "fact": {"type": "string", "description": "The discovered fact"},
                    "source": {"type": "string", "description": "Where this fact comes from"},
                    "confidence": {"type": "string", "enum": ["verified", "likely", "uncertain"], "default": "likely"}
                },
                "required": ["fact"]
            }
        ),

        Tool(
            name="chainguard_sources",
            description="List all tracked sources (RESEARCH mode). Shows sources by relevance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_facts",
            description="List all indexed facts (RESEARCH mode). Shows facts by confidence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # =====================================================================
        # LONG-TERM MEMORY TOOLS (v5.1)
        # =====================================================================

        Tool(
            name="chainguard_memory_init",
            description="""Initialize Long-Term Memory for the project. Indexes code structure, functions, and patterns.

Features:
- Semantic search ("Where is authentication handled?")
- Automatic context injection at set_scope
- Persistent across sessions

First run takes 1-5 minutes depending on project size. Subsequent runs are fast.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "include_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Glob patterns to include (default: **/*.{py,php,js,ts,tsx})"
                    },
                    "exclude_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Patterns to exclude (default: node_modules, vendor, .git)"
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force re-initialization even if memory exists",
                        "default": False
                    }
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_memory_query",
            description="""Semantic search in project memory. Ask questions in natural language.

Examples:
- "Where is authentication handled?"
- "Which functions use the users table?"
- "How does error handling work?"

Returns relevant code locations with relevance scores.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "query": {"type": "string", "description": "Natural language question"},
                    "limit": {"type": "integer", "description": "Max results (default: 5)", "default": 5},
                    "filter_type": {
                        "type": "string",
                        "enum": ["all", "code", "functions", "database", "architecture"],
                        "description": "Filter by type",
                        "default": "all"
                    }
                },
                "required": ["query"]
            }
        ),

        Tool(
            name="chainguard_memory_update",
            description="""Update project memory. Use after major changes or to add learnings.

Actions:
- reindex_file: Re-index a specific file
- add_learning: Add an insight or pattern discovered during work
- cleanup: Remove stale entries""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["reindex_file", "add_learning", "cleanup"],
                        "description": "What to update",
                        "default": "reindex_file"
                    },
                    "file_path": {"type": "string", "description": "File to reindex (for reindex_file action)"},
                    "learning": {"type": "string", "description": "Insight to store (for add_learning action)"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_memory_status",
            description="Show Long-Term Memory status and statistics. Shows indexed documents, storage size, and last update.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_memory_summarize",
            description="""Generate deep logic summaries for code files (v5.4).

Unlike basic indexing which only captures structure (function names, class names),
this tool extracts and stores detailed descriptions of what the code actually DOES.
It analyzes docstrings, comments, function names, and code patterns to create
human-readable summaries of the logic and purpose.

Use this when you need the Memory to understand code behavior, not just structure.

Examples:
- chainguard_memory_summarize() - Summarize all new files in project
- chainguard_memory_summarize(file="src/auth.py") - Summarize specific file
- chainguard_memory_summarize(force=True) - Re-summarize all files""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "file": {"type": "string", "description": "Optional specific file to summarize"},
                    "force": {"type": "boolean", "description": "Re-summarize even if summary exists", "default": False}
                },
                "required": []
            }
        ),

        # =================================================================
        # Phase 3 Tools (v5.3): AST Analysis, Architecture, Export/Import
        # =================================================================

        Tool(
            name="chainguard_analyze_code",
            description="Analyze code structure using AST parsing. Extracts classes, functions, methods, imports, and relationships. Uses tree-sitter when available, falls back to regex.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to analyze (or directory for batch analysis)"},
                    "working_dir": {"type": "string"}
                },
                "required": ["file"]
            }
        ),

        Tool(
            name="chainguard_detect_architecture",
            description="Detect architectural patterns in the codebase. Identifies MVC, MVVM, Clean Architecture, Layered, API-first, and more. Also detects framework (Laravel, Django, React, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_memory_export",
            description="Export project memory to a portable JSON or JSONL file. Useful for backup or transfer between machines.",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["json", "jsonl"], "description": "Export format (default: json)"},
                    "collections": {"type": "array", "items": {"type": "string"}, "description": "Collections to export (default: all)"},
                    "include_embeddings": {"type": "boolean", "description": "Include vector embeddings (larger file)"},
                    "compress": {"type": "boolean", "description": "Compress with gzip"},
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_memory_import",
            description="Import project memory from an exported JSON or JSONL file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Path to import file"},
                    "merge": {"type": "boolean", "description": "Merge with existing data (default: true)"},
                    "skip_existing": {"type": "boolean", "description": "Skip documents that already exist (default: true)"},
                    "working_dir": {"type": "string"}
                },
                "required": ["file"]
            }
        ),

        Tool(
            name="chainguard_list_exports",
            description="List available memory export files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # HALLUCINATION PREVENTION: Symbol Validation
        Tool(
            name="chainguard_symbol_mode",
            description="""Set or view symbol validation mode (Hallucination Prevention).

Modes:
- OFF: Disable symbol validation entirely
- WARN: Show warnings but never block (DEFAULT - safe for production)
- STRICT: Block on high-confidence hallucinated symbols
- ADAPTIVE: Auto-adjust based on false positive rate

Use WARN (default) for normal work. Switch to OFF if you encounter too many false positives.
STRICT is only recommended when you need maximum protection against hallucinated code.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["OFF", "WARN", "STRICT", "ADAPTIVE"], "description": "Validation mode to set (omit to view current mode)"},
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_validate_symbols",
            description="""Validate symbols in code against the codebase (Hallucination Prevention).

Checks for potentially hallucinated function/method calls by comparing:
- Function calls in the code against known definitions in the project
- Built-in functions for each language (PHP, JS, TS, Python, C#, Go, Rust)
- Common external library patterns

Returns confidence scores for each potential issue. High confidence (>0.8) suggests
likely hallucination. Low confidence may be false positives (external APIs, dynamic code).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to validate (relative to project)"},
                    "code": {"type": "string", "description": "Code to validate (alternative to file)"},
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # HALLUCINATION PREVENTION: Package Validation (Slopsquatting Detection)
        Tool(
            name="chainguard_validate_packages",
            description="""Validate package imports against project dependencies (Slopsquatting Detection).

Research shows ~20% of LLM-recommended packages don't exist! Attackers register
these hallucinated package names ("slopsquatting") to distribute malware.

Validates imports against:
- composer.json / composer.lock (PHP)
- package.json / node_modules (JavaScript/TypeScript)
- requirements.txt / pyproject.toml (Python)

Features:
- Typo detection using Levenshtein distance
- Slopsquatting warnings for similar package names
- Standard library whitelisting (Node builtins, Python stdlib, PHP classes)
- Confidence scoring for each issue""",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to validate (relative to project)"},
                    "code": {"type": "string", "description": "Code to validate (alternative to file)"},
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        ),

        # =====================================================================
        # KANBAN SYSTEM (v6.5) - Persistent Task Management
        # =====================================================================

        Tool(
            name="chainguard_kanban_init",
            description="""Initialize Kanban board with custom columns. CALL THIS FIRST before adding cards!

**IMPORTANT - Column Planning:**
Before calling this tool, ANALYZE the user's task and DESIGN appropriate columns!

Think about:
1. What are the logical PHASES of this specific task?
2. What workflow makes sense for THIS project?
3. Are there approval/review steps needed?

**Examples of task-specific columns:**
- API Development: ["design", "implementation", "testing", "documentation", "deployed"]
- Bug Fixing: ["reported", "investigating", "fixing", "testing", "resolved"]
- Migration Project: ["analysis", "preparation", "migration", "validation", "complete"]
- Feature Request: ["specification", "design", "development", "qa", "release"]
- Book Writing: ["outline", "draft", "revision", "editing", "published"]

**Available Presets (if task matches):**
- "programming": backlog → in_progress → testing → review → done
- "content": ideen → entwurf → überarbeitung → lektorat → fertig
- "devops": geplant → vorbereitung → deployment → testing → live
- "research": zu_untersuchen → in_recherche → analyse → verifiziert → dokumentiert
- "agile": backlog → sprint → in_progress → review → done
- "simple": todo → doing → done

**Best Practice:** Design 3-6 columns that reflect the ACTUAL workflow of the task!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Custom column names (e.g., ['planning', 'development', 'testing', 'deployed'])"
                    },
                    "preset": {
                        "type": "string",
                        "enum": ["default", "programming", "content", "devops", "research", "agile", "simple"],
                        "description": "Use a preset instead of custom columns"
                    }
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_kanban",
            description="""View Kanban board. Shows all cards organized by columns.

Use this to:
- Get overview of current project tasks
- See blocked cards (dependencies not met)
- Plan next steps

Compact view shows: priority icon, card ID, title, detail/dependency markers.

TIP: Use chainguard_kanban_init first to set up custom columns for your workflow!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "compact": {"type": "boolean", "description": "Compact view (default: true)", "default": True}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_kanban_add",
            description="""Add a new card to the Kanban board.

Creates a task card with optional:
- Priority (low/medium/high/critical)
- Dependencies (other card IDs that must be done first)
- Tags for categorization
- Detail content (creates linked .md file)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "title": {"type": "string", "description": "Card title"},
                    "column": {"type": "string", "enum": ["backlog", "in_progress", "review", "done"], "default": "backlog"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium"},
                    "depends_on": {"type": "array", "items": {"type": "string"}, "description": "Card IDs this depends on"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                    "detail": {"type": "string", "description": "Detailed description (creates .md file)"}
                },
                "required": ["title"]
            }
        ),

        Tool(
            name="chainguard_kanban_move",
            description="Move a card to a different column. Use to update task status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "card_id": {"type": "string", "description": "Card ID to move"},
                    "to_column": {"type": "string", "enum": ["backlog", "in_progress", "review", "done"], "description": "Target column"}
                },
                "required": ["card_id", "to_column"]
            }
        ),

        Tool(
            name="chainguard_kanban_detail",
            description="Get detailed information for a card, including linked markdown content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "card_id": {"type": "string", "description": "Card ID to get details for"}
                },
                "required": ["card_id"]
            }
        ),

        Tool(
            name="chainguard_kanban_update",
            description="Update card properties (title, priority, tags, dependencies).",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "card_id": {"type": "string", "description": "Card ID to update"},
                    "title": {"type": "string", "description": "New title"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "detail": {"type": "string", "description": "Update detail content"}
                },
                "required": ["card_id"]
            }
        ),

        Tool(
            name="chainguard_kanban_delete",
            description="Delete a card permanently. Use for cards created by mistake.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "card_id": {"type": "string", "description": "Card ID to delete"}
                },
                "required": ["card_id"]
            }
        ),

        Tool(
            name="chainguard_kanban_archive",
            description="Archive a card. Removes from board but keeps in archive.yaml for history.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "card_id": {"type": "string", "description": "Card ID to archive"}
                },
                "required": ["card_id"]
            }
        ),

        Tool(
            name="chainguard_kanban_history",
            description="View archived cards. Shows cards that were completed and archived.",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max cards to show (default: 10)", "default": 10}
                },
                "required": []
            }
        ),

        Tool(
            name="chainguard_kanban_show",
            description="""Display full graphical Kanban board with ALL details.

Shows a complete visual board including:
- Progress bar with completion percentage
- Statistics per column (backlog, in_progress, review, done)
- Blocked cards indicator
- Each card with:
  - Priority (🔴 critical, 🟠 high, 🟡 medium, 🟢 low)
  - ID, title, dates (created/updated)
  - Tags and dependencies
  - FULL linked markdown file content (preview)
  - Blocked status if dependencies not met

Use this for a complete overview of the current project state.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"}
                },
                "required": []
            }
        )
    ]
