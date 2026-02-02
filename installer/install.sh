#!/bin/bash
# =============================================================================
# CHAINGUARD - Installer
# =============================================================================
# Installs Chainguard on a new machine.
#
# Copyright (c) 2026 Provimedia GmbH
# Licensed under the Polyform Noncommercial License 1.0.0
# See LICENSE file in the project root for full license information.
#
# Usage:
#   ./install.sh [--no-hooks] [--verify-only] [--uninstall]
#
# Options:
#   --no-hooks      Install without observer hooks
#   --verify-only   Only verify the installation
#   --uninstall     Uninstall
#   --update        Update to latest version
#   --help          Show this help
# =============================================================================

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Konfiguration
CHAINGUARD_HOME="${CHAINGUARD_HOME:-$HOME/.chainguard}"
CHAINGUARD_VERSION="6.9.0"
GITHUB_REPO=""  # Nur lokale Installation - kein Remote-Repo
GITHUB_BRANCH="main"
MIN_PYTHON_VERSION="3.9"

# Script Verzeichnis ermitteln (für lokale Installation)
if [[ -n "${BASH_SOURCE[0]}" ]] && [[ -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SOURCE_DIR="$SCRIPT_DIR/../src"
else
    SCRIPT_DIR=""
    SOURCE_DIR=""
fi

# Flags
INSTALL_HOOKS=true
VERIFY_ONLY=false
UNINSTALL=false
UPDATE_MODE=false
QUIET_MODE=false

# =============================================================================
# Hilfsfunktionen
# =============================================================================
print_banner() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          ${BOLD}CHAINGUARD INSTALLER v$CHAINGUARD_VERSION${NC}${GREEN}                          ║${NC}"
    echo -e "${GREEN}║      Automatische Qualitätskontrolle für Claude Code              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

info() {
    [[ "$QUIET_MODE" == "true" ]] && return
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

step() {
    echo ""
    echo -e "${CYAN}━━━ $1 ━━━${NC}"
}

# =============================================================================
# Voraussetzungen prüfen
# =============================================================================
check_prerequisites() {
    step "Prüfe Voraussetzungen"

    local errors=0

    # Betriebssystem erkennen
    OS="$(uname -s)"
    case "$OS" in
        Linux*)     OS_TYPE="linux";;
        Darwin*)    OS_TYPE="macos";;
        CYGWIN*|MINGW*|MSYS*) OS_TYPE="windows";;
        *)          OS_TYPE="unknown";;
    esac
    info "Betriebssystem: $OS_TYPE ($OS)"

    # Python 3.8+ prüfen
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        # Prüfen ob python = python3
        if python --version 2>&1 | grep -q "Python 3"; then
            PYTHON_CMD="python"
        else
            PYTHON_CMD=""
        fi
    else
        PYTHON_CMD=""
    fi

    if [[ -n "$PYTHON_CMD" ]]; then
        PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
        PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')

        if [[ "$PYTHON_MAJOR" -ge 3 ]] && [[ "$PYTHON_MINOR" -ge 9 ]]; then
            success "Python $PYTHON_VERSION gefunden ($PYTHON_CMD)"
        else
            error "Python 3.9+ erforderlich (gefunden: $PYTHON_VERSION)"
        fi
    else
        error "Python3 nicht gefunden. Bitte installieren:\n  macOS: brew install python3\n  Ubuntu/Debian: sudo apt install python3\n  Windows: https://python.org/downloads"
    fi

    # pip prüfen
    if command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
        success "pip3 gefunden"
    elif $PYTHON_CMD -m pip --version &> /dev/null; then
        PIP_CMD="$PYTHON_CMD -m pip"
        success "pip (via python -m pip) gefunden"
    else
        warn "pip nicht gefunden. Python-Abhängigkeiten müssen manuell installiert werden."
        PIP_CMD=""
    fi

    # jq prüfen (optional aber empfohlen)
    if command -v jq &> /dev/null; then
        JQ_AVAILABLE=true
        success "jq gefunden"
    else
        JQ_AVAILABLE=false
        warn "jq nicht gefunden. JSON-Konfiguration eingeschränkt."
        echo "  Install: brew install jq (macOS) / apt install jq (Linux)"
    fi

    # Git prüfen (optional)
    if command -v git &> /dev/null; then
        GIT_AVAILABLE=true
        success "git gefunden"
    else
        GIT_AVAILABLE=false
        warn "git nicht gefunden. Projekt-Identifikation eingeschränkt."
    fi

    # curl oder wget für Remote-Installation
    if command -v curl &> /dev/null; then
        DOWNLOAD_CMD="curl -sSL"
        success "curl gefunden"
    elif command -v wget &> /dev/null; then
        DOWNLOAD_CMD="wget -qO-"
        success "wget gefunden"
    else
        DOWNLOAD_CMD=""
        warn "Weder curl noch wget gefunden. Remote-Installation nicht möglich."
    fi

    # Prüfen ob Claude Code installiert ist
    CLAUDE_SETTINGS_DIR="$HOME/.claude"
    if [[ -d "$CLAUDE_SETTINGS_DIR" ]]; then
        success "Claude Code Verzeichnis gefunden"
    else
        warn "Claude Code Verzeichnis nicht gefunden (~/.claude)"
        echo "  Claude Code wird bei der ersten Nutzung automatisch erstellt."
    fi

    return $errors
}

