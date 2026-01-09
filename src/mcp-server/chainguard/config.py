"""
CHAINGUARD MCP Server - Configuration Module

Contains: Constants, Enums, ChainguardConfig, TaskMode System

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.
"""

import os
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, Set, Union, List, Any


# =============================================================================
# Version
# =============================================================================
VERSION = "6.0.0"


# =============================================================================
# Feature Flags (v6.0)
# =============================================================================
# XML Responses: Enable structured XML responses for better Claude comprehension
# Set CHAINGUARD_XML_RESPONSES=false to disable and use legacy plain text
XML_RESPONSES_ENABLED = os.environ.get("CHAINGUARD_XML_RESPONSES", "true").lower() == "true"


# =============================================================================
# Enums
# =============================================================================
class Phase(str, Enum):
    """
    Valid project phases.
    Inherits from str for JSON serialization compatibility.
    """
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    DONE = "done"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "Phase":
        """Safe conversion from string, defaults to UNKNOWN."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.UNKNOWN


class ValidationStatus(str, Enum):
    """Validation result status."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

    def __str__(self) -> str:
        return self.value


# =============================================================================
# Task Mode System (v5.0)
# =============================================================================
class TaskMode(str, Enum):
    """
    Task modes for different use cases.
    The mode determines which features are active.
    """
    PROGRAMMING = "programming"  # Default: Code, Bugs, Features
    CONTENT = "content"          # Books, Articles, Documentation
    DEVOPS = "devops"            # Server Admin, CLI, WordPress, Infrastructure
    RESEARCH = "research"        # Research, Analysis, Information Gathering
    GENERIC = "generic"          # Minimal tracking without validation

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "TaskMode":
        """Safe conversion from string, defaults to PROGRAMMING."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.PROGRAMMING


@dataclass
class ModeFeatures:
    """
    Feature flags per task mode.
    Controls which validations and features are active.
    """
    # Core features
    syntax_validation: Union[bool, Set[str]] = True  # True, False, or Set of extensions
    db_inspection: bool = True
    http_testing: bool = True
    code_analysis: bool = True
    error_memory: bool = True
    scope_enforcement: bool = True  # Hard blockades via Enforcer Hook
    file_tracking: bool = True

    # Content mode features
    word_count: bool = False
    chapter_tracking: bool = False

    # DevOps mode features
    command_logging: bool = False
    rollback_tracking: bool = False
    config_validation: bool = False  # YAML/JSON/CONF validation

    # Research mode features
    source_tracking: bool = False
    fact_indexing: bool = False


# Task Mode Configuration
TASK_MODE_CONFIG: Dict[TaskMode, ModeFeatures] = {
    TaskMode.PROGRAMMING: ModeFeatures(
        syntax_validation=True,
        db_inspection=True,
        http_testing=True,
        code_analysis=True,
        error_memory=True,
        scope_enforcement=True,
        file_tracking=True,
    ),
    TaskMode.CONTENT: ModeFeatures(
        syntax_validation=False,
        db_inspection=False,
        http_testing=False,
        code_analysis=False,
        error_memory=False,
        scope_enforcement=False,  # No blockades for creative work
        file_tracking=True,
        word_count=True,
        chapter_tracking=True,
    ),
    TaskMode.DEVOPS: ModeFeatures(
        syntax_validation={".yaml", ".yml", ".json", ".conf", ".ini", ".toml", ".env"},
        db_inspection=False,
        http_testing=True,  # For health checks
        code_analysis=False,
        error_memory=True,
        scope_enforcement=False,  # Soft enforcement
        file_tracking=True,
        command_logging=True,
        rollback_tracking=True,
        config_validation=True,
    ),
    TaskMode.RESEARCH: ModeFeatures(
        syntax_validation=False,
        db_inspection=False,
        http_testing=False,
        code_analysis=False,
        error_memory=False,
        scope_enforcement=False,
        file_tracking=True,
        source_tracking=True,
        fact_indexing=True,
    ),
    TaskMode.GENERIC: ModeFeatures(
        syntax_validation=False,
        db_inspection=False,
        http_testing=False,
        code_analysis=False,
        error_memory=False,
        scope_enforcement=False,
        file_tracking=True,
    ),
}


# Context Injection Templates per Mode
TASK_MODE_CONTEXT: Dict[TaskMode, str] = {
    TaskMode.PROGRAMMING: """
