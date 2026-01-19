<!-- CHAINGUARD-MANDATORY-START v6.5.0 -->

# ================================================
# STOP - LIES DAS ZUERST!
# ================================================
#
# BEVOR DU IRGENDETWAS ANDERES TUST:
#
#     chainguard_set_scope(
#         description="...",
#         working_dir="...",
#         acceptance_criteria=[...]
#     )
#
# ALLE anderen Chainguard-Tools sind BLOCKIERT
# bis du set_scope aufgerufen hast!
#
# v6.5: Kanban-System für komplexe Projekte
# BLOCKIERT wenn DB-Schema nicht geprüft wurde!
#
# ================================================

## CHAINGUARD v6.5 - PFLICHT-ANWEISUNGEN (HARD ENFORCEMENT!)

| # | PFLICHT-AKTION | WANN |
|---|----------------|------|
| 1 | `chainguard_set_scope(...)` | **ALLERERSTE AKTION bei jedem Task!** |
| 2 | `chainguard_db_connect() + chainguard_db_schema()` | **VOR jeder DB/Schema-Arbeit! (BLOCKIERT sonst!)** |
| 3 | `chainguard_track(file="...", ctx="...")` | Nach JEDER Dateiänderung |
| 4 | `chainguard_test_endpoint(...)` | **Bei Web-Projekten: VOR finish!** |
| 5 | `chainguard_kanban_show()` | **Bei komplexen Projekten: Überblick behalten!** |
| 6 | `chainguard_finish(confirmed=True)` | Am Task-Ende |

> **v6.5 Features:** Kanban-System, TOON Token-Optimierung, Task-Mode System, Halluzination Prevention

### Minimaler Workflow

```python
# 1. ZUERST - Scope setzen (PFLICHT!)
chainguard_set_scope(description="Was du baust", working_dir="/pfad")

# 2. BEI DB-ARBEIT - Schema prüfen (BLOCKIERT SONST!)
chainguard_db_connect(host="localhost", user="root", password="...", database="mydb")
chainguard_db_schema()  # Zeigt alle Tabellen + Spalten!

# 3. Arbeiten + Tracken
# ... Edit/Write ...
chainguard_track(file="...", ctx="...")

# 4. Bei Web-Projekten (PHP/JS/TS): HTTP-Tests!
chainguard_set_base_url(base_url="http://localhost:8888/app")
chainguard_test_endpoint(url="/geänderte-route", method="GET")

# 5. Bei komplexen Projekten: Kanban nutzen!
chainguard_kanban_show()  # Vollständige Übersicht

# 6. Abschliessen
chainguard_finish(confirmed=True)
```

### Context-Canary: `ctx="..."`

Bei JEDEM Chainguard-Aufruf `ctx="..."` mitgeben! Fehlt er -> Kontext verloren -> Auto-Refresh.
<!-- CHAINGUARD-MANDATORY-END -->



























# CHAINGUARD v6.5.0 - Kanban-System + TOON Token-Optimierung + Task-Mode System

> **🔴 WICHTIG - Modulare Struktur:**
> Der MCP-Server läuft von `~/.chainguard/` - NICHT aus diesem Projekt!
>
> **Bei Updates:** Siehe **[SYNCINSTALL.md](SYNCINSTALL.md)** für die vollständige Sync-Checkliste!
>
> **Quick-Sync:**
> ```bash
> rm -rf ~/.chainguard/chainguard && cp -r src/mcp-server/chainguard ~/.chainguard/ && \
> cp src/mcp-server/chainguard_mcp.py ~/.chainguard/ && \
> cp src/hooks/chainguard_enforcer.py ~/.chainguard/hooks/ && \
> cp src/templates/CHAINGUARD.md.block ~/.chainguard/templates/
> ```
> Danach Claude Code neu starten!

## Modulare Architektur (v4.12)

```
~/.chainguard/
├── chainguard_mcp.py      ← Wrapper (importiert Package)
└── chainguard/            ← Modulares Package
    ├── __init__.py        (Exports)
    ├── server.py          (MCP Server Setup)
    ├── handlers.py        (Handler-Registry Pattern - testbar!)
    ├── tools.py           (Tool Definitionen)
    ├── models.py          (Dataclasses)
    ├── project_manager.py (Projekt-CRUD)
    ├── validators.py      (Syntax-Checks, async JSON)
    ├── analyzers.py       (Code-Analyse)
    ├── http_session.py    (HTTP/Login mit TTL-Cache)
    ├── test_runner.py     (Test-Ausführung, v4.10)
    ├── history.py         (Error Memory System, v4.11)
    ├── db_inspector.py    (Database Schema Inspector, v4.12)
    ├── kanban.py          (Kanban-System, v6.5)
    ├── cache.py           (LRU + TTL-LRU Cache)
    ├── checklist.py       (Async Checklist-Ausführung)
    ├── config.py          (Konstanten + Feature-Flags)
    ├── toon.py            (TOON Encoder, v6.0)
    └── utils.py           (Hilfsfunktionen)
```

**Vorteile:**
- Einzelne Module lesbar (nicht 31K+ Tokens)
- Handler-Registry Pattern: Testbar, erweiterbar
- Klare Trennung der Verantwortlichkeiten

**Design-Prinzip:** Minimaler Kontextverbrauch, maximaler Nutzen, maximale Performance.

## Unit-Tests (PFLICHT bei neuen Features!)

> **Bei jeder Änderung am MCP-Server müssen die Tests erweitert/angepasst werden!**

```bash
# Tests ausführen
cd src/mcp-server && python3 -m pytest tests/ -v

# Einzelnes Modul testen
python3 -m pytest tests/test_cache.py -v
```

| Test-Datei | Testet | Anzahl |
|------------|--------|--------|
| `test_cache.py` | LRUCache, TTLLRUCache, GitCache | 19 |
| `test_models.py` | ScopeDefinition, ProjectState | 19 |
| `test_test_runner.py` | TestConfig, TestResult, OutputParser | 28 |
| `test_history.py` | HistoryManager, ErrorEntry, Auto-Suggest | 29 |
| `test_db_inspector.py` | DBConfig, DBInspector, SchemaInfo | 26 |
| `test_task_mode.py` | TaskMode, ModeFeatures, Auto-Detection | 32 |
| `test_toon.py` | TOON Encoder, Token-Savings, Array-Formatting | 63 |
| `test_kanban.py` | KanbanCard, KanbanBoard, KanbanManager, Dependencies, Presets | 50 |

