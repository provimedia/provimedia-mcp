# CHAINGUARD SYNC & INSTALL CHECKLISTE

> **WICHTIG:** Diese Datei bei JEDEM Update von Chainguard durcharbeiten!
> Verhindert, dass veraltete Templates im Live-System neuere Versionen überschreiben.

## Versionsprüfung

**Aktuelle Version:** Prüfe zuerst die Versionen:

```bash
# Lokale Version (Entwicklung)
grep "VERSION = " src/mcp-server/chainguard/config.py

# Live Version (~/.chainguard)
grep "VERSION = " ~/.chainguard/chainguard/config.py

# Template Version
grep "MANDATORY-START" src/templates/CHAINGUARD.md.block | head -1
grep "MANDATORY-START" ~/.chainguard/templates/CHAINGUARD.md.block | head -1
```

---

## Sync-Checkliste

### 1. Versionsnummern aktualisieren

| Datei | Zeile | Prüfen |
|-------|-------|--------|
| `src/mcp-server/chainguard/config.py` | `VERSION = "x.x.x"` | [ ] |
| `src/hooks/chainguard_enforcer.py` | `Enforcer Hook vx.x` | [ ] |
| `src/templates/CHAINGUARD.md.block` | `CHAINGUARD-MANDATORY-START vx.x.x` | [ ] |
| `templates/CLAUDE.md` | Titel `# CHAINGUARD vx.x.x` | [ ] |
| `installer/install.sh` | `CHAINGUARD_VERSION="x.x.x"` | [ ] |
| `CLAUDE.md` | Titel `# CHAINGUARD vx.x.x` | [ ] |

### 2. MCP Package synchronisieren

```bash
# Komplettes Package nach ~/.chainguard/ kopieren
rm -rf ~/.chainguard/chainguard
cp -r src/mcp-server/chainguard ~/.chainguard/
cp src/mcp-server/chainguard_mcp.py ~/.chainguard/

# Verifizieren
grep "VERSION = " ~/.chainguard/chainguard/config.py
```

### 3. Hooks synchronisieren

```bash
# Enforcer Hook (PreToolUse - blockiert Edit/Write bei Regelverstößen)
cp src/hooks/chainguard_enforcer.py ~/.chainguard/hooks/

# Memory-Inject Hook (UserPromptSubmit - injiziert Memory-Kontext VOR LLM)
cp src/hooks/chainguard_memory_inject.py ~/.chainguard/hooks/

# Scope-Reminder Hook (UserPromptSubmit - erinnert an set_scope wenn nicht gesetzt)
cp src/hooks/chainguard_scope_reminder.py ~/.chainguard/hooks/

# Verifizieren
grep "Enforcer Hook v" ~/.chainguard/hooks/chainguard_enforcer.py
grep "Memory Injection Hook v" ~/.chainguard/hooks/chainguard_memory_inject.py
ls -la ~/.chainguard/hooks/chainguard_scope_reminder.py
```

### 4. Templates synchronisieren

```bash
# CHAINGUARD.md.block (wird vom Hook genutzt!)
cp src/templates/CHAINGUARD.md.block ~/.chainguard/templates/

# CLAUDE.md Template
cp templates/CLAUDE.md ~/.chainguard/templates/

# Verifizieren
grep "MANDATORY-START" ~/.chainguard/templates/CHAINGUARD.md.block | head -1
```

### 5. Docs synchronisieren

```bash
cp -r docs/ ~/.chainguard/
```

### 6. Installer prüfen

```bash
# Version im Installer prüfen
grep "CHAINGUARD_VERSION" installer/install.sh
```

---

## Quick-Sync Befehl

Alles auf einmal synchronisieren:

```bash
# Vollständiger Sync
rm -rf ~/.chainguard/chainguard && \
cp -r src/mcp-server/chainguard ~/.chainguard/ && \
cp src/mcp-server/chainguard_mcp.py ~/.chainguard/ && \
cp src/hooks/chainguard_enforcer.py ~/.chainguard/hooks/ && \
cp src/hooks/chainguard_memory_inject.py ~/.chainguard/hooks/ && \
cp src/hooks/chainguard_scope_reminder.py ~/.chainguard/hooks/ && \
cp src/templates/CHAINGUARD.md.block ~/.chainguard/templates/ && \
cp templates/CLAUDE.md ~/.chainguard/templates/ && \
cp -r docs/ ~/.chainguard/ && \
echo "Sync abgeschlossen - Version:" && \
grep "VERSION = " ~/.chainguard/chainguard/config.py
```

---

## Nach dem Sync

1. **Claude Code neu starten** (Terminal schließen und neu öffnen)
2. **Testen:** `/clear` und dann eine Anfrage stellen
3. **Prüfen:** Hook sollte neue Version anzeigen

---

## Häufige Fehler

### Problem: Hook überschreibt mit alter Version

**Ursache:** `~/.chainguard/templates/CHAINGUARD.md.block` hat alte Version

**Lösung:**
```bash
cp src/templates/CHAINGUARD.md.block ~/.chainguard/templates/
```

### Problem: MCP Tools zeigen alte Version

**Ursache:** `~/.chainguard/chainguard/` nicht aktualisiert

**Lösung:**
```bash
rm -rf ~/.chainguard/chainguard
cp -r src/mcp-server/chainguard ~/.chainguard/
```

### Problem: Installer zeigt alte Version

**Ursache:** `installer/install.sh` nicht aktualisiert

**Lösung:** `CHAINGUARD_VERSION` in `installer/install.sh` anpassen

---

## Datei-Übersicht

| Quelle (Entwicklung) | Ziel (Live) | Zweck |
|---------------------|-------------|-------|
| `src/mcp-server/chainguard/` | `~/.chainguard/chainguard/` | MCP Server Package |
| `src/mcp-server/chainguard_mcp.py` | `~/.chainguard/chainguard_mcp.py` | MCP Wrapper |
| `src/hooks/chainguard_enforcer.py` | `~/.chainguard/hooks/chainguard_enforcer.py` | PreToolUse Enforcer Hook |
| `src/hooks/chainguard_memory_inject.py` | `~/.chainguard/hooks/chainguard_memory_inject.py` | UserPromptSubmit Memory Injection |
| `src/hooks/chainguard_scope_reminder.py` | `~/.chainguard/hooks/chainguard_scope_reminder.py` | UserPromptSubmit Scope Reminder |
| `src/templates/CHAINGUARD.md.block` | `~/.chainguard/templates/CHAINGUARD.md.block` | Hook-Template |
| `templates/CLAUDE.md` | `~/.chainguard/templates/CLAUDE.md` | Vollständiges Template |
| `docs/` | `~/.chainguard/docs/` | Dokumentation |
| `installer/install.sh` | - | Installer (bleibt im Repo) |
| `CLAUDE.md` | - | Projekt-spezifisch (wird vom Hook aktualisiert) |

---

## Modulstruktur (v6.4.5)

Das Chainguard MCP Server Package besteht aus folgenden Modulen:

### Core Module
| Modul | Zweck |
|-------|-------|
| `config.py` | Konstanten, Enums, Konfiguration |
| `models.py` | Datenmodelle (ScopeDefinition, ProjectState) |
| `project_manager.py` | Projekt-State-Management |
| `handlers.py` | Handler-Registry mit Tool-Handlern |
| `tools.py` | MCP Tool-Definitionen |
| `server.py` | MCP Server Setup |

### Validation & Analysis
| Modul | Zweck |
|-------|-------|
| `validators.py` | Syntax-Validierung (PHP, JS, JSON, Python, TS) |
| `analyzers.py` | Code-Analyse und Impact-Analyse |
| `checklist.py` | Async Checklist-Ausführung |

### Testing & HTTP
| Modul | Zweck |
|-------|-------|
| `test_runner.py` | Test-Ausführung (PHPUnit, Jest, pytest) |
| `http_session.py` | HTTP Session-Management |