────────────────────────────────────────
📋 **PROGRAMMING-MODUS - Pflicht-Aktionen:**

1. `chainguard_track(file="...", ctx="🔗")` nach JEDER Dateiänderung
2. `chainguard_db_schema()` VOR SQL/Migration-Änderungen
3. `chainguard_test_endpoint()` für geänderte Web-Routen
4. `chainguard_finish(confirmed=True)` am Ende

**Syntax-Validierung:** PHP, JS, JSON, Python, TypeScript aktiv
**Blockaden:** Aktiv bei Schema-Dateien ohne DB-Check
────────────────────────────────────────
""",

    TaskMode.CONTENT: """
────────────────────────────────────────
📝 **CONTENT-MODUS - Flexibles Schreiben:**

- **Keine Syntax-Validierung** (Texte, nicht Code)
- **Keine Blockaden** - freies kreatives Arbeiten
- Tracking optional: `chainguard_track(file="kapitel1.md")`
- Word-Count: `chainguard_word_count()`

**Tipp:** Nutze acceptance_criteria als Kapitel-Checkliste!

Beispiel:
```
chainguard_check_criteria(criterion="Kapitel 1", fulfilled=True)
```
────────────────────────────────────────
""",

    TaskMode.DEVOPS: """
────────────────────────────────────────
🖥️ **DEVOPS-MODUS - Server & CLI:**

- **Config-Validierung:** YAML/JSON/CONF aktiv
- **Command-Logging:** Commands werden protokolliert
- **Health-Checks:** `chainguard_test_endpoint()` für Service-Status
- **Checkpoints:** `chainguard_checkpoint()` vor kritischen Änderungen

**Keine Code-Syntax-Blockaden** - fokussiert auf Infrastruktur

Beispiel für WordPress:
```
chainguard_log_command(cmd="wp plugin install woocommerce")
chainguard_test_endpoint(url="https://site.com/wp-admin/")
```
────────────────────────────────────────
""",

    TaskMode.RESEARCH: """
────────────────────────────────────────
🔬 **RESEARCH-MODUS - Recherche & Analyse:**

- **Quellen tracken:** `chainguard_add_source(url="...", title="...")`
- **Fakten indexieren:** `chainguard_index_fact(fact="...", confidence="verified")`
- **Keine Blockaden** - Fokus auf Wissenssammlung

**Tipp:** Nutze acceptance_criteria als Forschungsfragen!

Beispiel:
```
chainguard_add_source(url="https://paper.com", title="AI Study 2025")
chainguard_index_fact(fact="GPT-4 hat 1.7T Parameter", confidence="verified")
```
────────────────────────────────────────
""",

    TaskMode.GENERIC: """
────────────────────────────────────────
⚡ **GENERIC-MODUS - Minimales Tracking:**