**Checkliste für neue Features:**
1. Neues Modul? → Neue `tests/test_<module>.py` erstellen
2. Neue Klasse/Funktion? → Tests in bestehende Datei hinzufügen
3. Bug-Fix? → Regression-Test hinzufügen
4. **Alle 764+ Tests müssen grün sein vor Sync!**

Siehe **[docs/TESTING.md](docs/TESTING.md)** für vollständige Dokumentation.

## v6.5.0 Features (NEU!)

### Kanban-System - Persistente Aufgabenverwaltung

Für komplexe, mehrtägige Projekte mit Pipelines. Überlebt Session-Neustarts!

**Struktur im Projekt:**
```
.claude/
├── kanban.yaml      # Board-Daten (YAML)
├── cards/
│   └── <id>.md      # Detaillierte Anweisungen pro Card
└── archive.yaml     # Archivierte/erledigte Cards
```

**Spalten-Presets (LLM-gesteuert):**

| Preset | Spalten | Verwendung |
|--------|---------|------------|
| `default` | backlog → in_progress → review → done | Standard-Workflow |
| `programming` | backlog → in_progress → testing → review → done | Software-Entwicklung |
| `content` | ideen → entwurf → überarbeitung → lektorat → fertig | Bücher/Artikel |
| `devops` | geplant → vorbereitung → deployment → testing → live | Server/Infra |
| `research` | zu_untersuchen → in_recherche → analyse → verifiziert → dokumentiert | Recherche |
| `agile` | backlog → sprint → in_progress → review → done | Agiles Team |
| `simple` | todo → doing → done | Minimalistisch |

**Custom Columns:** Bei `chainguard_kanban_init` können beliebige Spalten definiert werden!

### Kanban-Tools

| Tool | Zweck |
|------|-------|
| `chainguard_kanban_init` | **Board initialisieren mit Preset oder Custom-Spalten** |
| `chainguard_kanban` | Board anzeigen (kompakt) |
| `chainguard_kanban_show` | **Vollständige grafische Ansicht mit allen Details** |
| `chainguard_kanban_add` | Card hinzufügen (mit Priority, Tags, Details) |
| `chainguard_kanban_move` | Card verschieben (backlog → in_progress → done) |
| `chainguard_kanban_detail` | Card-Details laden (inkl. verknüpfte MD-Datei) |
| `chainguard_kanban_update` | Card bearbeiten (Title, Priority, Tags) |
| `chainguard_kanban_delete` | Card löschen |
| `chainguard_kanban_archive` | Card archivieren (Historie behalten) |
| `chainguard_kanban_history` | Archivierte Cards anzeigen |

### Kanban Workflow-Beispiel

```python
# 0. Board initialisieren mit task-spezifischen Spalten (EMPFOHLEN!)
# Option A: Mit Preset
chainguard_kanban_init(preset="programming")  # Für Code-Projekte

# Option B: Custom Columns für spezifische Workflows
chainguard_kanban_init(columns=["design", "implementation", "testing", "documentation", "deployed"])

# 1. Cards hinzufügen
chainguard_kanban_add(
    title="Auth System implementieren",
    priority="high",
    tags=["backend", "security"],
    detail="## Anforderungen\n\n- JWT-basiert\n- 2FA Support"
)

# 2. Weitere Cards mit Abhängigkeiten
chainguard_kanban_add(
    title="Login UI bauen",
    depends_on=["abc123"],  # Wartet auf Auth System
    detail="## UI Components\n\n- Login Form\n- Forgot Password"
)

# 3. Überblick verschaffen
chainguard_kanban_show()  # Grafische Vollansicht

# 4. Arbeit beginnen
chainguard_kanban_move(card_id="abc123", to_column="in_progress")

# 5. Bei Fertigstellung
chainguard_kanban_move(card_id="abc123", to_column="done")
chainguard_kanban_archive(card_id="abc123")  # Optional: Archivieren
```

### Grafische Board-Ansicht (`chainguard_kanban_show`)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                📋 KANBAN BOARD                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Progress: [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 20% (1/5 done)         ║
║  📥 2 │ 🔄 1 │ 👀 1 │ ✅ 1 │ ⛔ 1 blocked                                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ 📥 BACKLOG (2)                                                                ║
║──────────────────────────────────────────────────────────────────────────────║
║   ┌─ 🟠 [abc123] Auth System implementieren                                   ║
║   │  Priority: HIGH │ Created: 2026-01-19 │ Updated: 2026-01-19              ║
║   │  Tags: #backend #security                                                ║
║   │  📄 Detail-Datei:                                                         ║
║   │  ┌──────────────────────────────────────────────────────────────────     ║
║   │  │ ## Anforderungen                                                      ║
║   │  │ - JWT-basiert                                                         ║
║   │  │ - 2FA Support                                                         ║
║   │  └──────────────────────────────────────────────────────────────────     ║
║   └──────────────────────────────────────────────────────────────────────────║
...
```

**Features der Show-Ansicht:**
- Progress-Bar mit Prozent
- Stats pro Spalte + Blocked-Count
- Priority-Icons: 🔴 critical, 🟠 high, 🟡 medium, 🟢 low
- ⛔ BLOCKED wenn Dependencies nicht erfüllt
- Inline-Preview der verknüpften MD-Dateien (8 Zeilen)
- Timestamp

### Feature-Flag

In `config.py`:
```python
KANBAN_ENABLED = True  # An/Aus-Schalter
```

---

## v6.0.0 Features

### TOON - Token-Oriented Object Notation

TOON ist ein kompaktes Datenformat speziell für LLM-Input, das **30-60% weniger Tokens** verbraucht als JSON.

**Vorher (JSON-style):**
```json
[{"id":"abc","path":"/app","phase":"impl","files":5},{"id":"def","path":"/other","phase":"plan","files":3}]
```

**Nachher (TOON):**
```
projects[2]{id,path,phase,files}:
  abc,/app,impl,5
  def,/other,plan,3