# =============================================================================
# Installation der Dateien
# =============================================================================
install_files() {
    step "Installiere Chainguard nach $CHAINGUARD_HOME"

    # Verzeichnisstruktur erstellen
    info "Erstelle Verzeichnisstruktur..."
    mkdir -p "$CHAINGUARD_HOME"/{hooks,projects,config,logs,backup,templates}

    # Prüfen ob lokale oder Remote-Installation
    if [[ -d "$SOURCE_DIR/mcp-server" ]]; then
        install_from_local
    elif [[ -n "$DOWNLOAD_CMD" ]]; then
        install_from_remote
    else
        error "Weder lokale Quellen noch Download-Möglichkeit verfügbar."
    fi

    # Berechtigungen setzen
    info "Setze Berechtigungen..."
    chmod +x "$CHAINGUARD_HOME/hooks/"*.sh 2>/dev/null || true
    chmod +x "$CHAINGUARD_HOME/"*.py 2>/dev/null || true
    chmod +x "$CHAINGUARD_HOME/"*.sh 2>/dev/null || true

    # Versionsinfo speichern
    echo "$CHAINGUARD_VERSION" > "$CHAINGUARD_HOME/.version"
    date -Iseconds > "$CHAINGUARD_HOME/.installed_at"

    success "Dateien installiert"
}