- **Alle Validierungen deaktiviert**
- **Keine Blockaden**
- Einfaches Task-Tracking
- `chainguard_status()` für Überblick
- `chainguard_finish()` zum Abschluss
────────────────────────────────────────
""",
}


# XML Context Templates (v6.0)
TASK_MODE_CONTEXT_XML: Dict[TaskMode, Dict[str, Any]] = {
    TaskMode.PROGRAMMING: {
        "mode": "programming",
        "rules": [
            {"priority": 1, "action": "chainguard_track(file=\"...\", ctx=\"🔗\")", "when": "nach JEDER Dateiänderung"},
            {"priority": 2, "action": "chainguard_db_inspect()", "when": "VOR SQL/Migration-Änderungen"},
            {"priority": 3, "action": "chainguard_test_endpoint()", "when": "für geänderte Web-Routen"},
            {"priority": 4, "action": "chainguard_finish(confirmed=True)", "when": "am Ende"}
        ],
        "features": {
            "syntax_validation": {"enabled": True, "types": "PHP, JS, JSON, Python, TypeScript"},
            "db_inspection": {"enabled": True},
            "scope_enforcement": {"enabled": True}
        }
    },
    TaskMode.CONTENT: {
        "mode": "content",
        "rules": [
            {"priority": 1, "action": "chainguard_track(file=\"...\")", "when": "optional nach Änderungen"},
            {"priority": 2, "action": "chainguard_word_count()", "when": "für Fortschritt"},
            {"priority": 3, "action": "chainguard_check_criteria()", "when": "Kapitel abschließen"}
        ],
        "features": {
            "syntax_validation": {"enabled": False},
            "word_count": {"enabled": True},
            "chapter_tracking": {"enabled": True}
        },
        "hints": ["Keine Syntax-Validierung", "Freies kreatives Arbeiten"]
    },
    TaskMode.DEVOPS: {
        "mode": "devops",
        "rules": [
            {"priority": 1, "action": "chainguard_log_command()", "when": "nach CLI-Commands"},
            {"priority": 2, "action": "chainguard_checkpoint()", "when": "vor kritischen Änderungen"},
            {"priority": 3, "action": "chainguard_test_endpoint()", "when": "Service-Status prüfen"}
        ],
        "features": {
            "config_validation": {"enabled": True, "types": "YAML, JSON, CONF"},
            "command_logging": {"enabled": True},
            "health_checks": {"enabled": True}
        },
        "hints": ["Keine Code-Syntax-Blockaden", "Fokus auf Infrastruktur"]
    },
    TaskMode.RESEARCH: {
        "mode": "research",
        "rules": [
            {"priority": 1, "action": "chainguard_add_source(url=\"...\", title=\"...\")", "when": "Quelle gefunden"},
            {"priority": 2, "action": "chainguard_index_fact(fact=\"...\", confidence=\"...\")", "when": "Fakt verifiziert"}
        ],
        "features": {
            "source_tracking": {"enabled": True},
            "fact_indexing": {"enabled": True}
        },
        "hints": ["Keine Blockaden", "Fokus auf Wissenssammlung"]
    },
    TaskMode.GENERIC: {
        "mode": "generic",
        "rules": [
            {"priority": 1, "action": "chainguard_status()", "when": "für Überblick"},
            {"priority": 2, "action": "chainguard_finish()", "when": "zum Abschluss"}
        ],
        "features": {
            "file_tracking": {"enabled": True}
        },
        "hints": ["Alle Validierungen deaktiviert", "Minimales Tracking"]
    }
}


def get_mode_context_xml(mode: TaskMode) -> Dict[str, Any]:
    """Get XML-structured context for a task mode."""
    return TASK_MODE_CONTEXT_XML.get(mode, TASK_MODE_CONTEXT_XML[TaskMode.PROGRAMMING])


# Mode Detection Keywords (for auto-detection)
MODE_DETECTION_KEYWORDS: Dict[TaskMode, Set[str]] = {
    TaskMode.CONTENT: {
        "buch", "book", "kapitel", "chapter", "artikel", "article",
        "text", "schreib", "write", "dokumentation", "documentation",
        "readme", "blog", "story", "roman", "novel", "essay"
    },
    TaskMode.DEVOPS: {
        "server", "nginx", "apache", "docker", "kubernetes", "k8s",
        "deploy", "wordpress", "wp-cli", "ssh", "config", "konfigur",
        "install", "setup", "admin", "infrastructure", "infra",
        "ansible", "terraform", "ci/cd", "pipeline", "backup"
    },
    TaskMode.RESEARCH: {
        "recherche", "research", "analyse", "analysis", "vergleich",
        "comparison", "untersuche", "investigate", "evaluate", "studie",
        "study", "report", "bericht", "markt", "market"
    },
}


def detect_task_mode(description: str, working_dir: str = "") -> TaskMode:
    """
    Auto-detect task mode from description and working directory.

    This is a HINT for the LLM - the actual decision is made by the LLM
    based on the tool description. This function provides a fallback
    for cases where no explicit mode is given.

    Returns: TaskMode (defaults to PROGRAMMING if uncertain)
    """
    desc_lower = description.lower()

    # 1. Keyword-based detection from description
    for mode, keywords in MODE_DETECTION_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return mode

    # 2. File-based detection from working directory
    if working_dir:
        path = Path(working_dir)

        try:
            # WordPress project?
            if (path / "wp-config.php").exists() or (path / "wp-content").exists():
                return TaskMode.DEVOPS

            # Server config directory?
            path_str = str(path).lower()
            if any(p in path_str for p in ["/etc/nginx", "/etc/apache", "/var/www/html"]):
                return TaskMode.DEVOPS

            # Documentation/book project?
            md_files = list(path.glob("*.md")) + list(path.glob("**/*.md"))
            code_files = (list(path.glob("*.py")) + list(path.glob("*.js")) +
                         list(path.glob("*.php")) + list(path.glob("*.ts")))

            # If mostly markdown files, likely content project
            if len(md_files) > 5 and len(code_files) < 3:
                return TaskMode.CONTENT

            # Code project with package manager
            if ((path / "package.json").exists() or
                (path / "composer.json").exists() or
                (path / "requirements.txt").exists() or
                (path / "Cargo.toml").exists()):
                return TaskMode.PROGRAMMING

        except (OSError, PermissionError):
            pass  # Ignore file system errors

    # 3. Default to programming (most common use case)
    return TaskMode.PROGRAMMING


def get_mode_features(mode: TaskMode) -> ModeFeatures:
    """Get feature flags for a given task mode."""
    return TASK_MODE_CONFIG.get(mode, TASK_MODE_CONFIG[TaskMode.PROGRAMMING])


def get_mode_context(mode: TaskMode) -> str:
    """Get context injection text for a given task mode."""
    return TASK_MODE_CONTEXT.get(mode, TASK_MODE_CONTEXT[TaskMode.PROGRAMMING])


def should_validate_syntax(mode: TaskMode, file_path: str) -> bool:
    """
    Check if syntax validation should run for a file in the given mode.

    Returns True if:
    - Mode has syntax_validation=True (validate all)
    - Mode has syntax_validation as Set and file extension matches
    """
    features = get_mode_features(mode)

    if features.syntax_validation is True:
        return True
    elif features.syntax_validation is False:
        return False
    elif isinstance(features.syntax_validation, set):
        ext = Path(file_path).suffix.lower()
        return ext in features.syntax_validation

    return False


# =============================================================================
# Constants
# =============================================================================
# Scope Limits
MAX_DESCRIPTION_LENGTH = 500
DESCRIPTION_PREVIEW_LENGTH = 200

# List Limits (prevent unbounded growth)
MAX_OUT_OF_SCOPE_FILES = 20
MAX_CHANGED_FILES = 30
MAX_RECENT_ACTIONS = 5
MAX_PROJECTS_IN_CACHE = 20

# Performance Tuning
DEBOUNCE_DELAY_SECONDS = 0.5
GIT_CACHE_TTL_SECONDS = 300
SYNTAX_CHECK_TIMEOUT_SECONDS = 10
HTTP_REQUEST_TIMEOUT_SECONDS = 10

# Batch Limits
MAX_BATCH_FILES = 50

# Test Runner (v4.10)
TEST_RUN_TIMEOUT_SECONDS = 300  # 5 Minuten max für Tests
TEST_OUTPUT_MAX_LENGTH = 2000   # Max Zeichen für Output-Speicherung
TEST_FAILED_LINES_MAX = 10      # Max Fehlerzeilen in Zusammenfassung

# Error Memory / History (v4.11)
HISTORY_MAX_ENTRIES = 500       # Max entries per history file
ERROR_INDEX_MAX_ENTRIES = 100   # Max errors in index
SIMILARITY_THRESHOLD = 0.6      # For fuzzy matching errors
AUTO_SUGGEST_MAX_RESULTS = 2    # Max suggestions to show on error

# Database Inspector (v4.12)
DB_SCHEMA_CACHE_TTL = 300       # 5 minutes cache for schema
DB_SAMPLE_ROWS = 5              # Sample rows to show
DB_MAX_TABLES = 50              # Max tables to load

# DB Schema Check Enforcement (v4.18)
DB_SCHEMA_CHECK_TTL = 600       # 10 minutes - after this, schema check is considered stale
DB_SCHEMA_PATTERNS = [          # File patterns that trigger schema invalidation
    '.sql', 'migration', 'migrate', 'schema', 'database',
    '/migrations/', '/db/', 'seed', 'alter_', 'create_'
]

# Context-Check Feature (v4.6)
CONTEXT_MARKER = "🔗"
CONTEXT_REFRESH_TEXT = """
⚠️ CHAINGUARD CONTEXT REFRESH