```

**Aktivierte Tools:**
| Tool | Format | Token-Ersparnis |
|------|--------|-----------------|
| `chainguard_projects` | TOON | ~40% |
| `chainguard_history` | TOON | ~40% |

**Feature Flags (config.py):**
```python
TOON_ENABLED = True        # TOON für Array-Outputs (default: an)
MEMORY_ENABLED = False     # Long-Term Memory (default: aus wegen RAM)
XML_RESPONSES_ENABLED = False  # XML-Responses (default: aus)
```

### Memory standardmäßig deaktiviert

Long-Term Memory (ChromaDB + sentence-transformers) kann **1-2GB RAM** verbrauchen und auf Systemen mit wenig Speicher zu Problemen führen. Daher ist `MEMORY_ENABLED = False` der neue Default.

**Aktivieren (nur bei genug RAM):**
```python
# In ~/.chainguard/chainguard/config.py:
MEMORY_ENABLED = True
```

---

## v5.5.0 Features (NEU!)

### Halluzination Prevention - Symbol & Package Validation

LLMs halluzinieren manchmal Funktionsnamen oder Pakete, die nicht existieren. Chainguard erkennt das jetzt automatisch!

#### Symbol Validation
Prüft Funktions-/Methodenaufrufe gegen bekannte Definitionen im Projekt:

```python
# Modus setzen (Default: WARN)
chainguard_symbol_mode(mode="WARN")  # OFF, WARN, STRICT, ADAPTIVE

# Code validieren
chainguard_validate_symbols(file="src/Controller.php")
# → ⚠ Potential hallucination: unknownMethod() not found in codebase
#   Confidence: 0.85 - likely hallucinated
```

| Modus | Verhalten |
|-------|-----------|
| OFF | Deaktiviert |
| WARN | Warnung anzeigen (Default, blockiert nie) |
| STRICT | Blockiert bei hoher Konfidenz (>0.8) |
| ADAPTIVE | Auto-Anpassung basierend auf False-Positive-Rate |

#### Package Validation (Slopsquatting Detection)
~20% der LLM-empfohlenen Pakete existieren nicht! Angreifer registrieren diese Namen ("Slopsquatting"):

```python
chainguard_validate_packages(file="src/app.js")
# → ⚠ Package 'colrs' not found in package.json
#   Did you mean: 'colors'? (Levenshtein: 1)
#   🔴 SLOPSQUATTING RISK: Similar package exists!
```

**Unterstützte Paket-Manager:**
- PHP: composer.json / composer.lock
- JS/TS: package.json / node_modules
- Python: requirements.txt / pyproject.toml

### Neue Tools (v5.5)

| Tool | Zweck |
|------|-------|
| `chainguard_symbol_mode` | Validierungsmodus setzen/anzeigen |
| `chainguard_validate_symbols` | Funktionsaufrufe gegen Codebase prüfen |
| `chainguard_validate_packages` | Imports gegen Dependencies prüfen |

---

## v5.3.0 Features

### AST-Analyse & Architektur-Erkennung

#### Code-Struktur analysieren
Extrahiert Klassen, Funktionen, Methoden, Imports mit AST-Parsing:

```python
chainguard_analyze_code(file="src/UserController.php")
# → 📊 AST Analysis: UserController.php
#   Classes: UserController
#   Methods: index(), store(), update(), destroy()
#   Imports: App\Models\User, Illuminate\Http\Request
#   Relationships: extends Controller, uses User
```

#### Architektur erkennen
Identifiziert Framework und Architektur-Pattern automatisch:

```python
chainguard_detect_architecture()
# → 🏗 Architecture Detection:
#   Framework: Laravel 10.x (detected)
#   Pattern: MVC (Model-View-Controller)
#
#   Evidence:
#   - app/Http/Controllers/ → Controllers
#   - app/Models/ → Models
#   - resources/views/ → Views
#   - routes/web.php → Routing
```

**Erkannte Patterns:** MVC, MVVM, Clean Architecture, Layered, API-first, Hexagonal

### Memory Export/Import

Projekt-Memory portabel machen für Backup oder Transfer:

```python
# Exportieren
chainguard_memory_export(format="json", compress=True)
# → ✓ Exported to ~/.chainguard/exports/garvis_2024-01-15.json.gz
#   Size: 2.3 MB (12.1 MB uncompressed)

# Importieren
chainguard_memory_import(file="backup.json", merge=True)
# → ✓ Imported 847 documents, skipped 23 existing

# Verfügbare Exports auflisten
chainguard_list_exports()
# → exports[3]: garvis_2024-01-15.json.gz, project2_2024-01-10.json, ...
```

### Neue Tools (v5.3)

| Tool | Zweck |
|------|-------|
| `chainguard_analyze_code` | AST-Analyse für Code-Struktur |
| `chainguard_detect_architecture` | Framework & Pattern erkennen |
| `chainguard_memory_export` | Memory exportieren (JSON/JSONL, optional gzip) |
| `chainguard_memory_import` | Memory importieren (merge/replace) |
| `chainguard_list_exports` | Verfügbare Export-Dateien auflisten |

---

## v5.1.0 Features

### Long-Term Memory - Semantische Suche im Code

Chainguard kann jetzt die gesamte Codebase indexieren und semantische Fragen beantworten!

#### Memory initialisieren
```python
chainguard_memory_init()
# → 🧠 Initializing Long-Term Memory...
#   Indexing: 347 files (py, php, js, ts, tsx)
#   Duration: 2m 34s
#   Storage: 45 MB
#   ✓ Memory ready for semantic search
```

#### Semantische Suche
```python
chainguard_memory_query(query="Wo wird die Authentifizierung gehandhabt?")
# → 🔍 Results for "Wo wird die Authentifizierung gehandhabt?":
#
#   1. src/Auth/AuthController.php (0.92)
#      → Handles login, logout, password reset
#
#   2. src/Middleware/AuthMiddleware.php (0.87)
#      → JWT token validation, session checks
#
#   3. config/auth.php (0.71)
#      → Auth configuration, guards, providers
```

#### Memory aktualisieren
```python
# Nach großen Änderungen
chainguard_memory_update(action="reindex_file", file_path="src/NewFeature.php")