install_from_local() {
    info "Installiere aus lokalem Verzeichnis: $SOURCE_DIR"

    # v4.7: Modulares Package kopieren
    if [[ -d "$SOURCE_DIR/mcp-server/chainguard" ]]; then
        info "Installiere modulares Package (v4.7+)..."
        rm -rf "$CHAINGUARD_HOME/chainguard" 2>/dev/null || true
        cp -r "$SOURCE_DIR/mcp-server/chainguard" "$CHAINGUARD_HOME/chainguard"
        info "  ✓ chainguard/ Package kopiert"

        # Wrapper erstellen
        cat > "$CHAINGUARD_HOME/chainguard_mcp.py" << 'WRAPPER_EOF'
#!/usr/bin/env python3
"""
CHAINGUARD MCP Server - Wrapper

This file wraps the modular chainguard package.
The actual implementation is in the chainguard/ subdirectory.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from chainguard.server import run

if __name__ == "__main__":
    run()
WRAPPER_EOF
        info "  ✓ chainguard_mcp.py Wrapper erstellt"
    elif [[ -f "$SOURCE_DIR/mcp-server/chainguard_mcp.py" ]]; then
        # Fallback: Alte monolithische Version
        info "Installiere monolithische Version (Legacy)..."
        cp "$SOURCE_DIR/mcp-server/chainguard_mcp.py" "$CHAINGUARD_HOME/chainguard_mcp.py"
        info "  ✓ chainguard_mcp.py kopiert"
    else
        error "Weder modulares Package noch chainguard_mcp.py gefunden!"
    fi

    # Weitere Dateien kopieren
    local files_to_copy=(
        "mcp-server/requirements.txt:requirements.txt"
        "deep-validator.py:deep-validator.py"
        "hooks/project-identifier.sh:hooks/project-identifier.sh"
        "hooks/observer-hook.sh:hooks/observer-hook.sh"
        "hooks/auto-track.sh:hooks/auto-track.sh"
        "hooks/scope-reminder.sh:hooks/scope-reminder.sh"
        "hooks/chainguard_enforcer.py:hooks/chainguard_enforcer.py"
        "hooks/chainguard_memory_inject.py:hooks/chainguard_memory_inject.py"
        "hooks/chainguard_scope_reminder.py:hooks/chainguard_scope_reminder.py"
        "templates/CHAINGUARD.md.block:templates/CHAINGUARD.md.block"
    )

    local copied=0
    local failed=0

    for file_spec in "${files_to_copy[@]}"; do
        local src="${file_spec%%:*}"
        local dst="${file_spec##*:}"

        if [[ -f "$SOURCE_DIR/$src" ]]; then
            cp "$SOURCE_DIR/$src" "$CHAINGUARD_HOME/$dst"
            ((copied++))
            info "  ✓ $dst"
        else
            warn "  ✗ $src nicht gefunden"
            ((failed++))
        fi
    done

    # Templates kopieren (optional)
    if [[ -d "$SCRIPT_DIR/../templates" ]]; then
        mkdir -p "$CHAINGUARD_HOME/templates"
        cp -r "$SCRIPT_DIR/../templates/"* "$CHAINGUARD_HOME/templates/" 2>/dev/null || true
        info "  ✓ Templates kopiert"
    fi

    # Docs kopieren (optional)
    if [[ -d "$SCRIPT_DIR/../docs" ]]; then
        mkdir -p "$CHAINGUARD_HOME/docs"
        cp -r "$SCRIPT_DIR/../docs/"* "$CHAINGUARD_HOME/docs/" 2>/dev/null || true
        info "  ✓ Dokumentation kopiert"
    fi

    success "$((copied + 1)) Dateien/Packages kopiert, $failed fehlgeschlagen"
}

install_from_remote() {
    info "Installiere von GitHub: $GITHUB_REPO (Branch: $GITHUB_BRANCH)"

    local BASE_URL="https://raw.githubusercontent.com/$GITHUB_REPO/$GITHUB_BRANCH"

    # Liste der Remote-Dateien
    local remote_files=(
        "src/mcp-server/chainguard_mcp.py:chainguard_mcp.py"
        "src/mcp-server/requirements.txt:requirements.txt"
        "src/deep-validator.py:deep-validator.py"
        "src/hooks/project-identifier.sh:hooks/project-identifier.sh"
        "src/hooks/observer-hook.sh:hooks/observer-hook.sh"
        "src/hooks/auto-track.sh:hooks/auto-track.sh"
        "src/hooks/scope-reminder.sh:hooks/scope-reminder.sh"
        "src/templates/CHAINGUARD.md.block:templates/CHAINGUARD.md.block"
    )

    local downloaded=0
    local failed=0

    for file_spec in "${remote_files[@]}"; do
        local src="${file_spec%%:*}"
        local dst="${file_spec##*:}"

        info "  Lade $src..."
        if $DOWNLOAD_CMD "$BASE_URL/$src" > "$CHAINGUARD_HOME/$dst" 2>/dev/null; then
            # Prüfen ob Download erfolgreich (nicht leer und kein 404)
            if [[ -s "$CHAINGUARD_HOME/$dst" ]] && ! grep -q "404: Not Found" "$CHAINGUARD_HOME/$dst" 2>/dev/null; then
                ((downloaded++))
                info "  ✓ $dst"
            else
                rm -f "$CHAINGUARD_HOME/$dst"
                ((failed++))
                warn "  ✗ $dst (nicht gefunden oder leer)"
            fi
        else
            ((failed++))
            warn "  ✗ $dst (Download fehlgeschlagen)"
        fi
    done

    if [[ $downloaded -eq 0 ]]; then
        error "Keine Dateien konnten heruntergeladen werden. Prüfe die Repository-URL."
    fi

    success "$downloaded Dateien heruntergeladen, $failed fehlgeschlagen"
}

# =============================================================================
# Python venv erstellen und Dependencies installieren
# =============================================================================
install_python_deps() {
    step "Erstelle Python Virtual Environment und installiere Abhängigkeiten"

    VENV_DIR="$CHAINGUARD_HOME/venv"
    VENV_PIP="$VENV_DIR/bin/pip"
    VENV_PYTHON="$VENV_DIR/bin/python"

    # venv erstellen oder aktualisieren
    if [[ -d "$VENV_DIR" ]]; then
        info "Bestehendes venv gefunden, aktualisiere..."
    else
        info "Erstelle neues venv in $VENV_DIR..."
        if ! $PYTHON_CMD -m venv "$VENV_DIR" 2>/dev/null; then
            error "Konnte venv nicht erstellen. Bitte python3-venv installieren:\n  macOS: brew install python3\n  Ubuntu/Debian: sudo apt install python3-venv"
        fi
        success "venv erstellt: $VENV_DIR"
    fi

    # pip im venv aktualisieren
    "$VENV_PIP" install --upgrade pip --quiet 2>/dev/null || true

    # Erforderliche Packages
    local required_packages=(
        "mcp>=0.9.0"
        "aiofiles>=23.0.0"
        "aiohttp>=3.8.0"
        "aiomysql>=0.2.0"
        "pyyaml>=6.0"
    )

    # Long-Term Memory Packages (v6.9: lightweight backend)
    local memory_packages=(
        "fastembed>=0.3.0"
        "numpy>=1.24.0"
    )

    # Optionale Packages
    local optional_packages=(
        "anthropic"
    )

    info "Installiere erforderliche Packages ins venv..."
    for pkg in "${required_packages[@]}"; do
        if "$VENV_PIP" install "$pkg" --quiet 2>/dev/null; then
            success "  $pkg"
        else
            error "Konnte $pkg nicht installieren."
        fi
    done

    info "Installiere Long-Term Memory Packages..."
    for pkg in "${memory_packages[@]}"; do
        if "$VENV_PIP" install "$pkg" --quiet 2>/dev/null; then
            success "  $pkg"
        else
            warn "  $pkg konnte nicht installiert werden (Long-Term Memory deaktiviert)"
        fi
    done

    info "Installiere optionale Packages..."
    for pkg in "${optional_packages[@]}"; do
        if "$VENV_PIP" install "$pkg" --quiet 2>/dev/null; then
            success "  $pkg"
        else
            warn "  $pkg konnte nicht installiert werden (optional)"
        fi
    done

    success "Python-Abhängigkeiten im venv installiert"
}

# =============================================================================
# Verifiziere Python-Module im venv
# =============================================================================
verify_python_modules() {
    info "Verifiziere Python-Module im venv..."

    VENV_PYTHON="$CHAINGUARD_HOME/venv/bin/python"

    if [[ ! -x "$VENV_PYTHON" ]]; then
        warn "venv Python nicht gefunden: $VENV_PYTHON"
        return 1
    fi

    local modules_ok=true

    # Erforderliche Module
    if "$VENV_PYTHON" -c "import mcp" 2>/dev/null; then
        success "  mcp Modul verfügbar"
    else
        warn "  mcp Modul NICHT verfügbar"
        modules_ok=false
    fi

    if "$VENV_PYTHON" -c "import aiofiles" 2>/dev/null; then
        success "  aiofiles Modul verfügbar (async I/O)"
    else
        warn "  aiofiles Modul nicht verfügbar"
        modules_ok=false
    fi

    if "$VENV_PYTHON" -c "import aiohttp" 2>/dev/null; then
        success "  aiohttp Modul verfügbar (HTTP Testing)"
    else
        warn "  aiohttp Modul nicht verfügbar (für HTTP Endpoint-Testing)"
    fi

    if "$VENV_PYTHON" -c "import aiomysql" 2>/dev/null; then
        success "  aiomysql Modul verfügbar (DB Inspector)"
    else
        warn "  aiomysql Modul nicht verfügbar (für Database Inspector)"
    fi

    # Long-Term Memory (v6.9: fastembed + numpy)
    if "$VENV_PYTHON" -c "from fastembed import TextEmbedding" 2>/dev/null; then
        success "  fastembed Modul verfügbar (Embeddings)"
    else
        warn "  fastembed Modul nicht verfügbar (für Long-Term Memory)"
    fi

    if "$VENV_PYTHON" -c "import numpy" 2>/dev/null; then
        success "  numpy Modul verfügbar (Vector Operations)"
    else
        warn "  numpy Modul nicht verfügbar (für Long-Term Memory)"
    fi

    if "$VENV_PYTHON" -c "import yaml" 2>/dev/null; then
        success "  yaml Modul verfügbar"
    else
        warn "  yaml Modul nicht verfügbar (optional)"
    fi

    if "$VENV_PYTHON" -c "import anthropic" 2>/dev/null; then
        success "  anthropic Modul verfügbar"
    else
        warn "  anthropic Modul nicht verfügbar (optional, für deep-validator)"
    fi

    if [[ "$modules_ok" == "false" ]]; then
        return 1
    fi
    return 0
}

# =============================================================================
# Prüfe PHP-Tools (PHPStan für statische Analyse)
# =============================================================================
check_php_tools() {
    step "Prüfe PHP-Tools"

    # PHPStan prüfen
    if command -v phpstan &> /dev/null; then
        local phpstan_version=$(phpstan --version 2>/dev/null | head -1)
        success "PHPStan gefunden: $phpstan_version"
        echo "    PHPStan ist aktiviert für statische PHP-Analyse (Level 5)"
    elif [[ -f "vendor/bin/phpstan" ]]; then
        success "PHPStan gefunden: vendor/bin/phpstan"
    else
        warn "PHPStan nicht gefunden (optional, für erweiterte PHP-Analyse)"
        echo ""
        echo "  PHPStan erkennt Laufzeitfehler VOR der Ausführung:"
        echo "    - Null-Zugriffe (\$user['id'] auf null)"
        echo "    - Typ-Fehler (string statt int)"
        echo "    - Undefinierte Methoden"
        echo ""
        echo "  Installation:"
        echo "    Global:  composer global require phpstan/phpstan"
        echo "    Projekt: composer require --dev phpstan/phpstan"
        echo ""
        echo "  Nach Installation ist PHPStan automatisch aktiv in Chainguard."
    fi
}

# =============================================================================
# Claude Code Konfiguration
# =============================================================================
configure_claude_code() {
    step "Konfiguriere Claude Code"

    CLAUDE_SETTINGS_DIR="$HOME/.claude"
    CLAUDE_SETTINGS_FILE="$CLAUDE_SETTINGS_DIR/settings.json"

    mkdir -p "$CLAUDE_SETTINGS_DIR"

    # MCP Server Pfad (~ expandieren für JSON)
    MCP_SERVER_PATH="$CHAINGUARD_HOME/chainguard_mcp.py"

    if [[ -f "$CLAUDE_SETTINGS_FILE" ]]; then
        # Backup erstellen
        local backup_file="$CHAINGUARD_HOME/backup/settings.json.$(date +%Y%m%d_%H%M%S)"
        cp "$CLAUDE_SETTINGS_FILE" "$backup_file"
        info "Backup erstellt: $backup_file"

        if [[ "$JQ_AVAILABLE" == "true" ]]; then
            configure_claude_with_jq
        else
            configure_claude_manual
        fi
    else
        # Neue Konfiguration erstellen
        create_new_claude_config
    fi
}

configure_claude_with_jq() {
    info "Aktualisiere Claude Code Konfiguration mit jq..."

    local VENV_PYTHON_PATH="$CHAINGUARD_HOME/venv/bin/python"

    # Prüfen ob mcpServers existiert und chainguard hinzufügen/aktualisieren
    jq --arg cmd "$VENV_PYTHON_PATH" --arg path "$MCP_SERVER_PATH" '
        .mcpServers = (.mcpServers // {}) |
        .mcpServers.chainguard = {
            "command": $cmd,
            "args": [$path]
        }
    ' "$CLAUDE_SETTINGS_FILE" > "$CLAUDE_SETTINGS_FILE.tmp"

    if [[ -s "$CLAUDE_SETTINGS_FILE.tmp" ]]; then
        mv "$CLAUDE_SETTINGS_FILE.tmp" "$CLAUDE_SETTINGS_FILE"
        success "MCP Server konfiguriert (venv Python: $VENV_PYTHON_PATH)"
    else
        rm -f "$CLAUDE_SETTINGS_FILE.tmp"
        error "Fehler beim Aktualisieren der Konfiguration"
    fi
}

configure_claude_manual() {
    local VENV_PYTHON_PATH="$CHAINGUARD_HOME/venv/bin/python"

    warn "jq nicht verfügbar. Manuelle Konfiguration erforderlich."
    echo ""
    echo "Füge folgendes zu $CLAUDE_SETTINGS_FILE hinzu:"
    echo ""
    cat << EOF
{
  "mcpServers": {
    "chainguard": {
      "command": "$VENV_PYTHON_PATH",
      "args": ["$MCP_SERVER_PATH"]
    }
  }
}
EOF
    echo ""
    read -p "Drücke Enter wenn fertig..." -r
}

create_new_claude_config() {
    info "Erstelle neue Claude Code Konfiguration..."

    local VENV_PYTHON_PATH="$CHAINGUARD_HOME/venv/bin/python"

    cat > "$CLAUDE_SETTINGS_FILE" << EOF
{
  "mcpServers": {
    "chainguard": {
      "command": "$VENV_PYTHON_PATH",
      "args": ["$MCP_SERVER_PATH"]
    }
  }
}
EOF
    success "Neue Konfiguration erstellt: $CLAUDE_SETTINGS_FILE"
}

# =============================================================================
# Hook-Konfiguration (Optional)
# =============================================================================
configure_hooks() {
    if [[ "$INSTALL_HOOKS" != "true" ]]; then
        info "Hook-Installation übersprungen (--no-hooks)"
        return 0
    fi

    step "Konfiguriere Hooks"

    local VENV_PYTHON_PATH="$CHAINGUARD_HOME/venv/bin/python"
    local SCOPE_HOOK="$CHAINGUARD_HOME/hooks/scope-reminder.sh"
    local TRACK_HOOK="$CHAINGUARD_HOME/hooks/auto-track.sh"
    local ENFORCER_HOOK="$VENV_PYTHON_PATH $CHAINGUARD_HOME/hooks/chainguard_enforcer.py"
    local MEMORY_HOOK="$VENV_PYTHON_PATH $CHAINGUARD_HOME/hooks/chainguard_memory_inject.py"
    local SCOPE_REMINDER_HOOK="$VENV_PYTHON_PATH $CHAINGUARD_HOME/hooks/chainguard_scope_reminder.py"

    if [[ "$JQ_AVAILABLE" != "true" ]]; then
        warn "jq nicht verfügbar. Hooks müssen manuell konfiguriert werden."
        echo ""
        echo "Füge zu $CLAUDE_SETTINGS_FILE hinzu:"
        cat << EOF
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "$SCOPE_HOOK"},
          {"type": "command", "command": "$MEMORY_HOOK"},
          {"type": "command", "command": "$SCOPE_REMINDER_HOOK"}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": "$ENFORCER_HOOK"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": "$TRACK_HOOK"}]
      }
    ]
  }
EOF
        return 0
    fi

    # Alle Hooks hinzufügen: UserPromptSubmit + PreToolUse + PostToolUse
    jq --arg scope_hook "$SCOPE_HOOK" --arg track_hook "$TRACK_HOOK" --arg enforcer_hook "$ENFORCER_HOOK" --arg memory_hook "$MEMORY_HOOK" --arg scope_reminder_hook "$SCOPE_REMINDER_HOOK" '
        .hooks = (.hooks // {}) |
        # UserPromptSubmit Hook für Scope-Reminder (legacy) + Memory Injection + Scope Reminder (Python)
        .hooks.UserPromptSubmit = [
            {
                "matcher": "",
                "hooks": [
                    {"type": "command", "command": $scope_hook},
                    {"type": "command", "command": $memory_hook},
                    {"type": "command", "command": $scope_reminder_hook}
                ]
            }
        ] |
        # PreToolUse Hook für HARD ENFORCEMENT (v4.17)
        .hooks.PreToolUse = [
            {
                "matcher": "Edit|Write",
                "hooks": [{"type": "command", "command": $enforcer_hook}]
            }
        ] |
        # PostToolUse Hook für Auto-Track
        .hooks.PostToolUse = [
            {
                "matcher": "Edit|Write",
                "hooks": [{"type": "command", "command": $track_hook}]
            }
        ]
    ' "$CLAUDE_SETTINGS_FILE" > "$CLAUDE_SETTINGS_FILE.tmp"

    if [[ -s "$CLAUDE_SETTINGS_FILE.tmp" ]]; then
        mv "$CLAUDE_SETTINGS_FILE.tmp" "$CLAUDE_SETTINGS_FILE"
        success "Scope-Reminder Hook (legacy) konfiguriert (UserPromptSubmit)"
        success "Memory-Inject Hook konfiguriert (UserPromptSubmit) - PRE-INJECTION!"
        success "Scope-Reminder Hook (Python v6.1) konfiguriert (UserPromptSubmit)"
        success "Enforcer Hook konfiguriert (PreToolUse) - HARD BLOCKING!"
        success "Auto-Track Hook konfiguriert (PostToolUse)"
    else
        rm -f "$CLAUDE_SETTINGS_FILE.tmp"
        warn "Hook-Konfiguration fehlgeschlagen"
    fi
}

# =============================================================================
# Globale Konfiguration
# =============================================================================
create_global_config() {
    step "Erstelle globale Konfiguration"

    local config_file="$CHAINGUARD_HOME/config/config.yaml"

    # Nur erstellen wenn nicht existiert
    if [[ -f "$config_file" ]] && [[ "$UPDATE_MODE" != "true" ]]; then
        info "Konfiguration existiert bereits, überspringe..."
        return 0
    fi

    cat > "$config_file" << EOF
# Chainguard Konfiguration v$CHAINGUARD_VERSION
# Erstellt: $(date -Iseconds)

version: "$CHAINGUARD_VERSION"

# LLM Validierung
llm:
  enabled: true
  # API Key wird aus ANTHROPIC_API_KEY Umgebungsvariable gelesen
  model: "claude-sonnet-4-20250514"
  max_tokens: 1024

# Validierungs-Einstellungen
validation:
  # Bei wie vielen Dateiänderungen eine Warnung ausgeben?
  file_change_threshold: 15
  # Nach wie vielen Bash-Commands ohne Tests warnen?
  bash_without_tests_threshold: 20
  # Automatische finale Validierung bei Session-Ende?
  auto_final_validation: false

# Observer Einstellungen
observer:
  # Welche Tools beobachten?
  tracked_tools:
    - Edit
    - Write
    - TodoWrite
    - Bash
  # Log-Retention (Tage)
  log_retention_days: 30

# Projekt-Erkennung
project_detection:
  # Priorität: git-remote > git-root > working-dir
  prefer_git: true

# Installation
installation:
  home: "$CHAINGUARD_HOME"
  installed_at: "$(date -Iseconds)"
  os: "$OS_TYPE"
  python: "$PYTHON_VERSION"
EOF

    success "Konfiguration erstellt: $config_file"
}

# =============================================================================
# MCP Server Health Check
# =============================================================================
health_check() {
    step "Führe Health-Check durch"

    local all_ok=true

    # 1. Prüfe ob alle erforderlichen Dateien existieren
    info "Prüfe Dateien..."
    local required_files=(
        "$CHAINGUARD_HOME/chainguard_mcp.py"
        "$CHAINGUARD_HOME/hooks/project-identifier.sh"
        "$CHAINGUARD_HOME/hooks/auto-track.sh"
    )

    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            success "  ✓ $(basename "$file")"
        else
            warn "  ✗ $(basename "$file") FEHLT"
            all_ok=false
        fi
    done

    # 2. Prüfe venv
    info "Prüfe Python venv..."
    local VENV_PYTHON="$CHAINGUARD_HOME/venv/bin/python"
    if [[ -x "$VENV_PYTHON" ]]; then
        local venv_py_version=$("$VENV_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        success "  ✓ venv Python $venv_py_version"
    else
        warn "  ✗ venv Python nicht gefunden ($VENV_PYTHON)"
        all_ok=false
        VENV_PYTHON="$PYTHON_CMD"
    fi

    # 3. Prüfe ob MCP Server syntaktisch korrekt ist
    info "Prüfe MCP Server Syntax..."

    if [[ -d "$CHAINGUARD_HOME/chainguard" ]]; then
        info "  Modulares Package erkannt (v4.7+)"
        local syntax_ok=true
        for pyfile in "$CHAINGUARD_HOME/chainguard/"*.py; do
            if ! "$VENV_PYTHON" -m py_compile "$pyfile" 2>/dev/null; then
                warn "  ✗ $(basename $pyfile) Syntax fehlerhaft"
                syntax_ok=false
            fi
        done
        if [[ "$syntax_ok" == "true" ]]; then
            success "  ✓ Alle Module Syntax OK"
        else
            all_ok=false
        fi
    elif "$VENV_PYTHON" -m py_compile "$CHAINGUARD_HOME/chainguard_mcp.py" 2>/dev/null; then
        success "  ✓ Python-Syntax OK (Legacy)"
    else
        warn "  ✗ Python-Syntax fehlerhaft"
        all_ok=false
    fi

    # 4. Prüfe ob MCP Server importiert werden kann
    info "Prüfe MCP Server Import..."
    if "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$CHAINGUARD_HOME')
try:
    from chainguard.config import VERSION
    print(f'Chainguard v{VERSION}')
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location('chainguard_mcp', '$CHAINGUARD_HOME/chainguard_mcp.py')
    module = importlib.util.module_from_spec(spec)
" 2>/dev/null; then
        success "  ✓ MCP Server ladbar"
    else
        warn "  ✗ MCP Server kann nicht geladen werden"
        all_ok=false
    fi

    # 4. Prüfe Claude Code Konfiguration
    info "Prüfe Claude Code Konfiguration..."
    if [[ -f "$HOME/.claude/settings.json" ]]; then
        if [[ "$JQ_AVAILABLE" == "true" ]]; then
            if jq -e '.mcpServers.chainguard' "$HOME/.claude/settings.json" > /dev/null 2>&1; then
                success "  ✓ MCP Server in settings.json registriert"
            else
                warn "  ✗ MCP Server NICHT in settings.json"
                all_ok=false
            fi
        else
            if grep -q "chainguard" "$HOME/.claude/settings.json" 2>/dev/null; then
                success "  ✓ MCP Server vermutlich registriert"
            else
                warn "  ✗ MCP Server möglicherweise nicht registriert"
            fi
        fi
    else
        warn "  ✗ settings.json nicht gefunden"
        all_ok=false
    fi

    # 5. Prüfe Project Identifier
    info "Prüfe Project Identifier..."
    if [[ -x "$CHAINGUARD_HOME/hooks/project-identifier.sh" ]]; then
        if "$CHAINGUARD_HOME/hooks/project-identifier.sh" --identify > /dev/null 2>&1; then
            success "  ✓ Project Identifier funktioniert"
        else
            warn "  ✗ Project Identifier fehlerhaft"
        fi
    fi

    # Zusammenfassung
    echo ""
    if [[ "$all_ok" == "true" ]]; then
        success "Health-Check bestanden!"
        return 0
    else
        warn "Health-Check mit Warnungen abgeschlossen"
        return 1
    fi
}

# =============================================================================
# Zusammenfassung
# =============================================================================
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ${BOLD}INSTALLATION ABGESCHLOSSEN${NC}${GREEN}                            ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Installation:${NC}   $CHAINGUARD_HOME"
    echo -e "  ${BOLD}Version:${NC}        $CHAINGUARD_VERSION"
    echo -e "  ${BOLD}Python:${NC}         $PYTHON_VERSION"
    echo -e "  ${BOLD}OS:${NC}             $OS_TYPE"
    echo ""
    echo -e "${CYAN}Nächste Schritte:${NC}"
    echo "  1. Starte Claude Code neu (oder öffne ein neues Terminal)"
    echo "  2. Der Chainguard MCP Server startet automatisch"
    echo "  3. Nutze die Tools: chainguard_set_scope, chainguard_validate, etc."
    echo ""
    echo -e "${CYAN}Verfügbare Tools:${NC}"
    echo "  chainguard_set_scope    - Scope für Aufgabe definieren"
    echo "  chainguard_track        - Änderungen tracken (silent, debounced)"
    echo "  chainguard_status       - Ultra-kompakte Statuszeile"
    echo "  chainguard_context      - Voller Kontext (sparsam nutzen)"
    echo "  chainguard_validate     - Validierung speichern"
    echo "  chainguard_set_phase    - Phase setzen"
    echo ""
    echo -e "${CYAN}v6.3 Features (NEU):${NC}"
    echo "  • PHPStan Integration: Statische Analyse für PHP"
    echo "  • Erkennt Laufzeitfehler VOR der Ausführung"
    echo "  • Null-Zugriffe, Typ-Fehler, undefinierte Methoden"
    echo "  • Level 5 (empfohlen): Findet die meisten Bugs"
    echo ""
    echo -e "${CYAN}v6.9 Features (NEU):${NC}"
    echo "  • Python venv: Isolierte Installation, PEP 668 kompatibel"
    echo "  • Alle Dependencies in $CHAINGUARD_HOME/venv/"
    echo ""
    echo -e "${CYAN}v5.x/v6.x Features:${NC}"
    echo "  • Long-Term Memory: Semantische Suche im Projekt"
    echo "  • fastembed + numpy/sqlite3 (~267 MB statt ~3.8 GB, 100% offline)"
    echo "  • Task-Mode System (programming, content, devops, research)"
    echo ""
    echo -e "${CYAN}v4.x Features:${NC}"
    echo "  • HARD ENFORCEMENT via PreToolUse Hook"
    echo "  • Database Inspector (chainguard_db_schema)"
    echo "  • Error Memory System (chainguard_recall)"
    echo "  • Test Runner (chainguard_run_tests)"
    echo "  • HTTP Endpoint Testing"
    echo "  • Handler-Registry Pattern, Async I/O"
    echo ""
    echo -e "${CYAN}Performance:${NC}"
    echo "  • Async I/O (non-blocking)"
    echo "  • Write Debouncing (90% weniger Disk-I/O)"
    echo "  • LRU Cache (Memory-bounded)"
    echo ""

    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
        echo -e "${YELLOW}Hinweis:${NC} ANTHROPIC_API_KEY nicht gesetzt."
        echo "  Für LLM-basierte Validierung, füge zu ~/.zshrc oder ~/.bashrc hinzu:"
        echo "  export ANTHROPIC_API_KEY='dein-api-key'"
        echo ""
    fi

    echo -e "${CYAN}Hilfe & Dokumentation:${NC}"
    echo "  ./installer/install.sh --help     - Installer-Hilfe"
    echo "  ./installer/verify.sh             - Installation verifizieren"
    echo "  ./installer/uninstall.sh          - Deinstallieren"
    echo ""
}

# =============================================================================
# Uninstall
# =============================================================================
uninstall() {
    print_banner
    step "Deinstalliere Chainguard"

    if [[ ! -d "$CHAINGUARD_HOME" ]]; then
        info "Chainguard ist nicht installiert."
        exit 0
    fi

    echo ""
    warn "Dies wird Chainguard vollständig entfernen!"
    echo "  Verzeichnis: $CHAINGUARD_HOME"
    echo ""
    read -p "Fortfahren? [y/N] " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Abgebrochen."
        exit 0
    fi

    # MCP Server aus Claude Code entfernen
    if [[ "$JQ_AVAILABLE" == "true" ]] && [[ -f "$HOME/.claude/settings.json" ]]; then
        info "Entferne MCP Server aus Claude Code..."
        jq 'del(.mcpServers.chainguard)' "$HOME/.claude/settings.json" > "$HOME/.claude/settings.json.tmp"
        mv "$HOME/.claude/settings.json.tmp" "$HOME/.claude/settings.json"
        success "MCP Server entfernt"
    fi

    # Verzeichnis löschen
    info "Lösche $CHAINGUARD_HOME..."
    rm -rf "$CHAINGUARD_HOME"
    success "Chainguard deinstalliert"

    echo ""
    echo "Chainguard wurde vollständig entfernt."
    echo "Die Claude Code Konfiguration (~/.claude/settings.json) wurde aktualisiert."
}

# =============================================================================
# Hilfe
# =============================================================================
show_help() {
    echo "CHAINGUARD INSTALLER v$CHAINGUARD_VERSION"
    echo ""
    echo "Verwendung: $0 [OPTIONEN]"
    echo ""
    echo "Optionen:"
    echo "  --no-hooks      Installation ohne Observer-Hooks"
    echo "  --verify-only   Nur Verifizierung der Installation"
    echo "  --uninstall     Deinstallation"
    echo "  --update        Update auf neueste Version (behält Konfiguration)"
    echo "  --quiet         Reduzierte Ausgabe"
    echo "  --help          Diese Hilfe anzeigen"
    echo ""
    echo "Umgebungsvariablen:"
    echo "  CHAINGUARD_HOME    Installationsverzeichnis (Standard: ~/.chainguard)"
    echo "  ANTHROPIC_API_KEY  API-Key für LLM-Validierung (optional)"
    echo ""
    echo "Beispiele:"
    echo "  ./install.sh                    # Standard-Installation"
    echo "  ./install.sh --no-hooks         # Ohne Hooks"
    echo "  ./install.sh --verify-only      # Nur prüfen"
    echo "  CHAINGUARD_HOME=/opt/cg ./install.sh  # Custom Pfad"
}

# =============================================================================
# Hauptprogramm
# =============================================================================
main() {
    # Argumente parsen
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-hooks)
                INSTALL_HOOKS=false
                shift
                ;;
            --verify-only)
                VERIFY_ONLY=true
                shift
                ;;
            --uninstall)
                UNINSTALL=true
                shift
                ;;
            --update)
                UPDATE_MODE=true
                shift
                ;;
            --quiet)
                QUIET_MODE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                warn "Unbekannte Option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Uninstall?
    if [[ "$UNINSTALL" == "true" ]]; then
        uninstall
        exit 0
    fi

    # Banner
    print_banner

    # Voraussetzungen prüfen
    check_prerequisites

    # Nur Verify?
    if [[ "$VERIFY_ONLY" == "true" ]]; then
        health_check
        exit $?
    fi

    # Installation durchführen
    install_files
    install_python_deps
    verify_python_modules || warn "Einige Python-Module fehlen"
    check_php_tools
    configure_claude_code

    # Hooks konfigurieren (mit Benutzer-Bestätigung)
    if [[ "$INSTALL_HOOKS" == "true" ]] && [[ -t 0 ]]; then
        echo ""
        read -p "Möchtest du die Auto-Track Hooks aktivieren? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            configure_hooks
        else
            INSTALL_HOOKS=false
        fi
    elif [[ "$INSTALL_HOOKS" == "true" ]]; then
        configure_hooks
    fi

    create_global_config

    # Health Check
    health_check || true

    # Zusammenfassung
    print_summary
}

main "$@"