Wichtige Regeln (Kontext war verloren):
1. chainguard_track(file="...", ctx="🔗") nach JEDER Dateiänderung
2. chainguard_validate(status="PASS") am Task-Ende
3. ctx="🔗" bei JEDEM Chainguard-Tool mitgeben!

Beispiel: chainguard_status(ctx="🔗")
"""

# Scope-Blockade Feature (v4.9)
SCOPE_REQUIRED_TOOLS = {
    "chainguard_set_scope",  # Immer erlaubt
    "chainguard_projects",   # Immer erlaubt (read-only)
    "chainguard_config",     # Immer erlaubt (admin)
}

SCOPE_BLOCKED_TEXT = """
❌ BLOCKIERT - KEIN SCOPE GESETZT!

Du MUSST zuerst chainguard_set_scope() aufrufen!

Beispiel:
```
chainguard_set_scope(
    description="Was du baust",
    working_dir="/pfad/zum/projekt",
    acceptance_criteria=["Kriterium 1"]
)
```

Erst DANACH kannst du andere Chainguard-Tools nutzen.
"""

# Paths
CHAINGUARD_HOME = Path(os.environ.get("CHAINGUARD_HOME", Path.home() / ".chainguard"))
CHAINGUARD_HOME.mkdir(parents=True, exist_ok=True)
(CHAINGUARD_HOME / "projects").mkdir(exist_ok=True)


# =============================================================================
# Logging (with rotation: 5 files x 1MB max)
# =============================================================================
_log_handler = RotatingFileHandler(
    CHAINGUARD_HOME / "mcp-server.log",
    maxBytes=1024 * 1024,  # 1MB
    backupCount=5
)
_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger("chainguard")
logger.setLevel(logging.INFO)
logger.addHandler(_log_handler)


# =============================================================================
# Configuration Class
# =============================================================================
@dataclass
class ChainguardConfig:
    """Minimal configuration."""
    validation_reminder_threshold: int = 8
    max_log_entries: int = 50
    cleanup_inactive_days: int = 30

    @classmethod
    def load(cls) -> "ChainguardConfig":
        config_path = CHAINGUARD_HOME / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                    return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        return cls()

    def save(self):
        with open(CHAINGUARD_HOME / "config.json", 'w') as f:
            json.dump(asdict(self), f, indent=2)


# Global config instance
CONFIG = ChainguardConfig.load()
