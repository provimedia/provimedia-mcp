# CHAINGUARD MCP Server v5.0.0 - Deep Dive Dokumentation

> **Letzte Aktualisierung:** 2026-01-08
> **Version:** 5.0.0
> **Autor:** Auto-generiert durch Deep Dive Analyse

---

## Inhaltsverzeichnis

1. [Architektur-Übersicht](#1-architektur-übersicht)
2. [Task-Mode System (v5.0)](#2-task-mode-system-v50)
3. [Modulare Struktur](#3-modulare-struktur)
4. [Datenmodelle (models.py)](#4-datenmodelle-modelspy)
5. [Konfiguration (config.py)](#5-konfiguration-configpy)
6. [Cache-System (cache.py)](#6-cache-system-cachepy)
7. [Project Manager (project_manager.py)](#7-project-manager-project_managerpy)
8. [Handler-System (handlers.py)](#8-handler-system-handlerspy)
9. [Tool-Definitionen (tools.py)](#9-tool-definitionen-toolspy)
10. [Syntax-Validierung (validators.py)](#10-syntax-validierung-validatorspy)
11. [Code-Analyse (analyzers.py)](#11-code-analyse-analyzerspy)
12. [HTTP Session Management (http_session.py)](#12-http-session-management-http_sessionpy)
13. [Test Runner (test_runner.py)](#13-test-runner-test_runnerpy)
14. [Error Memory System (history.py)](#14-error-memory-system-historypy)
15. [Database Inspector (db_inspector.py)](#15-database-inspector-db_inspectorpy)
16. [Checklist Runner (checklist.py)](#16-checklist-runner-checklistpy)
17. [Utilities (utils.py)](#17-utilities-utilspy)
18. [Server (server.py)](#18-server-serverpy)
19. [Enforcer Hook](#19-enforcer-hook)
20. [Alle Tools im Detail](#20-alle-tools-im-detail)
21. [Flowcharts](#21-flowcharts)

---

## 1. Architektur-Übersicht

### 1.1 Design-Prinzipien

- **Minimaler Kontextverbrauch**: Token-effiziente Responses
- **Maximale Performance**: Async I/O, Debouncing, Caching
- **Modulare Struktur**: Einzelne Module lesbar (nicht 31K+ Tokens)
- **Handler-Registry Pattern**: Testbar und erweiterbar

### 1.2 Verzeichnisstruktur

```
~/.chainguard/
├── chainguard_mcp.py          # Wrapper (importiert Package)
├── chainguard/                 # Modulares Package
│   ├── __init__.py            # Exports (163 Zeilen)
│   ├── __main__.py            # Entry Point (8 Zeilen)
│   ├── server.py              # MCP Server Setup (145 Zeilen)
│   ├── handlers.py            # Handler-Registry Pattern (1251 Zeilen)
│   ├── tools.py               # Tool Definitionen (422 Zeilen)
│   ├── models.py              # Dataclasses (404 Zeilen)
│   ├── project_manager.py     # Projekt-CRUD (440 Zeilen)
│   ├── validators.py          # Syntax-Checks (195 Zeilen)
│   ├── analyzers.py           # Code-Analyse (391 Zeilen)
│   ├── http_session.py        # HTTP/Login (347 Zeilen)
│   ├── test_runner.py         # Test-Ausführung (408 Zeilen)
│   ├── history.py             # Error Memory (603 Zeilen)
│   ├── db_inspector.py        # Database Inspector (681 Zeilen)
│   ├── cache.py               # LRU + TTL-LRU Cache (190 Zeilen)
│   ├── checklist.py           # Async Checklist (161 Zeilen)
│   ├── config.py              # Konstanten (197 Zeilen)
│   └── utils.py               # Hilfsfunktionen (50 Zeilen)
├── hooks/
│   └── chainguard_enforcer.py # PreToolUse Hook (271 Zeilen)
├── projects/                   # Projekt-Daten
│   └── {project_id}/
│       ├── state.json         # Projekt-State
│       ├── enforcement-state.json  # Für Hook
│       ├── history.jsonl      # Änderungs-Log
│       └── error_index.json   # Fehler-Index
├── config.json                # Globale Konfiguration
└── mcp-server.log             # Log-Datei (rotierend)
```

### 1.3 Abhängigkeiten

**Pflicht:**
- `mcp` - MCP Protocol Implementation
- `aiofiles` - Async File I/O

**Optional:**
- `aiohttp` - HTTP Client (Fallback: urllib)
- `aiomysql` - MySQL Support
- `asyncpg` - PostgreSQL Support
- `aiosqlite` - SQLite Support

---

## 2. Task-Mode System (v5.0)

### 2.1 Übersicht

Das Task-Mode System ist das fundamentale neue Feature von v5.0. Es löst das Problem, dass Chainguard zu Code-zentrisch war - Syntax-Validierung, DB-Schema-Checks und HTTP-Tests sind sinnvoll für Programmierung, aber störend bei anderen Aufgaben wie Bücher schreiben, Server verwalten oder Recherche.

### 2.2 Die 5 Modi

| Modus | Beschreibung | Typische Aufgaben |
|-------|--------------|-------------------|
| **programming** | Standard-Modus für Code-Arbeit | Features implementieren, Bugs fixen, Refactoring |
| **content** | Flexibles Schreiben ohne Blockaden | Bücher, Artikel, Dokumentation |
| **devops** | Server- und Infrastruktur-Arbeit | Server einrichten, WordPress, CLI-Tools |
| **research** | Recherche und Analyse | Marktanalyse, Wettbewerbsforschung, Fact-Finding |
| **generic** | Minimales Tracking | Alles andere |

### 2.3 Feature-Matrix

| Feature | programming | content | devops | research | generic |
|---------|:-----------:|:-------:|:------:|:--------:|:-------:|
| Syntax-Validierung | ✓ | - | - | - | - |
| DB-Pflicht | ✓ | - | - | - | - |
| HTTP-Tests | ✓ | - | ✓ | - | - |
| Scope-Enforcement | ✓ | - | ✓ | - | - |
| File-Tracking | ✓ | ✓ | ✓ | - | ✓ |
| Word-Count | - | ✓ | - | - | - |
| Chapter-Tracking | - | ✓ | - | - | - |
| Command-Logging | - | - | ✓ | - | - |
| Checkpoints | - | - | ✓ | - | - |
| Health-Checks | - | - | ✓ | - | - |
| Source-Tracking | - | - | - | ✓ | - |
| Fact-Indexing | - | - | - | ✓ | - |

### 2.4 Modus-Auswahl

Der Modus wird durch das LLM (Claude) bei `chainguard_set_scope()` bestimmt:

```
┌─────────────────────────────────────────────────┐
│  User: "Schreibe Kapitel 3 meines Buches"       │
│       ↓                                          │
│  Claude (LLM) liest Tool-Description            │
│       ↓                                          │
│  LLM erkennt: Buch → CONTENT Modus              │
│       ↓                                          │
│  chainguard_set_scope(mode="content", ...)      │
│       ↓                                          │
│  - Keine Syntax-Blockaden ✓                      │
│  - Word-Count verfügbar ✓                        │
│  - Kapitel-Tracking ✓                            │
└─────────────────────────────────────────────────┘
```

**Entscheidungshilfe für das LLM:**

| User-Request enthält... | → Modus |
|------------------------|---------|
| "Code", "Feature", "Bug", "implementieren" | programming |
| "Kapitel", "Buch", "Artikel", "schreiben" | content |
| "Server", "WordPress", "Nginx", "einrichten" | devops |
| "recherchieren", "analysieren", "herausfinden" | research |
| Unklar | generic |

### 2.5 Context Injection

Jeder Modus injiziert spezifische Anweisungen bei `set_scope`:

#### Programming Mode

```
────────────────────────────────────────
📋 **PFLICHT-AKTIONEN FÜR DIESEN TASK:**

1. `chainguard_track(file="...", ctx="🔗")` nach JEDER Dateiänderung
2. `chainguard_db_schema()` VOR DB-Arbeit
3. `chainguard_test_endpoint()` bei Web-Änderungen
4. `chainguard_finish(confirmed=True)` am Ende

Bei Fehler: `chainguard_recall(query="...")` für Auto-Suggest!
────────────────────────────────────────
```

#### Content Mode

```
────────────────────────────────────────
📝 **CONTENT-MODUS - Flexibles Schreiben:**

- **Keine Syntax-Validierung** (Texte, nicht Code)
- **Keine Blockaden** - freies kreatives Arbeiten
- Tracking optional: `chainguard_track(file="kapitel1.md")`
- Word-Count: `chainguard_word_count()`

**Tipp:** Nutze acceptance_criteria als Kapitel-Checkliste!
────────────────────────────────────────
```

#### DevOps Mode

```
────────────────────────────────────────
🔧 **DEVOPS-MODUS - Infrastruktur-Arbeit:**

- Command-Logging: `chainguard_log_command(command="...")`
- Checkpoints: `chainguard_checkpoint(name="vor-nginx-config")`
- Health-Checks: `chainguard_health_check(endpoints=[...])`

**Empfehlung:** Checkpoint VOR kritischen Änderungen!
────────────────────────────────────────
```

#### Research Mode

```
────────────────────────────────────────
🔍 **RESEARCH-MODUS - Strukturierte Recherche:**

- Quellen tracken: `chainguard_add_source(url="...", relevance="high")`
- Fakten indexieren: `chainguard_index_fact(fact="...", confidence="verified")`
- Übersicht: `chainguard_sources()`, `chainguard_facts()`

**Keine Blockaden** - fokussiere dich auf die Recherche!
────────────────────────────────────────
```

### 2.6 Mode-spezifische Tools

#### Content Mode Tools

| Tool | Parameter | Beschreibung |
|------|-----------|--------------|
| `chainguard_word_count` | file (optional) | Zeigt Wort-Zählung für Scope oder einzelne Datei |
| `chainguard_track_chapter` | chapter, status, word_count | Trackt Kapitel-Status (draft/review/done) |

**Beispiel:**
```python
chainguard_word_count()
# → 📊 Word Count:
#    - Total: 15,234 words
#    - kapitel1.md: 3,500 words
#    - kapitel2.md: 4,200 words

chainguard_track_chapter(chapter="Kapitel 3", status="draft", word_count=2500)
# → ✓ Kapitel 3: draft (2,500 words)
```

#### DevOps Mode Tools

| Tool | Parameter | Beschreibung |
|------|-----------|--------------|
| `chainguard_log_command` | command, result, output | Protokolliert CLI-Command mit Ergebnis |
| `chainguard_checkpoint` | name, files | Erstellt Rollback-Checkpoint |
| `chainguard_health_check` | endpoints, services | Prüft Verfügbarkeit |

**Beispiel:**
```python
chainguard_checkpoint(name="vor-nginx-config", files=["/etc/nginx/nginx.conf"])
# → ✓ Checkpoint: vor-nginx-config
#    Files: /etc/nginx/nginx.conf

chainguard_log_command(command="systemctl restart nginx", result="success")
# → ✓ Logged: systemctl restart nginx (success)

chainguard_health_check(endpoints=["http://localhost:80"], services=["nginx"])
# → 🏥 Health Check:
#    - http://localhost:80: ✓ 200 OK
#    - nginx.service: ✓ active (running)
```

#### Research Mode Tools

| Tool | Parameter | Beschreibung |
|------|-----------|--------------|
| `chainguard_add_source` | url, title, relevance | Fügt Quelle mit Relevanz hinzu |
| `chainguard_index_fact` | fact, source, confidence | Indexiert Fakt mit Konfidenz-Level |
| `chainguard_sources` | - | Listet alle Quellen nach Relevanz |
| `chainguard_facts` | - | Listet alle Fakten nach Konfidenz |

**Beispiel:**
```python
chainguard_add_source(
    url="https://example.com/report",
    title="Market Analysis 2025",
    relevance="high"
)
# → ✓ Source added: Market Analysis 2025 (high)

chainguard_index_fact(
    fact="Market share increased 15% YoY",
    source="Market Analysis 2025",
    confidence="verified"
)
# → ✓ Fact indexed (verified): Market share increased 15% YoY

chainguard_sources()
# → 📚 Sources (3):
#    HIGH:
#    - Market Analysis 2025 (https://example.com/report)
#    MEDIUM:
#    - Industry Overview (https://...)

chainguard_facts()
# → 📋 Facts (5):
#    VERIFIED:
#    - Market share increased 15% YoY
#    LIKELY:
#    - Competition expected to respond in Q2
```

### 2.7 Implementation Details

#### TaskMode Enum

```python
class TaskMode(str, Enum):
    PROGRAMMING = "programming"
    CONTENT = "content"
    DEVOPS = "devops"
    RESEARCH = "research"
    GENERIC = "generic"
```

#### ModeFeatures Dataclass

```python
@dataclass
class ModeFeatures:
    syntax_validation: bool = True
    db_enforcement: bool = True
    http_enforcement: bool = True
    scope_enforcement: bool = True
    file_tracking: bool = True

    # Content-specific
    word_count: bool = False
    chapter_tracking: bool = False

    # DevOps-specific
    command_logging: bool = False
    checkpoints: bool = False
    health_checks: bool = False

    # Research-specific
    source_tracking: bool = False
    fact_indexing: bool = False

    @classmethod
    def for_mode(cls, mode: TaskMode) -> "ModeFeatures":
        """Return feature set for given mode."""
```

#### Feature-Konfiguration pro Modus

```python
MODE_FEATURES = {
    TaskMode.PROGRAMMING: ModeFeatures(
        syntax_validation=True,
        db_enforcement=True,
        http_enforcement=True,
        scope_enforcement=True,
        file_tracking=True
    ),
    TaskMode.CONTENT: ModeFeatures(
        syntax_validation=False,
        db_enforcement=False,
        http_enforcement=False,
        scope_enforcement=False,
        file_tracking=True,
        word_count=True,
        chapter_tracking=True
    ),
    TaskMode.DEVOPS: ModeFeatures(
        syntax_validation=False,
        db_enforcement=False,
        http_enforcement=True,
        scope_enforcement=True,
        file_tracking=True,
        command_logging=True,
        checkpoints=True,
        health_checks=True
    ),
    TaskMode.RESEARCH: ModeFeatures(
        syntax_validation=False,
        db_enforcement=False,
        http_enforcement=False,
        scope_enforcement=False,
        file_tracking=False,
        source_tracking=True,
        fact_indexing=True
    ),
    TaskMode.GENERIC: ModeFeatures(
        syntax_validation=False,
        db_enforcement=False,
        http_enforcement=False,
        scope_enforcement=False,
        file_tracking=True
    )
}
```

### 2.8 Backwards-Kompatibilität

- **Default-Mode ist `programming`** - bestehende Workflows funktionieren unverändert
- **Alle v4.x Tools bleiben verfügbar** - keine Breaking Changes
- **Mode ist optional** - kann weggelassen werden

```python
# v4.x Stil - funktioniert weiterhin (mode=programming)
chainguard_set_scope(description="Feature X implementieren")

# v5.0 Stil - expliziter Modus
chainguard_set_scope(description="Kapitel schreiben", mode="content")
```

---

## 3. Modulare Struktur

### 3.1 Import-Hierarchie

```
chainguard_mcp.py
    └── chainguard/server.py
        ├── chainguard/tools.py
        ├── chainguard/handlers.py
        │   ├── chainguard/models.py
        │   ├── chainguard/project_manager.py
        │   ├── chainguard/validators.py
        │   ├── chainguard/analyzers.py
        │   ├── chainguard/http_session.py
        │   ├── chainguard/test_runner.py
        │   ├── chainguard/history.py
        │   ├── chainguard/db_inspector.py
        │   └── chainguard/checklist.py
        └── chainguard/config.py
            └── chainguard/cache.py
```

### 3.2 Exports (__init__.py)

```python
__all__ = [
    # Version
    "VERSION", "__version__",

    # Enums
    "Phase", "ValidationStatus",

    # Config
    "CONFIG", "CHAINGUARD_HOME", "logger",

    # Models
    "ScopeDefinition", "ProjectState",

    # Managers
    "ProjectManager", "project_manager",
    "HTTPSessionManager", "http_session_manager",

    # Validators & Analyzers
    "SyntaxValidator", "ChecklistRunner",
    "CodeAnalyzer", "ImpactAnalyzer",

    # Cache
    "LRUCache", "TTLLRUCache", "AsyncFileLock", "GitCache", "git_cache",

    # Handlers
    "HandlerRegistry",

    # Test Runner
    "TestRunner", "TestConfig", "TestResult",

    # History
    "HistoryManager", "HistoryEntry", "ErrorEntry", "format_auto_suggest",

    # Database Inspector
    "DBInspector", "DBConfig", "get_inspector", "clear_inspector",

    # Server
    "main", "run", "server",
]
```

---

## 4. Datenmodelle (models.py)

### 4.1 ScopeDefinition

Definiert die Scope-Grenzen für einen Development-Task.

```python
@dataclass
class ScopeDefinition:
    description: str = ""           # Task-Beschreibung
    modules: List[str] = []         # Datei-Patterns im Scope
    acceptance_criteria: List[str] = []  # Akzeptanzkriterien
    checklist: List[Dict[str, Any]] = []  # Automatische Checks
    created_at: str = ""            # ISO Timestamp
```

### 4.2 ProjectState

Repräsentiert den kompletten State eines getrackten Projekts.

```python
@dataclass
class ProjectState:
    # Identifikation
    project_id: str                 # SHA256-Hash (16 Zeichen)
    project_name: str               # Verzeichnisname
    project_path: str               # Absoluter Pfad

    # Phase
    phase: str = "unknown"          # planning/implementation/testing/review/done
    current_task: str = ""

    # Counters
    files_changed: int = 0
    files_since_validation: int = 0
    validations_passed: int = 0
    validations_failed: int = 0

    # Timestamps
    last_validation: str = ""
    last_activity: str = ""
    session_start: str = ""

    # Core Features
    scope: Optional[ScopeDefinition] = None
    criteria_status: Dict[str, bool] = {}
    alerts: List[Dict[str, Any]] = []
    out_of_scope_files: List[str] = []
    checklist_results: Dict[str, bool] = {}
    recent_actions: List[str] = []      # Max 5, Format: "HH:MM action"

    # HTTP Testing
    http_base_url: str = ""
    http_credentials: Dict[str, str] = {}
    http_tests_performed: int = 0

    # Impact-Check
    changed_files: List[str] = []       # Max 30
    impact_check_pending: bool = False

    # Test Runner (v4.10)
    test_config: Dict[str, Any] = {}    # {command, args, timeout}
    test_results: Dict[str, Any] = {}
    last_test_run: str = ""
    tests_passed: int = 0
    tests_failed: int = 0

    # Database Inspector (v4.12)
    db_config: Dict[str, Any] = {}
    db_schema_checked_at: str = ""      # v4.18: ISO Timestamp
```

### 4.3 Wichtige Methoden

| Methode | Beschreibung |
|---------|--------------|
| `to_json()` | Serialisiert State zu JSON |
| `from_dict(data)` | Deserialisiert mit Migration alter Formate |
| `needs_validation()` | True wenn files_since_validation >= threshold |
| `is_schema_checked()` | True wenn Schema-Check noch gültig (innerhalb TTL) |
| `get_schema_check_age()` | Alter des Schema-Checks in Sekunden |
| `invalidate_schema_check()` | Invalidiert Schema-Check (bei .sql-Änderung) |
| `set_schema_checked()` | Setzt Schema-Check Timestamp |
| `is_schema_file(path)` | Prüft ob Datei schema-relevant |
| `check_file_in_scope(path)` | Prüft ob Datei im Scope |
| `add_action(action)` | Fügt Action zu recent_actions hinzu |
| `get_status_line()` | Ultra-kompakte Status-Zeile |
| `get_completion_status()` | Prüft alle Abschluss-Bedingungen |
| `add_changed_file(name)` | Trackt geänderte Datei |
| `add_out_of_scope_file(path)` | Trackt OOS-Datei |
| `_check_http_test_needed()` | Prüft ob HTTP-Tests erforderlich |

---

## 5. Konfiguration (config.py)

### 5.1 Konstanten

```python
# Version
VERSION = "4.19.1"

# Scope Limits
MAX_DESCRIPTION_LENGTH = 500
DESCRIPTION_PREVIEW_LENGTH = 200

# List Limits
MAX_OUT_OF_SCOPE_FILES = 20
MAX_CHANGED_FILES = 30
MAX_RECENT_ACTIONS = 5
MAX_PROJECTS_IN_CACHE = 20

# Performance
DEBOUNCE_DELAY_SECONDS = 0.5
GIT_CACHE_TTL_SECONDS = 300
SYNTAX_CHECK_TIMEOUT_SECONDS = 10
HTTP_REQUEST_TIMEOUT_SECONDS = 10

# Batch
MAX_BATCH_FILES = 50

# Test Runner
TEST_RUN_TIMEOUT_SECONDS = 300
TEST_OUTPUT_MAX_LENGTH = 2000
TEST_FAILED_LINES_MAX = 10

# Error Memory
HISTORY_MAX_ENTRIES = 500
ERROR_INDEX_MAX_ENTRIES = 100
SIMILARITY_THRESHOLD = 0.6
AUTO_SUGGEST_MAX_RESULTS = 2

# Database
DB_SCHEMA_CACHE_TTL = 300
DB_SAMPLE_ROWS = 5
DB_MAX_TABLES = 50

# Schema Check Enforcement (v4.18)
DB_SCHEMA_CHECK_TTL = 600  # 10 Minuten
DB_SCHEMA_PATTERNS = ['.sql', 'migration', 'migrate', 'schema', 'database', ...]
```

### 5.2 Enums

```python
class Phase(str, Enum):
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    DONE = "done"
    UNKNOWN = "unknown"

class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
```

### 5.3 ChainguardConfig

```python
@dataclass
class ChainguardConfig:
    validation_reminder_threshold: int = 8
    max_log_entries: int = 50
    cleanup_inactive_days: int = 30

    @classmethod
    def load(cls) -> "ChainguardConfig"

    def save(self)
```

### 5.4 Context-Check Feature (v4.6)

```python
CONTEXT_MARKER = "🔗"
CONTEXT_REFRESH_TEXT = """
⚠️ CHAINGUARD CONTEXT REFRESH

Wichtige Regeln (Kontext war verloren):
1. chainguard_track(file="...", ctx="🔗") nach JEDER Dateiänderung
2. chainguard_validate(status="PASS") am Task-Ende
3. ctx="🔗" bei JEDEM Chainguard-Tool mitgeben!
"""
```

### 5.5 Scope-Blockade Feature (v4.9)

```python
SCOPE_REQUIRED_TOOLS = {
    "chainguard_set_scope",  # Immer erlaubt
    "chainguard_projects",   # Immer erlaubt
    "chainguard_config",     # Immer erlaubt
}

SCOPE_BLOCKED_TEXT = """
❌ BLOCKIERT - KEIN SCOPE GESETZT!
...
"""
```

---

## 6. Cache-System (cache.py)

### 6.1 LRUCache

Memory-bounded LRU Cache basierend auf OrderedDict.

```python
class LRUCache(OrderedDict):
    def __init__(self, maxsize: int = 20):
        self.maxsize = maxsize

    def __getitem__(self, key):
        # Move to end on access
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        # Evict oldest if over size
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]
```

### 6.2 TTLLRUCache

LRU Cache mit Time-To-Live Support.

```python
class TTLLRUCache(Generic[T]):
    def __init__(self, maxsize: int = 20, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, T]
        self._timestamps: Dict[str, float]
        self.maxsize = maxsize
        self.ttl = ttl_seconds

    def __contains__(self, key: str) -> bool
    def _is_expired(self, key: str) -> bool
    def _remove(self, key: str)
    def get(self, key: str, default: T = None) -> Optional[T]
    def set(self, key: str, value: T)
    def invalidate(self, key: str)
    def clear(self)
    def cleanup_expired(self) -> int  # Returns count removed
    def items(self)  # Iterator over non-expired items
```

### 6.3 AsyncFileLock

Non-blocking async File Lock per Path.

```python
class AsyncFileLock:
    _locks: Dict[str, asyncio.Lock] = {}
    _global_lock: Optional[asyncio.Lock] = None  # Lazy init (v4.19.1)

    @classmethod
    def _get_or_create_global_lock(cls) -> asyncio.Lock

    @classmethod
    async def acquire(cls, path: Path) -> asyncio.Lock

    @classmethod
    async def cleanup_unused(cls, keep_paths: Set[str])
```

**v4.19.1 Fix:** Lazy Initialization des Global Lock um Fehler in Python 3.10+/3.12+ zu vermeiden.

### 6.4 GitCache

Cache für Git Subprocess Results.

```python
class GitCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple]  # (result, timestamp)
        self.ttl = ttl_seconds

    def get(self, path: str) -> Optional[str]
    def set(self, path: str, result: str)
    def invalidate(self, path: str)
```

---

## 7. Project Manager (project_manager.py)

### 7.1 Übersicht

Der ProjectManager verwaltet Projekt-States mit High-End Optimierungen:
- LRU Cache mit Size Limit
- Async I/O (non-blocking)
- Write Debouncing (batched saves)
- Git Call Caching

### 7.2 Klasse ProjectManager

```python
class ProjectManager:
    def __init__(self):
        self.cache: LRUCache = LRUCache(maxsize=20)
        self._default_project_id: Optional[str] = None
        self._dirty: Set[str] = set()
        self._save_task: Optional[asyncio.Task] = None
        self._debounce_delay: float = 0.5
```

### 7.3 Methoden

| Methode | Beschreibung |
|---------|--------------|
| `_get_project_id_async(path)` | Berechnet Project ID (async) |
| `_get_project_id_sync(path)` | Berechnet Project ID (sync fallback) |
| `_get_state_path(project_id)` | Pfad zur state.json |
| `resolve_working_dir_async(working_dir)` | Löst working_dir auf |
| `_path_exists_async(path)` | Async path.exists() |
| `_makedirs_async(path)` | Async makedirs |
| `get_async(working_dir)` | Lädt/erstellt ProjectState |
| `save_async(state, immediate)` | Speichert State (debounced) |
| `_debounced_save()` | Führt verzögertes Speichern aus |
| `_write_state(state)` | Schreibt State auf Disk |
| `_write_enforcement_state(state)` | Schreibt enforcement-state.json |
| `flush()` | Force flush aller pending saves |
| `list_all_projects_async()` | Listet alle Projekte |

### 7.4 Project ID Berechnung

Die Project ID wird wie folgt berechnet (Reihenfolge):

1. **Git Remote URL Hash** - `git remote get-url origin`
2. **Git Root Path Hash** - `git rev-parse --show-toplevel`
3. **Working Dir Path Hash** - Fallback

```python
result = hashlib.sha256(source.encode()).hexdigest()[:16]
```

### 7.5 Enforcement State

Der ProjectManager schreibt automatisch `enforcement-state.json` für den PreToolUse Hook:

```python
enforcement_data = {
    "project_id": state.project_id,
    "has_scope": state.scope is not None,
    "db_schema_checked_at": state.db_schema_checked_at,
    "http_tests_performed": state.http_tests_performed,
    "blocking_alerts": [...],
    "phase": state.phase,
    "updated_at": datetime.now().isoformat()
}
```

---

## 8. Handler-System (handlers.py)

### 8.1 HandlerRegistry

Das Handler-Registry Pattern ermöglicht testbare und erweiterbare Tool-Handler.

```python
HandlerFunc = Callable[[Dict[str, Any]], Awaitable[List[TextContent]]]

class HandlerRegistry:
    _handlers: Dict[str, HandlerFunc] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a handler function."""
        def decorator(func: HandlerFunc) -> HandlerFunc:
            cls._handlers[name] = func
            return func
        return decorator

    @classmethod
    async def dispatch(cls, name: str, args: Dict[str, Any]) -> List[TextContent]:
        """Dispatch a tool call to its registered handler."""
        # v4.9: Scope-Blockade
        if name not in SCOPE_REQUIRED_TOOLS:
            state = await pm.get_async(working_dir)
            if not state.scope:
                return [TextContent(type="text", text=SCOPE_BLOCKED_TEXT)]

        handler = cls._handlers.get(name)
        if handler:
            return await handler(args)
        return [TextContent(type="text", text=f"Unknown: {name}")]

    @classmethod
    def list_handlers(cls) -> List[str]
```

### 8.2 Handler-Registrierung

```python
@handler.register("chainguard_track")
async def handle_track(args: Dict[str, Any]) -> List[TextContent]:
    """Track file change with auto-validation and Error Memory."""
    ...
```

### 8.3 Alle registrierten Handler

| Handler | Zeilen | Beschreibung |
|---------|--------|--------------|
| `handle_set_scope` | 117-206 | Definiert Task-Scope |
| `handle_track` | 208-326 | Trackt Dateiänderung |
| `handle_track_batch` | 328-424 | Trackt mehrere Dateien |
| `handle_status` | 426-437 | Kompakter Status |
| `handle_context` | 439-483 | Voller Kontext |
| `handle_set_phase` | 485-509 | Setzt Phase |
| `handle_run_checklist` | 515-532 | Führt Checklist aus |
| `handle_check_criteria` | 534-557 | Prüft Kriterien |
| `handle_validate` | 559-593 | Speichert Validation |
| `handle_alert` | 599-611 | Fügt Alert hinzu |
| `handle_clear_alerts` | 613-623 | Bestätigt Alerts |
| `handle_projects` | 629-637 | Listet Projekte |
| `handle_config` | 639-646 | Zeigt/setzt Config |
| `handle_test_endpoint` | 652-695 | HTTP-Test |
| `handle_login` | 697-746 | Login mit Session |
| `handle_set_base_url` | 748-758 | Base-URL setzen |
| `handle_clear_session` | 760-771 | Session löschen |
| `handle_analyze` | 777-793 | Code-Analyse |
| `handle_finish` | 795-895 | Task abschließen |
| `handle_test_config` | 901-928 | Test-Config |
| `handle_run_tests` | 930-968 | Tests ausführen |
| `handle_test_status` | 970-993 | Test-Status |
| `handle_recall` | 999-1053 | Error-History durchsuchen |
| `handle_history` | 1055-1087 | Change-Log anzeigen |
| `handle_learn` | 1089-1132 | Fix dokumentieren |
| `handle_db_connect` | 1138-1175 | DB verbinden |
| `handle_db_schema` | 1177-1201 | Schema laden |
| `handle_db_table` | 1203-1228 | Tabellen-Details |
| `handle_db_disconnect` | 1230-1242 | DB trennen |

### 8.4 Helper-Funktionen

```python
def _text(msg: str) -> List[TextContent]:
    """Create a single TextContent response."""
    return [TextContent(type="text", text=msg)]

def _check_context(args: Dict[str, Any]) -> str:
    """Check for context marker and return refresh text if missing."""
    ctx = args.get("ctx", "")
    return "" if ctx == CONTEXT_MARKER else CONTEXT_REFRESH_TEXT
```

---

## 9. Tool-Definitionen (tools.py)

### 9.1 Übersicht

Die `get_tool_definitions()` Funktion gibt eine Liste aller MCP Tools zurück.

### 9.2 Tool-Schema

```python
Tool(
    name="chainguard_track",
    description="Track file change + AUTO-VALIDATE syntax...",
    inputSchema={
        "type": "object",
        "properties": {
            "working_dir": {"type": "string"},
            "file": {"type": "string", "description": "Changed file path"},
            "action": {"type": "string", "description": "edit/create/delete"},
            "skip_validation": {"type": "boolean"},
            "ctx": {"type": "string", "description": "Context marker"}
        },
        "required": []
    }
)
```

### 9.3 Alle Tools

| Tool | Required Parameters | Optional Parameters |
|------|---------------------|---------------------|
| `chainguard_set_scope` | description | working_dir, modules, acceptance_criteria, checklist |
| `chainguard_track` | - | working_dir, file, action, skip_validation, ctx |
| `chainguard_track_batch` | files | working_dir, action, skip_validation |
| `chainguard_status` | - | working_dir, ctx |
| `chainguard_context` | - | working_dir |
| `chainguard_set_phase` | phase | working_dir, task |
| `chainguard_run_checklist` | - | working_dir |
| `chainguard_check_criteria` | - | working_dir, criterion, fulfilled |
| `chainguard_validate` | status | working_dir, note |
| `chainguard_alert` | message | working_dir |
| `chainguard_clear_alerts` | - | working_dir |
| `chainguard_projects` | - | - |
| `chainguard_config` | - | validation_threshold |
| `chainguard_test_endpoint` | url | working_dir, method, data, headers |
| `chainguard_login` | login_url, username, password | working_dir, username_field, password_field |
| `chainguard_set_base_url` | base_url | working_dir |
| `chainguard_clear_session` | - | working_dir |
| `chainguard_analyze` | target | working_dir |
| `chainguard_finish` | - | working_dir, confirmed, force |
| `chainguard_test_config` | - | working_dir, command, args, timeout |
| `chainguard_run_tests` | - | working_dir |
| `chainguard_test_status` | - | working_dir |
| `chainguard_recall` | query | working_dir, limit |
| `chainguard_history` | - | working_dir, limit, scope_only |
| `chainguard_learn` | resolution | working_dir, file_pattern, error_type |
| `chainguard_db_connect` | user, password, database | working_dir, host, port, db_type |
| `chainguard_db_schema` | - | working_dir, refresh |
| `chainguard_db_table` | table | working_dir, sample |
| `chainguard_db_disconnect` | - | working_dir |

---

## 10. Syntax-Validierung (validators.py)

### 10.1 SyntaxValidator

Validiert Datei-Syntax vor Runtime.

```python
class SyntaxValidator:
    @staticmethod
    async def validate_file(file_path: str, project_path: str) -> Dict[str, Any]:
        """
        Returns: {"valid": bool, "errors": [...], "checked": str}
        """
```

### 10.2 Unterstützte Sprachen

| Sprache | Tool | Extensions |
|---------|------|------------|
| PHP | `php -l` | .php |
| JavaScript | `node --check` | .js, .mjs, .cjs |
| JSON | Python json.load() | .json |
| Python | `python3 -m py_compile` | .py |
| TypeScript | `npx tsc --noEmit` | .ts, .tsx |

### 10.3 Error Extraction

```python
@staticmethod
def _extract_php_error(output: str) -> str
    """Extract 'Parse error' or 'syntax error' line."""

@staticmethod
def _extract_js_error(output: str) -> str
    """Extract 'SyntaxError' or 'Error' line."""

@staticmethod
def _extract_python_error(output: str) -> str
    """Extract 'SyntaxError', 'IndentationError', 'TabError'."""

@staticmethod
def _extract_ts_error(output: str) -> str
    """Extract 'error TS' line."""
```

---

## 11. Code-Analyse (analyzers.py)

### 11.1 CodeAnalyzer

Führt leichtgewichtige statische Analyse durch.

```python
class CodeAnalyzer:
    PATTERNS = {
        "mcp-server": {...},
        "async-io": {...},
        "http-client": {...},
        "caching": {...},
        "file-io": {...},
        "subprocess": {...},
        "laravel-controller": {...},
        "react-component": {...},
    }

    @classmethod
    async def analyze_file(cls, file_path: str, project_path: str) -> Dict[str, Any]:
        """
        Returns: {
            "file": str,
            "path": str,
            "metrics": {...},
            "patterns": [...],
            "checklist": [...],
            "hotspots": [...],
            "todos": [...]
        }
        """
```

### 11.2 Metriken

```python
metrics = {
    "loc": total_lines,
    "loc_code": non_comment_lines,
    "functions": func_count,
    "classes": class_count,
    "complexity": 1-5,
    "complexity_raw": complexity_indicators
}
```

### 11.3 ImpactAnalyzer

Analysiert geänderte Dateien und schlägt potentielle Impacts vor.

```python
class ImpactAnalyzer:
    PATTERNS = [
        ("CLAUDE.md", "Template auch aktualisieren?", "docs", "exact"),
        ("Controller.php", "Tests vorhanden?", "code", "suffix"),
        ("/migrations/", "Model-Änderungen konsistent?", "code", "contains"),
        ...
    ]

    @classmethod
    def analyze(cls, changed_files: List[str]) -> List[Dict[str, str]]

    @classmethod
    def format_impact_check(cls, changed_files: List[str], scope_desc: str) -> str
```

---

## 12. HTTP Session Management (http_session.py)

### 12.1 HTTPSessionManager

Verwaltet HTTP Sessions mit Cookie-Persistenz.

```python
class HTTPSessionManager:
    def __init__(self):
        self._sessions: TTLLRUCache[Dict[str, Any]] = TTLLRUCache(
            maxsize=50,
            ttl_seconds=86400  # 24h
        )

    def get_session(self, project_id: str) -> Dict[str, Any]
    def save_session(self, project_id: str, session_data: Dict[str, Any])
    def clear_session(self, project_id: str)
    def is_logged_in(self, project_id: str) -> bool

    async def ensure_session(self, project_id: str, base_url: str) -> Dict[str, Any]
        """v4.15: Auto-Re-Login wenn Session verloren."""

    async def test_endpoint(self, url, method, project_id, data, headers) -> Dict[str, Any]
    async def login(self, login_url, username, password, project_id, ...) -> Dict[str, Any]
```

### 12.2 Session-Struktur

```python
session = {
    "cookies": {},
    "csrf_token": None,
    "logged_in": False,
    "base_url": None,
    "last_used": None,
    "credentials": {}  # v4.15: Für Auto-Re-Login
}
```

### 12.3 Auth-Detection

```python
if result["status_code"] in [401, 403]:
    result["needs_auth"] = True
elif result["status_code"] in [301, 302, 303, 307, 308]:
    if "login" in redirect_url.lower():
        result["needs_auth"] = True
elif "login" in body and "form" in body:
    result["needs_auth"] = True
```

---

## 13. Test Runner (test_runner.py)

### 13.1 TestConfig

```python
@dataclass
class TestConfig:
    command: str = ""           # "./vendor/bin/phpunit"
    args: str = ""              # "--colors=never"
    timeout: int = 300
    working_dir: str = ""

    def get_full_command(self) -> List[str]
```

### 13.2 TestResult

```python
@dataclass
class TestResult:
    success: bool = False
    passed: int = 0
    failed: int = 0
    total: int = 0
    duration: float = 0.0
    framework: str = "unknown"
    output: str = ""
    error_lines: List[str] = []
    timestamp: str = ""
    exit_code: int = -1
```

### 13.3 OutputParser

Erkennt automatisch das Test-Framework anhand des Outputs.

```python
class OutputParser:
    PATTERNS = {
        "phpunit": {
            "success": re.compile(r"OK \((\d+) tests?, (\d+) assertions?\)"),
            "failure": re.compile(r"FAILURES!..."),
            "indicators": ["PHPUnit", "phpunit", ".phpunit"],
        },
        "jest": {...},
        "pytest": {...},
        "mocha": {...},
        "vitest": {...},
    }

    @classmethod
    def detect_framework(cls, output: str) -> str

    @classmethod
    def parse(cls, output: str, exit_code: int) -> TestResult
```

### 13.4 TestRunner

```python
class TestRunner:
    @staticmethod
    async def run_async(config: TestConfig, project_path: str) -> TestResult

    @staticmethod
    def run(config: TestConfig, project_path: str) -> TestResult
        """Sync wrapper - uses ThreadPoolExecutor when event loop is running."""

    @staticmethod
    def format_result(result: TestResult) -> str

    @staticmethod
    def format_status(result: TestResult, last_run: str = "") -> str
```

---

## 14. Error Memory System (history.py)

### 14.1 Übersicht

Das Error Memory System:
- Loggt alle Änderungen per Scope (append-only JSONL)
- Maintained einen Error Index für schnelles Nachschlagen
- Bietet Auto-Suggest für ähnliche Fehler
- Unterstützt Recall-Queries

### 14.2 HistoryEntry

```python
@dataclass
class HistoryEntry:
    ts: str                  # ISO Timestamp
    file: str                # Relativer Pfad
    action: str              # edit, create, delete
    validation: str          # PASS oder FAIL:message
    scope_id: str = ""
    scope_desc: str = ""
    fix_applied: Optional[str] = None
```

### 14.3 ErrorEntry

```python
@dataclass
class ErrorEntry:
    ts: str
    file_pattern: str        # "*Controller.php"
    error_type: str          # "PHP Syntax"
    error_msg: str
    scope_desc: str
    project_id: str
    resolution: Optional[str] = None

    def matches(self, query: str) -> float:
        """Calculate match score (0.0 - 1.0)."""
```

### 14.4 HistoryManager

```python
class HistoryManager:
    # Storage Paths
    @staticmethod
    def _get_history_path(project_id: str) -> Path
        """~/.chainguard/projects/{id}/history.jsonl"""

    @staticmethod
    def _get_error_index_path(project_id: str) -> Path
        """~/.chainguard/projects/{id}/error_index.json"""

    # History Log (append-only)
    @classmethod
    async def log_change(cls, project_id, file, action, validation_result, ...)

    @classmethod
    async def get_history(cls, project_id, limit=50, scope_id=None) -> List[HistoryEntry]

    # Error Index
    @classmethod
    async def index_error(cls, project_id, file, error_type, error_msg, scope_desc, ...)

    @classmethod
    async def update_resolution(cls, project_id, file_pattern, error_type, resolution)

    @classmethod
    async def find_similar_errors(cls, project_id, file, error_type, error_msg) -> List[ErrorEntry]
        """Auto-Suggest: Findet ähnliche Fehler mit bekannten Fixes."""

    @classmethod
    async def recall(cls, project_id, query, limit=5) -> List[ErrorEntry]
        """Durchsucht den Error Index."""

    # Pattern Extraction
    @staticmethod
    def _extract_pattern(file_name: str) -> str:
        """UserController.php -> *Controller.php"""
```

### 14.5 Auto-Suggest Formatter

```python
def format_auto_suggest(similar_errors: List[ErrorEntry]) -> str:
    """
    Returns:
    💡 Similar error fixed before:
       - *Controller.php (2d ago)
         → Missing semicolon before }
    """
```

---

## 15. Database Inspector (db_inspector.py)

### 15.1 Übersicht

Live Database Schema Inspection um SQL-Fehler zu vermeiden.

**Features:**
- MySQL/PostgreSQL/SQLite Support
- TTL-cached Schema (5 min default)
- Token-effiziente Formatierung
- SQL Injection Prevention (v4.19.1)

### 15.2 SQL Injection Prevention (v4.19.1)

```python
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def validate_identifier(name: str) -> bool:
    """Only allows alphanumeric and underscores."""
    if not name or len(name) > 128:
        return False
    return bool(IDENTIFIER_PATTERN.match(name))

def safe_identifier(name: str, db_type: str = "mysql") -> str:
    """Return safely quoted identifier."""
    if not validate_identifier(name):
        raise ValueError(f"Invalid identifier: {name}")
    if db_type == "postgres":
        return f'"{name}"'
    return f"`{name}`"
```

### 15.3 Data Models

```python
@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    db_type: str = "mysql"  # mysql, postgres, sqlite

@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool = True
    key: str = ""           # PRI, UNI, MUL
    default: Any = None
    extra: str = ""         # auto_increment
    fk_ref: str = ""        # table.column

@dataclass
class TableInfo:
    name: str
    columns: List[ColumnInfo] = []
    row_count: int = 0
    primary_key: List[str] = []
    foreign_keys: Dict[str, str] = {}

@dataclass
class SchemaInfo:
    database: str
    db_type: str
    version: str = ""
    tables: Dict[str, TableInfo] = {}
    cached_at: float = 0
```

### 15.4 DBInspector

```python
class DBInspector:
    def __init__(self):
        self._config: Optional[DBConfig] = None
        self._schema: Optional[SchemaInfo] = None
        self._cache_ttl: int = 300
        self._connected: bool = False

    def is_connected(self) -> bool

    async def connect(self, config: DBConfig) -> Dict[str, Any]
    async def _connect_mysql(self, config) -> Dict[str, Any]
    async def _connect_postgres(self, config) -> Dict[str, Any]
    async def _connect_sqlite(self, config) -> Dict[str, Any]

    async def get_schema(self, force_refresh: bool = False) -> Optional[SchemaInfo]
    async def _fetch_mysql_schema(self) -> SchemaInfo
    async def _fetch_postgres_schema(self) -> SchemaInfo
    async def _fetch_sqlite_schema(self) -> SchemaInfo

    async def get_table_details(self, table_name: str, show_sample: bool = False) -> Optional[str]
    async def _get_sample_rows(self, table_name: str) -> List[str]

    def format_schema(self, schema: SchemaInfo) -> str
    def clear(self)
```

### 15.5 Schema-Ausgabe Format

```
📊 Database: mydb (mysql 8.0.32)

users (4 cols, ~5 rows)
├─ id: INT PK AUTO
├─ username: VARCHAR(255) UNIQUE
├─ email: VARCHAR(255)
└─ created_at: DATETIME

articles (6 cols, ~50 rows)
├─ id: INT PK AUTO
├─ title: VARCHAR(255)
├─ content: TEXT
├─ author_id: INT FK→users.id
└─ created_at: DATETIME

(Cache: 120s alt, TTL: 300s)
```

---

## 16. Checklist Runner (checklist.py)

### 16.1 ChecklistRunner

Führt Checklist-Commands sicher und asynchron aus.

```python
class ChecklistRunner:
    ALLOWED_COMMANDS = {
        'test', 'grep', 'ls', 'cat', 'head', 'wc', 'find', 'stat', '[',
        'php', 'node', 'python', 'python3', 'npm', 'composer'
    }

    COMMAND_TIMEOUT = 10  # seconds

    @staticmethod
    async def run_check_async(check_command: str, project_path: str) -> Dict[str, Any]:
        """
        Returns: {"passed": bool, "output": str}
        """

    @staticmethod
    def run_check(check_command: str, project_path: str) -> Dict[str, Any]:
        """Sync wrapper - uses sync subprocess when event loop is running."""

    @staticmethod
    async def run_all_async(checklist: List[Dict], project_path: str) -> Dict[str, Any]:
        """Run all items in parallel."""

    @staticmethod
    def run_all(checklist: List[Dict], project_path: str) -> Dict[str, Any]:
        """Sync wrapper - runs sequentially."""
```

### 16.2 Checklist-Format

```python
checklist = [
    {"item": "Controller", "check": "test -f app/Http/Controllers/AuthController.php"},
    {"item": "Route", "check": "grep -q 'auth' routes/web.php"},
    {"item": "Test", "check": "test -f tests/Feature/AuthTest.php"}
]
```

### 16.3 Security

- **Kein shell=True** - Verwendet `asyncio.create_subprocess_exec`
- **Command Whitelist** - Nur erlaubte Befehle
- **Timeout** - 10 Sekunden max

---

## 17. Utilities (utils.py)

### 17.1 Path Sanitization

```python
def sanitize_path(file_path: str, project_path: str) -> Optional[str]:
    """
    Sanitize and validate a file path to prevent path traversal attacks.
    Returns None if path is invalid or outside project scope.
    """
    try:
        file_resolved = Path(file_path).resolve()
        project_resolved = Path(project_path).resolve()

        try:
            file_resolved.relative_to(project_resolved)
            return str(file_resolved)
        except ValueError:
            # File is outside project - could be legitimate
            return str(file_resolved)
    except (OSError, ValueError):
        return None

def is_path_safe(file_path: str, project_path: str) -> bool:
    """Check if a file path is safe (no traversal, within project)."""
```

---

## 18. Server (server.py)

### 18.1 Übersicht

Entry Point für den MCP Server.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource, Prompt, PromptMessage

server = Server("chainguard")
```

### 18.2 Tool Registration

```python
@server.list_tools()
async def list_tools() -> List[Tool]:
    return await get_tool_definitions()

@server.call_tool()
async def call_tool(name: str, args: Dict[str, Any]) -> List[TextContent]:
    return await handle_tool_call(name, args)
```

### 18.3 Resources

```python
@server.list_resources()
async def list_resources() -> List[Resource]:
    return [Resource(
        uri="chainguard://status",
        name="Chainguard Status",
        description="Current project status",
        mimeType="text/plain"
    )]

@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "chainguard://status":
        projects = await pm.list_all_projects_async()
        return "\n".join(f"{p['name']}|{p['phase']}" for p in projects[:5])
```

### 18.4 Prompts

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `start` | Start new task with scope | task (required) |
| `check` | Quick status check | - |
| `finish` | Complete task with validation | - |

### 18.5 Main Entry Point

```python
async def main():
    logger.info(f"Chainguard MCP Server v{VERSION} starting...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        logger.info("Flushing pending saves...")
        await pm.flush()

def run():
    """Entry point for console script."""
    asyncio.run(main())
```

---

## 19. Enforcer Hook

### 19.1 Übersicht

Der Enforcer Hook ist ein PreToolUse Hook der CHAINGUARD-Regeln hart enforced.

**Datei:** `~/.chainguard/hooks/chainguard_enforcer.py`

### 19.2 Hook-Konfiguration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.chainguard/hooks/chainguard_enforcer.py"
        }]
      }
    ]
  }
}
```

### 19.3 Exit Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Tool wird ausgeführt |
| 2 | Tool wird BLOCKIERT (mit Nachricht) |

### 19.4 Geprüfte Regeln

1. **Schema-Dateien ohne gültigen DB-Schema-Check** → BLOCK
   - TTL-basiert (10 Minuten)
   - Prüft `.sql`, `migration`, `migrate`, etc.

2. **Blocking Alerts vorhanden** → BLOCK
   - z.B. LOGIN_REQUIRED

3. **Kein Scope gesetzt** → WARN (kein Block)

### 19.5 Wichtige Funktionen

```python
def get_project_id(working_dir: str) -> str:
    """Berechnet Project ID wie der MCP Server."""
    # 1. Git Remote URL Hash
    # 2. Git Root Path Hash
    # 3. Working Dir Path Hash

def load_enforcement_state(working_dir: str) -> Optional[Dict[str, Any]]:
    """Lädt enforcement-state.json für ein Projekt."""

def is_schema_file(file_path: str) -> bool:
    """Prüft ob Datei eine Schema-Datei ist."""

def is_schema_check_valid(checked_at: str) -> Tuple[bool, int]:
    """Prüft ob Schema-Check noch gültig ist (innerhalb TTL)."""

def check_rules(tool_name: str, tool_input: Dict, state: Dict) -> Tuple[bool, str]:
    """Prüft alle CHAINGUARD-Regeln."""

def infer_project_dir(file_path: str, cwd_fallback: str) -> str:
    """Leitet Projektverzeichnis aus file_path ab."""
    # Sucht nach: .git, composer.json, package.json, .chainguard, CLAUDE.md
```

---

## 20. Alle Tools im Detail

### 20.1 Core Tools

#### chainguard_set_scope

**Zweck:** Definiert Task-Grenzen und Kriterien zu Beginn eines Tasks.

**Parameter:**
- `description` (required): Was gebaut wird
- `working_dir`: Projekt-Verzeichnis
- `modules`: Datei-Patterns im Scope
- `acceptance_criteria`: Akzeptanzkriterien
- `checklist`: Automatische Checks

**Effekte:**
- Setzt `state.scope`
- Reset aller scope-relevanten Felder (v4.16)
- Erstellt `.chainguard/marker` im Projekt (v4.19)
- Zeigt Context-Injection mit Pflichtregeln

**Response:**
```
✓ Scope: Feature X implementieren
Modules: src/*, tests/* | Criteria: 3 | Checks: 2

────────────────────────────────────────
📋 **PFLICHT-AKTIONEN FÜR DIESEN TASK:**

1. `chainguard_track(file="...", ctx="🔗")` nach JEDER Dateiänderung
...
```

#### chainguard_track

**Zweck:** Trackt Dateiänderung mit Auto-Validierung.

**Parameter:**
- `file`: Geänderte Datei
- `action`: edit, create, delete
- `skip_validation`: Syntax-Check überspringen
- `ctx`: Context Marker (🔗)

**Effekte:**
- Incrementiert `files_changed` und `files_since_validation`
- Führt Syntax-Check durch (PHP/JS/JSON/PY/TS)
- Indexiert Fehler für Auto-Suggest
- Loggt Change in History
- Invalidiert Schema-Check bei .sql-Änderung (v4.18)
- Prüft Scope-Zugehörigkeit

**Response (silent):** Leer wenn alles OK

**Response (error):**
```
✗ PHP Syntax: Parse error: unexpected '}'

💡 Similar error fixed before:
   - *Controller.php (2d ago)
     → Missing semicolon before }
```

#### chainguard_status

**Zweck:** Ultra-kompakter One-Line Status.

**Response:**
```
myproject|impl|F5/V3 [V!5,OOS:2] Feature X impl...
```

Format: `project_name|phase|Files/Validation [flags] scope_preview`

#### chainguard_finish

**Zweck:** Task mit vollständiger Validierung abschließen.

**2-Schritt-Prozess:**
1. **Ohne confirmed:** Zeigt Impact-Check
2. **Mit confirmed=true:** Schließt Task ab

**Blocking Issues (v4.15):**
- HTTP-Tests nicht durchgeführt bei Web-Dateien
- Blocking Alerts vorhanden

**Mit force=true:** Kann (nicht-blocking) Issues überschreiben

### 20.2 Test Runner Tools

#### chainguard_test_config

```python
chainguard_test_config(
    command="./vendor/bin/phpunit",
    args="tests/ --colors=never",
    timeout=300
)
```

#### chainguard_run_tests

Führt konfigurierte Tests aus mit Auto-Detection des Frameworks.

**Response:**
```
✓ phpunit: 23/23 tests passed
  Duration: 4.2s
```

### 20.3 Database Tools

#### chainguard_db_connect

```python
chainguard_db_connect(
    host="localhost",
    port=3306,
    user="root",
    password="root",
    database="mydb",
    db_type="mysql"  # mysql, postgres, sqlite
)
```

#### chainguard_db_schema

Lädt das Datenbankschema (5 Min Cache).

**Response:** Siehe Kapitel 14.5

#### chainguard_db_table

Zeigt Details einer Tabelle mit optionalen Sample-Daten.

```python
chainguard_db_table(table="users", sample=True)
```

### 20.4 HTTP Testing Tools

#### chainguard_set_base_url

```python
chainguard_set_base_url(base_url="http://localhost:8888/myapp")
```

#### chainguard_test_endpoint

```python
chainguard_test_endpoint(url="/api/users", method="GET")
```

**Auth-Detection:** Erkennt 401, 403, Login-Redirects

#### chainguard_login

```python
chainguard_login(
    login_url="/login",
    username="admin@example.com",
    password="secret",
    username_field="email",  # Default
    password_field="password"  # Default
)
```

**Effekte:**
- Holt CSRF-Token automatisch (Laravel)
- Speichert Session-Cookies
- Speichert Credentials für Auto-Re-Login (v4.15)

### 20.5 Error Memory Tools

#### chainguard_recall

Durchsucht Error-History nach ähnlichen Problemen.

```python
chainguard_recall(query="php syntax Controller", limit=5)
```

#### chainguard_learn

Dokumentiert einen Fix für zukünftige Auto-Suggests.

```python
chainguard_learn(resolution="Missing semicolon before closing brace")
```

---

## 21. Flowcharts

### 21.1 Tool Call Flow

```
User Request
    ↓
Claude will Tool aufrufen
    ↓
┌─────────────────────────────────────────┐
│ PreToolUse Hook (chainguard_enforcer)   │
│ → Liest enforcement-state.json          │
│ → Prüft: DB-Schema geladen?             │
│ → Prüft: Blocking Alerts?               │
│ → exit(2) wenn nicht OK → BLOCKIERT!    │
└─────────────────────────────────────────┘
    ↓ (nur wenn Hook OK)
┌─────────────────────────────────────────┐
│ MCP Server: @server.call_tool()         │
│ → handle_tool_call(name, args)          │
│ → HandlerRegistry.dispatch(name, args)  │
│   → Scope-Blockade prüfen (v4.9)        │
│   → Handler aufrufen                    │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Handler-Funktion                        │
│ → State laden: pm.get_async()           │
│ → Logik ausführen                       │
│ → State speichern: pm.save_async()      │
│   → Debounced (500ms)                   │
│   → enforcement-state.json schreiben    │
│ → Response: List[TextContent]           │
└─────────────────────────────────────────┘
    ↓
Response an Claude
```

### 21.2 Track Flow

```
chainguard_track(file="Controller.php", ctx="🔗")
    ↓
┌─ Path Validation ────────────────────────┐
│ is_path_safe(file, project_path)?        │
│ → True: Weiter                           │
│ → False: "⚠ Invalid path"                │
└──────────────────────────────────────────┘
    ↓
┌─ Schema-File Check (v4.18) ──────────────┐
│ is_schema_file(file)?                    │
│ → True: Schema invalidieren wenn geändert│
│         Warnen wenn nicht geprüft        │
└──────────────────────────────────────────┘
    ↓
┌─ Syntax Validation ──────────────────────┐
│ SyntaxValidator.validate_file()          │
│ → PHP: php -l                            │
│ → JS: node --check                       │
│ → JSON: json.load()                      │
│ → Python: py_compile                     │
│ → TS: npx tsc --noEmit                   │
└──────────────────────────────────────────┘
    ↓
┌─ Bei Fehler ─────────────────────────────┐
│ 1. Alert erstellen                       │
│ 2. Error indexieren                      │
│ 3. Similar errors suchen (Auto-Suggest)  │
└──────────────────────────────────────────┘
    ↓
┌─ Scope Check ────────────────────────────┐
│ check_file_in_scope(file)?               │
│ → False: add_out_of_scope_file()         │
│          "⚠ OOS: filename"               │
└──────────────────────────────────────────┘
    ↓
┌─ State Update ───────────────────────────┐
│ files_changed++                          │
│ files_since_validation++                 │
│ add_changed_file(name)                   │
│ add_action("edit: filename")             │
└──────────────────────────────────────────┘
    ↓
┌─ History Log (v4.11) ────────────────────┐
│ HistoryManager.log_change()              │
│ → Append to history.jsonl                │
└──────────────────────────────────────────┘
    ↓
┌─ Context Check ──────────────────────────┐
│ ctx == "🔗"?                             │
│ → Ja: Leer oder Warnung                  │
│ → Nein: CONTEXT_REFRESH_TEXT anhängen    │
└──────────────────────────────────────────┘
```

### 21.3 Finish Flow

```
chainguard_finish()
    ↓
┌─ Checklist Run ──────────────────────────┐
│ Wenn nicht schon gelaufen:               │
│ ChecklistRunner.run_all_async()          │
└──────────────────────────────────────────┘
    ↓
┌─ Completion Status ──────────────────────┐
│ get_completion_status()                  │
│ → Kriterien erfüllt?                     │
│ → Checklist bestanden?                   │
│ → Offene Alerts?                         │
│ → Syntax-Fehler?                         │
│ → HTTP-Tests bei Web-Projekten?          │
└──────────────────────────────────────────┘
    ↓
Blocking Issues? ─────────────────────────┐
│ → Ja: BLOCKIERT (auch mit force=true)    │
│       "🚫 BLOCKIERT - HTTP-Tests..."     │
└──────────────────────────────────────────┘
    ↓
Non-blocking Issues ohne force? ──────────┐
│ → "✗ Kann nicht abschließen..."          │
└──────────────────────────────────────────┘
    ↓
confirmed=false? ─────────────────────────┐
│ → Impact-Check anzeigen                  │
│ → impact_check_pending = true            │
│ → "→ Bitte mit confirmed=true bestätigen"│
└──────────────────────────────────────────┘
    ↓
confirmed=true oder force=true? ──────────┐
│ → State zurücksetzen                     │
│ → phase = "done"                         │
│ → "✓ Task erfolgreich abgeschlossen!"    │
└──────────────────────────────────────────┘
```

---

## Anhang: Versions-Historie

| Version | Datum | Highlights |
|---------|-------|------------|
| 5.0.0 | 2026-01 | **Task-Mode System** - 5 Modi (programming, content, devops, research, generic), Mode-spezifische Tools, Context Injection |
| 4.19.1 | 2025-12 | ThreadPoolExecutor Fix, AsyncFileLock Lazy Init |
| 4.19.0 | 2025-12 | Auto-Marker bei set_scope, immediate save |
| 4.18.0 | 2025-12 | TTL-basierte Schema-Check-Validierung |
| 4.17.0 | 2025-12 | HARD ENFORCEMENT via PreToolUse Hook |
| 4.16.0 | 2025-12 | Full State Reset, Context-Injection |
| 4.15.0 | 2025-11 | HTTP-Test Enforcement, Auto-Re-Login |
| 4.12.0 | 2025-11 | Database Inspector |
| 4.11.0 | 2025-11 | Error Memory System |
| 4.10.0 | 2025-11 | Test Runner |
| 4.8.0 | 2025-10 | Handler-Registry Pattern, TTL-LRU Cache |
| 4.6.0 | 2025-10 | Context-Check mit Canary-Parameter |
| 4.5.0 | 2025-10 | Python & TypeScript Validation |
| 4.4.0 | 2025-10 | Scope-Optimierung |
| 4.3.1 | 2025-09 | 2-Schritt-Finish mit Impact-Check |
| 4.2.0 | 2025-09 | HTTP Testing |
| 4.1.0 | 2025-09 | Async I/O, Write Debouncing |
| 4.0.0 | 2025-09 | Modulare Architektur |

---

**Ende der Dokumentation**

*Generiert durch Deep Dive Analyse aller Module des CHAINGUARD MCP Servers v5.0.0*