# Erkenntnisse speichern
chainguard_memory_update(
    action="add_learning",
    learning="Die Auth-Logik verwendet JWT mit 24h Expiry"
)

# Veraltete Einträge entfernen
chainguard_memory_update(action="cleanup")
```

#### Deep Logic Summaries
```python
chainguard_memory_summarize(file="src/PaymentService.php")
# → 📝 Summary: PaymentService.php
#
#   Purpose: Handles all payment processing
#
#   Key Functions:
#   - processPayment(): Validates card, charges via Stripe API
#   - refund(): Issues partial/full refunds
#   - validateCard(): Luhn check + expiry validation
#
#   Dependencies: Stripe SDK, Logger, UserRepository
```

### Neue Tools (v5.1)

| Tool | Zweck |
|------|-------|
| `chainguard_memory_init` | Memory initialisieren (indexiert Codebase) |
| `chainguard_memory_query` | Semantische Suche ("Wo ist X?") |
| `chainguard_memory_update` | Memory aktualisieren (reindex/learn/cleanup) |
| `chainguard_memory_status` | Memory-Status und Statistiken |
| `chainguard_memory_summarize` | Deep Logic Summaries generieren |

### Memory-Anforderungen

```bash
pip install chromadb sentence-transformers
```

**RAM-Verbrauch:** 1-2 GB (daher standardmäßig deaktiviert)

**Aktivieren:**
```python
# In ~/.chainguard/chainguard/config.py:
MEMORY_ENABLED = True
```

---

## v5.0.0 Features

### Task-Mode System - Flexibel für alle Aufgaben!

Das fundamentale Problem: Chainguard war zu Code-zentrisch. Syntax-Validierung, DB-Schema-Checks, HTTP-Tests - alles sinnvoll für Programmierung, aber störend bei:
- **Bücher schreiben** → Keine Syntax-Checks für Markdown!
- **Server verwalten** → Keine DB-Pflicht bei WordPress CLI!
- **Recherche** → Keine HTTP-Tests bei Analyse-Tasks!

**v5.0 löst das durch den Task-Mode:**

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

### Task-Modi im Überblick

| Modus | Features ON | Features OFF |
|-------|-------------|--------------|
| **programming** | Syntax-Check, DB-Pflicht, HTTP-Tests, Scope-Enforcement | - |
| **content** | Word-Count, Chapter-Tracking, File-Tracking | Syntax, DB, HTTP, Blockaden |
| **devops** | Command-Logging, Checkpoints, Health-Checks, Config-Validation | Code-Syntax, DB-Pflicht |
| **research** | Source-Tracking, Fact-Indexing | Syntax, DB, HTTP, Blockaden |
| **generic** | File-Tracking | Alles andere |

### Automatische Modus-Erkennung

Der Modus wird **vom LLM entschieden** (nicht deterministisch!):

1. **Tool-Description Injection**: Claude bekommt Modus-Optionen in der Tool-Beschreibung
2. **Semantisches Verstehen**: LLM erkennt "Kapitel schreiben" → content, "Server einrichten" → devops
3. **Fallback Auto-Detection**: Keywords + Dateimuster als Hinweis

```python
# LLM entscheidet basierend auf Kontext:
chainguard_set_scope(
    description="WordPress auf Server einrichten",
    mode="devops"  # LLM wählt basierend auf "WordPress", "Server"
)
```

### Neue Mode-spezifische Tools

#### Content Mode
| Tool | Zweck |
|------|-------|
| `chainguard_word_count` | Zeigt Wort-Zählung für aktuellen Scope |
| `chainguard_track_chapter` | Trackt Kapitel-Status (draft/review/done) |

#### DevOps Mode
| Tool | Zweck |
|------|-------|
| `chainguard_log_command` | Protokolliert ausgeführte CLI-Commands |
| `chainguard_checkpoint` | Erstellt Checkpoint vor kritischen Änderungen |
| `chainguard_health_check` | Prüft Endpoints auf Verfügbarkeit |

#### Research Mode
| Tool | Zweck |
|------|-------|
| `chainguard_add_source` | Fügt Quelle mit Relevanz hinzu |
| `chainguard_index_fact` | Indexiert Fakt mit Konfidenz-Level |
| `chainguard_sources` | Zeigt alle gesammelten Quellen |
| `chainguard_facts` | Zeigt alle indexierten Fakten |

### Context Injection per Mode

Jeder Modus injiziert spezifische Anweisungen:

```
────────────────────────────────────────
📝 CONTENT-MODUS - Flexibles Schreiben:

- Keine Syntax-Validierung (Texte, nicht Code)
- Keine Blockaden - freies kreatives Arbeiten
- Word-Count: chainguard_word_count()

Tipp: Nutze acceptance_criteria als Kapitel-Checkliste!
────────────────────────────────────────
```

### Migration von v4.x

**Keine Änderung nötig!** Bestehende Workflows funktionieren weiterhin:
- Default-Mode ist `programming`
- Alle v4.x Tools unverändert
- Backwards-kompatibel

---

## v4.19.0 Features

### HARD ENFORCEMENT via PreToolUse Hook
Das fundamentale Problem von v4.16 und früher war: Claude konnte Warnungen ignorieren und Regeln umgehen.

**v4.19 löst das durch echte BLOCKADEN + Auto-Marker:**

```
┌─────────────────────────────────────────────────┐
│  User Request                                    │
│       ↓                                          │
│  Claude will Edit aufrufen                       │
│       ↓                                          │
│  ┌───────────────────────────────────────────┐  │
│  │ PreToolUse Hook (chainguard_enforcer.py)  │  │
│  │ → Liest enforcement-state.json            │  │
│  │ → Prüft: DB-Schema geladen?               │  │
│  │ → Prüft: Blocking Alerts?                 │  │
│  │ → exit(2) wenn nicht OK → BLOCKIERT!      │  │
│  └───────────────────────────────────────────┘  │
│       ↓ (nur wenn Hook OK)                       │
│  Edit wird ausgeführt                            │
└─────────────────────────────────────────────────┘
```

### Neue Dateien

| Datei | Zweck |
|-------|-------|
| `hooks/chainguard_enforcer.py` | PreToolUse Hook - blockiert Edit/Write |
| `enforcement-state.json` | Minimaler State für Hook (vom MCP geschrieben) |

### Blockade-Regeln

1. **Schema-Dateien ohne DB-Inspektion**: Edit/Write auf `.sql`, `migration`, etc. wird BLOCKIERT bis `chainguard_db_schema()` aufgerufen wurde
2. **Blocking Alerts**: Edit/Write wird BLOCKIERT wenn nicht-bestätigte blocking Alerts existieren

### Hook-Konfiguration

Der Installer konfiguriert automatisch:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": "python3 ~/.chainguard/hooks/chainguard_enforcer.py"}]
      }
    ]
  }
}
```

