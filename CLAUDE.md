<!-- CHAINGUARD-MANDATORY-START v6.8.0 -->

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
# v6.8: Auto-Refresh stale Memory, PRD Auto-Detection
# BLOCKIERT wenn DB-Schema nicht geprüft wurde!
#
# ================================================

## CHAINGUARD v6.8 - PFLICHT-ANWEISUNGEN (HARD ENFORCEMENT!)

| # | PFLICHT-AKTION | WANN |
|---|----------------|------|
| 1 | `chainguard_set_scope(...)` | **ALLERERSTE AKTION bei jedem Task!** |
| 2 | `chainguard_db_connect() + chainguard_db_schema()` | **VOR jeder DB/Schema-Arbeit! (BLOCKIERT sonst!)** |
| 3 | `chainguard_track(file="...", ctx="...")` | Nach JEDER Dateiänderung |
| 4 | `chainguard_test_endpoint(...)` | **Bei Web-Projekten: VOR finish!** |
| 5 | `chainguard_kanban_show()` | **Bei komplexen Projekten: Überblick behalten!** |
| 6 | `chainguard_finish(confirmed=True)` | Am Task-Ende |

### Minimaler Workflow

```python
# 1. Scope setzen (PFLICHT!)
chainguard_set_scope(description="Was du baust", working_dir="/pfad")
# 2. Bei DB-Arbeit: chainguard_db_connect() + chainguard_db_schema()
# 3. Arbeiten + Tracken: chainguard_track(file="...", ctx="...")
# 4. Web-Projekte: chainguard_test_endpoint(url="/route")
# 5. Komplexe Projekte: chainguard_kanban_show()
# 6. Abschliessen: chainguard_finish(confirmed=True)
```

### Context-Canary: `ctx="..."`

Bei JEDEM Chainguard-Aufruf `ctx="..."` mitgeben! Fehlt er -> Kontext verloren -> Auto-Refresh.

### Kanban (v6.5) - Für komplexe Projekte

```python
chainguard_kanban_init(preset="programming")  # oder: content, devops, research
chainguard_kanban_add(title="Task", priority="high", detail="## MD")
chainguard_kanban_move(card_id="abc", to_column="in_progress")
chainguard_kanban_show()  # Grafische Ansicht
```

**Struktur:** `.claude/kanban.yaml`, `.claude/cards/<id>.md`
<!-- CHAINGUARD-MANDATORY-END -->



# CHAINGUARD v6.8.0 - Vollständige Dokumentation

> **Modulare Struktur:** MCP-Server läuft von `~/.chainguard/` - NICHT aus diesem Projekt!
> **Quick-Sync:** `rm -rf ~/.chainguard/chainguard && cp -r src/mcp-server/chainguard ~/.chainguard/ && cp src/mcp-server/chainguard_mcp.py ~/.chainguard/ && cp src/hooks/chainguard_enforcer.py ~/.chainguard/hooks/ && cp src/templates/CHAINGUARD.md.block ~/.chainguard/templates/`

## Modulare Architektur

```
~/.chainguard/
├── chainguard_mcp.py      ← Wrapper
└── chainguard/            ← Package (server.py, handlers.py, tools.py, models.py,
    │                         project_manager.py, validators.py, analyzers.py,
    │                         http_session.py, test_runner.py, history.py,
    │                         db_inspector.py, kanban.py, cache.py, checklist.py,
    │                         config.py, toon.py, utils.py)
```

## Unit-Tests

```bash
cd src/mcp-server && python3 -m pytest tests/ -v
```

**266+ Tests** in: test_cache.py, test_models.py, test_test_runner.py, test_history.py, test_db_inspector.py, test_task_mode.py, test_toon.py, test_kanban.py

## Task-Modi (v5.0+)

| Modus | Features ON | Features OFF |
|-------|-------------|--------------|
| **programming** (default) | Syntax-Check, DB-Pflicht, HTTP-Tests | - |
| **content** | Word-Count, Chapter-Tracking | Syntax, DB, HTTP |
| **devops** | Command-Logging, Checkpoints, Health-Checks | Syntax, DB |
| **research** | Source-Tracking, Fact-Indexing | Syntax, DB, HTTP |
| **generic** | File-Tracking | Alles andere |

## Kanban-System (v6.5)

Für mehrtägige Projekte mit >5 Tasks. Überlebt Session-Neustarts!

**Presets:** default, programming, content, devops, research, agile, simple

```python
chainguard_kanban_init(preset="programming")  # Oder: columns=["custom", "cols"]
chainguard_kanban_add(title="Task", priority="high", detail="## MD Content")
chainguard_kanban_move(card_id="abc", to_column="in_progress")
chainguard_kanban_show()  # Grafische Vollansicht
chainguard_kanban_archive(card_id="abc")  # Nach Fertigstellung
```

**Struktur:** `.claude/kanban.yaml`, `.claude/cards/<id>.md`, `.claude/archive.yaml`

## Halluzination Prevention (v5.5)

```python
chainguard_symbol_mode(mode="WARN")  # OFF, WARN, STRICT, ADAPTIVE
chainguard_validate_symbols(file="src/Controller.php")
chainguard_validate_packages(file="src/app.js")  # Slopsquatting Detection
```

## TOON Token-Optimierung (v6.0)

30-60% weniger Tokens für Array-Outputs. Automatisch aktiv für `chainguard_projects` und `chainguard_history`.