### Memory System (v5.1+)
| Modul | Zweck |
|-------|-------|
| `memory.py` | Long-Term Memory mit ChromaDB |
| `embeddings.py` | Embedding Engine (sentence-transformers) |

### Phase 3 Features (v5.3+)
| Modul | Zweck |
|-------|-------|
| `ast_analyzer.py` | AST-basierte Code-Analyse (tree-sitter Fallback: Regex) |
| `architecture.py` | Architektur-Pattern-Erkennung (MVC, Clean, etc.) |
| `memory_export.py` | Memory Export/Import (JSON, JSONL) |

### Phase 4 Features (v5.4+)
| Modul | Zweck |
|-------|-------|
| `code_summarizer.py` | Deep Logic Extraction - menschenlesbare Code-Summaries |

### Phase 5 Features (v6.0+)
| Modul | Zweck |
|-------|-------|
| `xml_response.py` | XML Response System - strukturierte XML-Ausgabe für bessere Claude-Comprehension |
| `toon.py` | TOON Encoder - Token-Oriented Object Notation für 30-60% weniger Tokens |

### Phase 6 Features (v6.1+)
| Modul | Zweck |
|-------|-------|
| `symbol_validator.py` | Halluzinationsprävention - Erkennt falsche Funktionsaufrufe |
| `symbol_patterns.py` | Regex-Patterns für 7 Sprachen (PHP, JS, TS, Python, C#, Go, Rust) |
| `package_validator.py` | Slopsquatting-Detection - Erkennt halluzinierte Package-Imports |

### Phase 7 Features (v6.4+)
| Modul | Zweck |
|-------|-------|
| `db_credentials.py` | Persistente DB-Credentials mit XOR-Obfuskation (v6.4.0) |

**v6.4.5 Updates:**
- `models.py` - Symbol-Warnings in `get_completion_status()` (blockiert finish ohne force)
- `symbol_validator.py` - Docstring/Multi-line-Comment-Skipping
- `symbol_patterns.py` - Python stdlib erweitert (field, dataclass, Optional, Path, etc.)

### Utilities
| Modul | Zweck |
|-------|-------|
| `cache.py` | LRU Cache, TTL-LRU Cache, Git Cache |
| `history.py` | Error Memory System |
| `db_inspector.py` | Database Schema Inspection |
| `utils.py` | Path-Sanitization, Hilfsfunktionen |

---

## Optionale Dependencies

| Feature | Packages | Modul |
|---------|----------|-------|
| Long-Term Memory | `chromadb`, `sentence-transformers` | memory.py, embeddings.py |
| AST Analysis (präzise) | `tree-sitter`, `tree-sitter-python`, etc. | ast_analyzer.py |
| HTTP Testing | `aiohttp` | http_session.py |
| **PHPStan (v6.3)** | `phpstan` (via Composer) | validators.py |

Ohne diese Packages funktioniert Chainguard weiterhin - Features werden automatisch deaktiviert.

---

## PHPStan Integration (v6.3)

PHPStan erkennt Laufzeitfehler **VOR** der Code-Ausführung:
- Null-Zugriffe (`$user['id']` auf null)
- Typ-Fehler (string statt int)
- Undefinierte Methoden

### Installation

```bash
# Global (empfohlen)
composer global require phpstan/phpstan

# Oder per Projekt
composer require --dev phpstan/phpstan
```

### Konfiguration

In `~/.chainguard/chainguard/config.py`:

```python
PHPSTAN_ENABLED = True   # Aktiviert (Standard)
PHPSTAN_LEVEL = 5        # Level 0-9 (5 empfohlen)
```

### Level-Übersicht

| Level | Prüft |
|-------|-------|
| 0-2 | Basics (undefined vars) |
| 3-4 | Typ-Hints |
| **5-6** | **Null-Checks** (empfohlen) |
| 7-9 | Sehr strikt |