---

## v4.12.0 Features

### Database Inspector - Keine SQL-Fehler mehr!
- **Live-Schema-Abfrage**: Verifizierte Feldnamen statt Raten
- **MySQL/PostgreSQL/SQLite**: Alle gängigen Datenbanken unterstützt
- **TTL-Cache**: Schema wird 5 Minuten gecacht (konfigurierbar)
- **Token-effizient**: Kompakte Darstellung (~50-100 Tokens)
- **Scope-gebunden**: Credentials nur im Memory, verschwinden mit Scope

> **Hinweis zu Sonderzeichen im Passwort:**
> Passwörter mit Sonderzeichen wie `!`, `@`, `#` etc. werden korrekt unterstützt.
> Falls Verbindungsprobleme auftreten, prüfe:
> 1. MySQL-Authentifizierungsmethode (caching_sha2_password vs mysql_native_password)
> 2. Ob das Passwort korrekt übergeben wird (nicht durch Shell-Escaping verändert)
> 3. Die Fehlermeldung enthält jetzt Hinweise wenn Sonderzeichen erkannt werden

### DB-Inspector Workflow

```python
# 1. Datenbankverbindung herstellen
chainguard_db_connect(
    host="localhost",
    user="root",
    password="root",
    database="knowledge",
    db_type="mysql"
)
# → ✓ Connected to knowledge (mysql 8.0.32)

# 2. Schema abrufen
chainguard_db_schema()
# → 📊 Database: knowledge (mysql 8.0.32)
#
#   users (4 cols, ~5 rows)
#   ├─ id: INT PK AUTO
#   ├─ username: VARCHAR(255) UNIQUE
#   ├─ email: VARCHAR(255)
#   └─ created_at: DATETIME
#
#   articles (6 cols, ~50 rows)
#   ├─ id: INT PK AUTO
#   ├─ title: VARCHAR(255)
#   ├─ content: TEXT
#   ├─ author_id: INT FK→users.id
#   └─ created_at: DATETIME

# 3. Jetzt korrekter SQL-Query:
$stmt = $pdo->prepare("SELECT id, username FROM users");
#                              ^^^^^^^^
#                              Exakter Feldname - kein Raten!

# 4. Einzelne Tabelle mit Sample-Daten
chainguard_db_table(table="users", sample=True)
# → Zeigt 5 Beispielzeilen
```

### Neue Tools (v4.12)

| Tool | Zweck |
|------|-------|
| `chainguard_db_connect` | Datenbankverbindung herstellen |
| `chainguard_db_schema` | Schema aller Tabellen abrufen (gecacht) |
| `chainguard_db_table` | Details einer Tabelle + Sample-Daten |
| `chainguard_db_disconnect` | Verbindung trennen, Cache löschen |

## v4.11.0 Features

### Error Memory System - Lerne aus Fehlern
- **Automatisches History-Log**: Jede Änderung wird dokumentiert (JSONL, append-only)
- **Error-Index**: Fehler werden indexiert für schnelles Nachschlagen
- **Auto-Suggest**: Bei bekannten Fehlern wird automatisch die Lösung vorgeschlagen
- **Token-effizient**: Kostet nur bei Fehlern etwas (0 Token bei Erfolg)

### Auto-Suggest Workflow

```python
# 1. Fehler tritt auf
chainguard_track(file="UserController.php", ctx="🔗")
→ "✗ PHP Syntax: unexpected }

   💡 Similar error fixed before:
      - *Controller.php (2d ago)
        → Missing semicolon before }"

# 2. Nach dem Fix - Resolution dokumentieren
chainguard_learn(resolution="Missing semicolon before closing brace")
→ "✓ Resolution dokumentiert"

# 3. Später: Fehler-History durchsuchen
chainguard_recall(query="php syntax Controller")
→ "🔍 2 Ergebnisse:
   1. *Controller.php - unexpected } → Missing semicolon"
```

### Neue Tools (v4.11)

| Tool | Zweck |
|------|-------|
| `chainguard_recall` | Durchsucht Error-History nach ähnlichen Problemen |
| `chainguard_history` | Zeigt Change-Log für aktuellen Scope |
| `chainguard_learn` | Dokumentiert einen Fix für zukünftige Auto-Suggests |

## v4.10.0 Features

### Test Runner - Technologie-agnostisch
- **Beliebiges Framework**: PHPUnit, Jest, pytest, mocha, vitest, etc.
- **Benutzer-definierter Command**: Flexibel konfigurierbar
- **Auto-Detection**: Erkennt Framework anhand des Outputs
- **Fehler-Tracking**: Speichert Ergebnisse, erstellt Alerts bei Failures

### Test Runner Workflow

```python
# 1. Einmalig konfigurieren (pro Projekt)
chainguard_test_config(
    command="./vendor/bin/phpunit",
    args="tests/ --colors=never"
)

# 2. Tests ausführen
chainguard_run_tests()
→ "✓ phpunit: 23/23 tests passed
   Duration: 4.2s"

# 3. Bei Fehler
chainguard_run_tests()
→ "✗ phpunit: 22/23 tests (1 failed)
   Duration: 3.8s

   Errors:
   • FAILED: LoginTest::testInvalidPassword
   • Expected 401, got 200"

# 4. Status prüfen
chainguard_test_status()
→ "Test Status: ✗ 22/23 (2m ago)"
```

### Unterstützte Frameworks