## Long-Term Memory (v5.1)

**AKTIVIERT auf dieser Installation.** (`MEMORY_ENABLED = True` in `config.py`)
Standard: Deaktiviert by default (1-2GB RAM). Aktivieren in `~/.chainguard/chainguard/config.py`: `MEMORY_ENABLED = True`

```python
chainguard_memory_init()  # Indexiert Codebase
chainguard_memory_query(query="Wo ist Auth?")
chainguard_memory_summarize(file="src/Service.php")
```

## Tool-Referenz

### Core
| Tool | Zweck |
|------|-------|
| `chainguard_set_scope` | Task-Grenzen, mode, Kriterien definieren |
| `chainguard_track` | Änderungen tracken + Auto-Validierung |
| `chainguard_track_batch` | Mehrere Dateien tracken |
| `chainguard_status` | Kompakte Statuszeile |
| `chainguard_set_phase` | Phase: planning/implementation/testing/review/done |
| `chainguard_finish` | Task abschliessen mit Prüfung |
| `chainguard_context` | Voller Kontext (sparsam!) |

### Kanban
| Tool | Zweck |
|------|-------|
| `chainguard_kanban_init` | Board mit Preset/Custom-Spalten |
| `chainguard_kanban` / `_show` | Board anzeigen (kompakt/voll) |
| `chainguard_kanban_add` | Card hinzufügen |
| `chainguard_kanban_move` | Card verschieben |
| `chainguard_kanban_detail` | Card-Details laden |
| `chainguard_kanban_update` | Card bearbeiten |
| `chainguard_kanban_delete` / `_archive` | Card löschen/archivieren |
| `chainguard_kanban_history` | Archiv anzeigen |

### Database
| Tool | Zweck |
|------|-------|
| `chainguard_db_connect` | DB-Verbindung (MySQL/PostgreSQL/SQLite) |
| `chainguard_db_schema` | Schema abrufen (5 min Cache) |
| `chainguard_db_table` | Tabellen-Details + Sample-Daten |
| `chainguard_db_disconnect` | Verbindung trennen |

### HTTP Testing
| Tool | Zweck |
|------|-------|
| `chainguard_set_base_url` | Base URL setzen |
| `chainguard_test_endpoint` | Endpoint testen |
| `chainguard_login` | Session speichern |
| `chainguard_clear_session` | Session löschen |

### Test Runner
| Tool | Zweck |
|------|-------|
| `chainguard_test_config` | Test-Command konfigurieren |
| `chainguard_run_tests` | Tests ausführen |
| `chainguard_test_status` | Letztes Ergebnis |

### Error Memory
| Tool | Zweck |
|------|-------|
| `chainguard_recall` | Error-History durchsuchen |
| `chainguard_history` | Change-Log anzeigen |
| `chainguard_learn` | Fix dokumentieren |

### Mode-spezifisch
| Tool | Mode | Zweck |
|------|------|-------|
| `chainguard_word_count` | content | Wort-Zählung |
| `chainguard_track_chapter` | content | Kapitel-Status |
| `chainguard_log_command` | devops | CLI-Commands loggen |
| `chainguard_checkpoint` | devops | Checkpoint erstellen |
| `chainguard_health_check` | devops | Endpoints prüfen |
| `chainguard_add_source` | research | Quelle hinzufügen |
| `chainguard_index_fact` | research | Fakt indexieren |
| `chainguard_sources` / `_facts` | research | Quellen/Fakten anzeigen |

### Analysis & Memory
| Tool | Zweck |
|------|-------|
| `chainguard_analyze` | Pre-Flight Check |
| `chainguard_analyze_code` | AST-Analyse |
| `chainguard_detect_architecture` | Framework erkennen |
| `chainguard_memory_init` | Memory initialisieren |
| `chainguard_memory_query` | Semantische Suche |
| `chainguard_memory_update` | Memory aktualisieren |
| `chainguard_memory_status` | Memory-Status |
| `chainguard_memory_summarize` | Logic Summaries |
| `chainguard_memory_export` / `_import` | Export/Import |

### Validation & Utility
| Tool | Zweck |
|------|-------|
| `chainguard_check_criteria` | Kriterien prüfen/setzen |
| `chainguard_run_checklist` | Checks ausführen |
| `chainguard_validate` | PASS/FAIL speichern |
| `chainguard_symbol_mode` | Validierungsmodus |
| `chainguard_validate_symbols` | Symbole prüfen |
| `chainguard_validate_packages` | Packages prüfen |
| `chainguard_alert` | Problem markieren |
| `chainguard_clear_alerts` | Alerts bestätigen |
| `chainguard_projects` | Projekte listen |
| `chainguard_config` | Konfiguration |

## Checklist-Beispiel

```json
{"checklist": [
  {"item": "Controller", "check": "test -f app/Http/Controllers/AuthController.php"},
  {"item": "Route", "check": "grep -q 'auth' routes/web.php"}
]}
```

**Erlaubte Commands:** test, grep, ls, cat, head, wc, find, stat, php, node, python, npm, composer

## Best Practices

1. **Tracking optional** - nur bei Scope-Kontrolle
2. **Status sparsam** - nicht nach jeder Änderung
3. **Context minimal** - nur wenn Details nötig
4. **Validation am Ende** - nicht ständig

## Installation

```bash
pip install mcp aiofiles aiohttp
```