| Framework | Detection Pattern |
|-----------|------------------|
| PHPUnit | `OK (X tests)`, `FAILURES!` |
| Jest | `Tests: X passed, Y total` |
| pytest | `X passed`, `X failed` |
| mocha | `X passing`, `X failing` |
| vitest | `X passed`, `X failed` |
| Generisch | Exit-Code 0 = PASS |

## v4.8.0 Features

### Handler-Registry Pattern
- **Decorator-basierte Handler**: `@handler.register("tool_name")`
- **Testbar**: Jeder Handler ist eine separate Funktion
- **Erweiterbar**: Neue Tools einfach hinzufügen

### TTL-LRU Cache
- **Memory-bounded + Zeit-limitiert**: Items verfallen nach TTL
- **Generic**: `TTLLRUCache[T]` für beliebige Typen
- **Cleanup**: Automatische Bereinigung abgelaufener Einträge

### Async Checklist-Ausführung
- **Parallele Ausführung**: `run_all_async()` führt Checks parallel aus
- **Non-blocking**: `asyncio.create_subprocess_exec()`
- **Schneller**: N Checks gleichzeitig statt sequentiell

### Memory-safe HTTP Sessions
- **TTLLRUCache**: Max 50 Sessions, 24h TTL
- **Kein Memory Leak**: Alte Sessions werden automatisch entfernt

### Async JSON-Validierung
- **aiofiles**: JSON-Dateien werden async gelesen
- **Non-blocking**: Event Loop wird nicht blockiert

## v4.6.0 Features (NEU!)

### Context-Check mit Canary-Parameter
- **Problem**: Claude Code verliert manchmal den CLAUDE.md Kontext bei langen Sessions
- **Lösung**: `ctx="🔗"` Parameter als "Canary" - wenn er fehlt, ist der Kontext verloren
- **Auto-Refresh**: MCP gibt automatisch die wichtigsten Regeln zurück wenn ctx fehlt
- **Selbstheilend**: Claude lernt die Regeln neu und gibt ctx wieder mit

**So funktioniert's:**
```python
# Mit Kontext - kurze Response
chainguard_status(ctx="🔗")
→ "proj|impl|5F ✓"

# Ohne Kontext (Canary fehlt) - Auto-Refresh!
chainguard_status()
→ "proj|impl|5F ✓

⚠️ CHAINGUARD CONTEXT REFRESH
Wichtige Regeln: ctx='🔗' bei jedem Aufruf..."
```

## v4.5.0 Features

### Python & TypeScript Syntax-Validierung
- **Python**: `chainguard_track` validiert jetzt `.py` Dateien mit `python3 -m py_compile`
- **TypeScript/TSX**: `.ts` und `.tsx` Dateien werden mit `npx tsc --noEmit` geprüft
- Fehler werden sofort gemeldet - nicht erst im Browser/Runtime

### Batch-Tracking für mehrere Dateien
```python
chainguard_track_batch(files=["a.py", "b.ts", "c.php"])
# → Effizienter als 3x chainguard_track
# → Validiert alle Dateien, zeigt Zusammenfassung
```

### Präzisere Impact-Patterns
- **Keine False-Positives mehr**: "test" matched nicht mehr "latest.php"
- **Match-Types**: exact, suffix, prefix, contains
- **Mehr Patterns**: TypeScript types, Docker, package.json, etc.

### Konstanten statt Magic Numbers
- Alle Limits jetzt als Konstanten definiert (MAX_CHANGED_FILES, etc.)
- Bessere Wartbarkeit und Konfigurierbarkeit

### Phase-Enum
- Type-safe Phases: `Phase.PLANNING`, `Phase.IMPLEMENTATION`, etc.
- Backward-compatible (String-Serialisierung)

## v4.4.0 Features

### Scope-Optimierung für lange Descriptions
- **Empfohlenes Limit**: Description max 500 Zeichen
- **Warnung**: Bei langer Description automatischer Strukturierungs-Hinweis
- **Token-Sparend**: `chainguard_context` zeigt nur 200 Zeichen Preview
- **Keine LLM-API nötig**: Alles reine Python-String-Logik

**Best Practice für komplexe Projekte:**
```python
# NICHT SO:
description="500+ Wörter detaillierte Beschreibung..."

# BESSER SO:
chainguard_set_scope(
    description="E-Commerce mit 7 Phasen",  # Kurz!
    acceptance_criteria=[
        "Phase 1: Auth mit 2FA",
        "Phase 2: Produktkatalog",
        "Phase 3: Warenkorb",
        # ... Details als checkbare Kriterien
    ]
)
```

## v4.3.1 Features

### 2-Schritt-Finish mit Impact-Check
- **`chainguard_finish`** - Zeigt erst Impact-Check mit geänderten Dateien
- **Pattern-Erkennung** - Erkennt automatisch vergessene Updates:
  - CLAUDE.md → Template auch aktualisieren?
  - chainguard/*.py → Nach ~/.chainguard/chainguard/ kopieren?
  - Controller.php → Tests vorhanden?
- **`chainguard_finish(confirmed=true)`** - Bestätigt und schließt ab
- Mit `force=true` überschreibbar

### Warnungen bei validate/set_phase
- `chainguard_validate(status="PASS")` warnt wenn Kriterien offen
- `chainguard_set_phase(phase="done")` warnt wenn nicht alles erfüllt

## v4.2.0 Features

### Automatische Syntax-Validierung
- `chainguard_track` validiert jetzt **automatisch PHP/JS/JSON**
- Fehler werden **sofort** erkannt - nicht erst im Browser
- `php -l` für PHP, `node --check` für JS

### HTTP Endpoint-Testing mit Sessions
- `chainguard_set_base_url` - Base URL setzen
- `chainguard_test_endpoint` - Endpoints testen mit Session-Support
- `chainguard_login` - Einloggen und Session speichern
- Erkennt automatisch Auth-Anforderungen (401, 403, Login-Redirect)

## v4.1.2 Fixes

- **Full Async Read** - list_all_projects_async() komplett non-blocking
- **Async Resource** - read_resource() nutzt jetzt async

## v4.1.1 Fixes

- **Thread-safe Lock Init** - Race Condition bei AsyncFileLock behoben
- **Full Async I/O** - path.exists(), mkdir() jetzt auch async
- **Memory Limit** - out_of_scope_files auf 20 begrenzt

## v4.1 Performance-Upgrades

- **True Async I/O** - Non-blocking file operations mit aiofiles
- **Write Debouncing** - 500ms Batching, ~90% weniger Disk-Writes
- **LRU Cache** - Memory-bounded (max 20 Projekte)
- **Git Call Caching** - 5min TTL, vermeidet redundante Subprocess-Calls
- **Path Sanitization** - Security-Hardening gegen Path-Traversal

## Workflow

### 1. Task starten (mit Mode!)
```python
# Programming (Standard - Code, Bugs, Features)
chainguard_set_scope(
  description="Feature X implementieren",
  mode="programming",                      # Optional: Default
  modules=["src/feature/*.ts"],
  acceptance_criteria=["Tests grün", "Docs aktualisiert"]
)

# Content (Bücher, Artikel, Dokumentation)
chainguard_set_scope(
  description="Kapitel 3 schreiben",
  mode="content",
  acceptance_criteria=["Kapitel 3 fertig", "5000 Wörter"]
)

# DevOps (Server, WordPress, CLI)
chainguard_set_scope(
  description="WordPress einrichten",
  mode="devops",
  acceptance_criteria=["Site live", "SSL aktiv"]
)

chainguard_set_phase(phase="implementation")
```

### 2. Arbeiten (Tracking mit Auto-Validierung)
```
# Nach Edits - validiert automatisch PHP/JS/JSON!
# WICHTIG: ctx="🔗" immer mitgeben!
chainguard_track(file="app/Http/Controllers/UserController.php", ctx="🔗")
```

**NEU in v4.2:** `chainguard_track` führt jetzt **automatisch Syntax-Checks** durch:
- **PHP**: `php -l` - findet Parse Errors sofort
- **JavaScript**: `node --check` - findet Syntax Errors
- **JSON**: Validiert JSON-Struktur

```
# Beispiel: PHP Fehler wird sofort erkannt
chainguard_track(file="Controller.php", ctx="🔗")
→ ✗ PHP Syntax: Parse error: syntax error, unexpected '}'
```

Silent wenn alles OK. Fehler werden **sofort** gemeldet - nicht erst im Browser!

### 3. Status prüfen (nur bei Bedarf)
```
chainguard_status(ctx="🔗")   # Eine Zeile: "project|impl|F5/V3 Feature X..."
```

### 4. Abschließen (NEU in v4.3)
```
chainguard_check_criteria(criterion="...", fulfilled=true)  # Kriterien markieren
chainguard_finish                            # Prüft alles automatisch!
```

**`chainguard_finish` prüft:**
- Alle Akzeptanzkriterien erfüllt?
- Checklist bestanden?
- Keine offenen Alerts?
- Keine Syntax-Fehler?

**Blockiert** wenn nicht 100% erfüllt! Mit `force=true` überschreibbar.

## Tools (v6.5)

### Core (täglich nutzen)
| Tool | Zweck |
|------|-------|
| `chainguard_set_scope` | Definiert Task-Grenzen, **mode** und Kriterien |
| `chainguard_track` | Trackt Änderungen + **AUTO-VALIDIERT** (mode-abhängig) |
| `chainguard_track_batch` | Mehrere Dateien auf einmal tracken |
| `chainguard_status` | Ultra-kompakte Statuszeile |
| `chainguard_set_phase` | Phase setzen: planning/implementation/testing/review/done |
| `chainguard_finish` | Vollständiger Abschluss mit Prüfung |

### Content Mode (NEU v5.0)
| Tool | Zweck |
|------|-------|
| `chainguard_word_count` | Zeigt Wort-Zählung für aktuellen Scope |
| `chainguard_track_chapter` | Trackt Kapitel-Status (draft/review/done) |

### DevOps Mode (NEU v5.0)
| Tool | Zweck |
|------|-------|
| `chainguard_log_command` | Protokolliert ausgeführte CLI-Commands |
| `chainguard_checkpoint` | Erstellt Checkpoint vor kritischen Änderungen |
| `chainguard_health_check` | Prüft Endpoints auf Verfügbarkeit |

### Research Mode (NEU v5.0)
| Tool | Zweck |
|------|-------|
| `chainguard_add_source` | Fügt Quelle mit Relevanz hinzu |
| `chainguard_index_fact` | Indexiert Fakt mit Konfidenz-Level |
| `chainguard_sources` | Zeigt alle gesammelten Quellen |
| `chainguard_facts` | Zeigt alle indexierten Fakten |

### Test Runner (v4.10)
| Tool | Zweck |
|------|-------|
| `chainguard_test_config` | Test-Command konfigurieren (PHPUnit, Jest, pytest, etc.) |
| `chainguard_run_tests` | Tests ausführen mit Auto-Detection |
| `chainguard_test_status` | Letztes Test-Ergebnis anzeigen |

### Error Memory (v4.11)
| Tool | Zweck |
|------|-------|
| `chainguard_recall` | Durchsucht Error-History nach ähnlichen Problemen |
| `chainguard_history` | Zeigt Change-Log für aktuellen Scope |
| `chainguard_learn` | Dokumentiert einen Fix für zukünftige Auto-Suggests |

### Database Inspector (v4.12)
| Tool | Zweck |
|------|-------|
| `chainguard_db_connect` | Datenbankverbindung herstellen (MySQL/PostgreSQL/SQLite) |
| `chainguard_db_schema` | Schema aller Tabellen abrufen (5 min Cache) |
| `chainguard_db_table` | Details einer Tabelle + optionale Sample-Daten |
| `chainguard_db_disconnect` | Verbindung trennen und Cache löschen |

### Analysis (v4.7)
| Tool | Zweck |
|------|-------|
| `chainguard_analyze` | Pre-Flight Check: Metriken, Patterns, Hotspots, Checkliste |

### Validation
| Tool | Zweck |
|------|-------|
| `chainguard_check_criteria` | Zeigt/setzt Akzeptanzkriterien |
| `chainguard_run_checklist` | Führt automatische Checks aus |
| `chainguard_validate` | Speichert PASS/FAIL (warnt bei offenen Punkten) |

### HTTP Testing (v4.2)
| Tool | Zweck |
|------|-------|
| `chainguard_set_base_url` | Base URL setzen (z.B. `http://localhost:8888/app`) |
| `chainguard_test_endpoint` | Endpoint testen mit Session-Support |
| `chainguard_login` | Einloggen, Session für spätere Requests speichern |
| `chainguard_clear_session` | Session/Cookies löschen |

### Utility
| Tool | Zweck |
|------|-------|
| `chainguard_context` | Voller Kontext (sparsam nutzen!) |
| `chainguard_alert` | Problem markieren |
| `chainguard_clear_alerts` | Alerts bestätigen |
| `chainguard_projects` | Alle Projekte listen |
| `chainguard_config` | Konfiguration |

### Long-Term Memory (v5.1)
| Tool | Zweck |
|------|-------|
| `chainguard_memory_init` | Memory initialisieren (indexiert Codebase) |
| `chainguard_memory_query` | Semantische Suche ("Wo ist Auth?") |
| `chainguard_memory_update` | Memory aktualisieren (reindex/learn/cleanup) |
| `chainguard_memory_status` | Memory-Status und Statistiken |
| `chainguard_memory_summarize` | Deep Logic Summaries generieren |

### AST & Architektur (v5.3)
| Tool | Zweck |
|------|-------|
| `chainguard_analyze_code` | AST-Analyse für Code-Struktur |
| `chainguard_detect_architecture` | Framework & Pattern erkennen |
| `chainguard_memory_export` | Memory exportieren (JSON/JSONL) |
| `chainguard_memory_import` | Memory importieren |
| `chainguard_list_exports` | Verfügbare Exports auflisten |

### Halluzination Prevention (v5.5)
| Tool | Zweck |
|------|-------|
| `chainguard_symbol_mode` | Validierungsmodus (OFF/WARN/STRICT/ADAPTIVE) |
| `chainguard_validate_symbols` | Funktionsaufrufe gegen Codebase prüfen |
| `chainguard_validate_packages` | Imports gegen Dependencies prüfen (Slopsquatting) |

### Kanban-System (v6.5)
| Tool | Zweck |
|------|-------|
| `chainguard_kanban_init` | **Board initialisieren mit Preset oder Custom-Spalten** |
| `chainguard_kanban` | Board anzeigen (kompakt) |
| `chainguard_kanban_show` | **Vollständige grafische Ansicht mit allen Details** |
| `chainguard_kanban_add` | Card hinzufügen (mit Priority, Tags, Detail-MD) |
| `chainguard_kanban_move` | Card verschieben (backlog → in_progress → done) |
| `chainguard_kanban_detail` | Card-Details laden (inkl. verknüpfte MD-Datei) |
| `chainguard_kanban_update` | Card bearbeiten (Title, Priority, Tags, Dependencies) |
| `chainguard_kanban_delete` | Card löschen |
| `chainguard_kanban_archive` | Card archivieren (aus Board entfernen, Historie behalten) |
| `chainguard_kanban_history` | Archivierte Cards anzeigen |

## HTTP Testing Workflow (NEU v4.2)

### Setup
```
chainguard_set_base_url(base_url="http://localhost:8888/myapp")
```

### Endpoint testen (ohne Auth)
```
chainguard_test_endpoint(url="/api/public/status")
→ ✓ GET 200
```

### Protected Endpoint → Auth erkannt
```
chainguard_test_endpoint(url="/api/users")
→ 🔐 Auth required (302): Redirect to login
→ Use chainguard_login to authenticate
```

### Einloggen
```
chainguard_login(
  login_url="/login",
  username="admin@example.com",
  password="secret123"
)
→ ✓ Logged in as admin@example.com
   Session stored for future requests
```

### Protected Endpoint → jetzt funktioniert's
```
chainguard_test_endpoint(url="/api/users")
→ ✓ GET 200
   [{"id":1,"name":"Admin"}, ...]
```

## Entfernte Features (v4.0)

Diese Features wurden entfernt - sie duplizierten andere Tools oder verbrauchten zu viel Kontext:

| Entfernt | Grund | Alternative |
|----------|-------|-------------|
| `chainguard_track_dependency` | LSP macht das besser | IDE/LSP nutzen |
| `chainguard_impact_analysis` | LSP macht das besser | IDE/LSP nutzen |
| `chainguard_save_learning` | Dupliziert laas_remember | `laas_remember` MCP |
| `chainguard_trends` | Selten nützlich | In `chainguard_context` integriert |
| `chainguard_brief` | Ersetzt durch `chainguard_status` | `chainguard_status` |

## Checklist-Beispiele

```json
{
  "checklist": [
    {"item": "Controller", "check": "test -f app/Http/Controllers/AuthController.php"},
    {"item": "Route", "check": "grep -q 'auth' routes/web.php"},
    {"item": "Test", "check": "test -f tests/Feature/AuthTest.php"}
  ]
}
```

**Erlaubte Commands:** `test`, `grep`, `ls`, `cat`, `head`, `wc`, `find`, `stat`, `php`, `node`, `python`, `npm`, `composer`

## Best Practices

1. **Tracking ist optional** - nur nutzen wenn Scope-Kontrolle wichtig ist
2. **Status nur bei Bedarf** - nicht nach jeder Änderung abfragen
3. **Context sparsam** - `chainguard_context` nur wenn Details wirklich nötig
4. **Validation am Ende** - nicht nach jeder kleinen Änderung

## Performance-Vergleich

| Szenario | v5.0 | v6.0 |
|----------|------|------|
| 10 Dateiänderungen tracken | ~150 tok | ~150 tok |
| `chainguard_projects` (10 items) | ~120 tok | **~70 tok** (TOON) |
| `chainguard_history` (20 items) | ~300 tok | **~180 tok** (TOON) |
| Content-Mode (keine Syntax) | 0 tok | 0 tok |
| Memory RAM-Verbrauch | 1-2GB | **0 MB** (disabled) |
| Disk-Writes bei 10 Tracks | 2 | 2 |
| Checklist (10 Items) | ~1s | ~1s |

**v6.0: TOON Token-Optimierung + Memory standardmäßig deaktiviert.**

## Installation

```bash
pip install mcp aiofiles aiohttp  # aiohttp optional für HTTP-Testing
```
