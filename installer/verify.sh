#!/bin/bash
# =============================================================================
# CHAINGUARD - Verification Script
# =============================================================================
# Verifiziert eine bestehende Chainguard-Installation und prüft alle
# Komponenten auf Funktionalität.
#
# Verwendung:
#   ./verify.sh [--fix] [--verbose] [--json]
#
# Optionen:
#   --fix       Versucht Probleme automatisch zu beheben
#   --verbose   Ausführliche Ausgabe
#   --json      Ausgabe als JSON
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

# Flags
FIX_MODE=false
VERBOSE=false
JSON_OUTPUT=false

# Zähler
CHECKS_TOTAL=0
CHECKS_PASSED=0
CHECKS_WARNED=0
CHECKS_FAILED=0

# JSON Ergebnisse
declare -a JSON_RESULTS=()

# =============================================================================
# Hilfsfunktionen
# =============================================================================
check_pass() {
    ((CHECKS_TOTAL++))
    ((CHECKS_PASSED++))
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        JSON_RESULTS+=("{\"check\": \"$1\", \"status\": \"pass\", \"message\": \"$2\"}")
    else
        echo -e "${GREEN}[PASS]${NC} $1"
        [[ "$VERBOSE" == "true" ]] && [[ -n "$2" ]] && echo "       $2"
    fi
}

check_warn() {
    ((CHECKS_TOTAL++))
    ((CHECKS_WARNED++))
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        JSON_RESULTS+=("{\"check\": \"$1\", \"status\": \"warn\", \"message\": \"$2\"}")
    else
        echo -e "${YELLOW}[WARN]${NC} $1"
        [[ -n "$2" ]] && echo "       $2"
    fi
}

check_fail() {
    ((CHECKS_TOTAL++))
    ((CHECKS_FAILED++))
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        JSON_RESULTS+=("{\"check\": \"$1\", \"status\": \"fail\", \"message\": \"$2\"}")
    else
        echo -e "${RED}[FAIL]${NC} $1"
        [[ -n "$2" ]] && echo "       $2"
    fi
}

section() {
    if [[ "$JSON_OUTPUT" != "true" ]]; then
        echo ""
        echo -e "${CYAN}━━━ $1 ━━━${NC}"
    fi
}

# =============================================================================
# Verifizierungen
# =============================================================================
verify_installation_exists() {
    section "Installation"

    if [[ -d "$CHAINGUARD_HOME" ]]; then
        check_pass "Chainguard Verzeichnis existiert" "$CHAINGUARD_HOME"
    else
        check_fail "Chainguard Verzeichnis nicht gefunden" "Erwartet: $CHAINGUARD_HOME"
        return 1
    fi

    # Version prüfen
    if [[ -f "$CHAINGUARD_HOME/.version" ]]; then
        local version=$(cat "$CHAINGUARD_HOME/.version")
        check_pass "Version" "$version"
    else
        check_warn "Versionsdatei nicht gefunden" "Möglicherweise alte Installation"
    fi

    # Installationsdatum
    if [[ -f "$CHAINGUARD_HOME/.installed_at" ]]; then
        local installed=$(cat "$CHAINGUARD_HOME/.installed_at")
        check_pass "Installationsdatum" "$installed"
    fi
}

verify_required_files() {
    section "Erforderliche Dateien"

    local required_files=(
        "chainguard_mcp.py:MCP Server"
        "hooks/project-identifier.sh:Project Identifier"
        "hooks/scope-reminder.sh:Scope-Reminder Hook"
        "hooks/auto-track.sh:Auto-Track Hook"
        "hooks/observer-hook.sh:Observer Hook"
    )

    for file_spec in "${required_files[@]}"; do
        local file="${file_spec%%:*}"
        local name="${file_spec##*:}"

        if [[ -f "$CHAINGUARD_HOME/$file" ]]; then
            check_pass "$name" "$file"
        else
            check_fail "$name fehlt" "$file"
        fi
    done

    # Optionale Dateien
    local optional_files=(
        "deep-validator.py:Deep Validator"
        "requirements.txt:Requirements"
        "config/config.yaml:Konfiguration"
    )

    for file_spec in "${optional_files[@]}"; do
        local file="${file_spec%%:*}"
        local name="${file_spec##*:}"

        if [[ -f "$CHAINGUARD_HOME/$file" ]]; then
            check_pass "$name (optional)" "$file"
        else
            check_warn "$name nicht vorhanden (optional)" "$file"
        fi
    done
}

verify_permissions() {
    section "Berechtigungen"

    # Ausführbare Skripte
    local executables=(
        "chainguard_mcp.py"
        "hooks/project-identifier.sh"
        "hooks/auto-track.sh"
        "hooks/observer-hook.sh"
    )

    for file in "${executables[@]}"; do
        if [[ -f "$CHAINGUARD_HOME/$file" ]]; then
            if [[ -x "$CHAINGUARD_HOME/$file" ]]; then
                check_pass "$file ist ausführbar"
            else
                check_warn "$file ist nicht ausführbar"
                if [[ "$FIX_MODE" == "true" ]]; then
                    chmod +x "$CHAINGUARD_HOME/$file"
                    echo "       [FIXED] Berechtigung korrigiert"
                fi
            fi
        fi
    done

    # Verzeichnis-Schreibrechte
    local dirs=("projects" "logs" "config" "backup")
    for dir in "${dirs[@]}"; do
        if [[ -d "$CHAINGUARD_HOME/$dir" ]]; then
            if [[ -w "$CHAINGUARD_HOME/$dir" ]]; then
                check_pass "$dir/ ist beschreibbar"
            else
                check_fail "$dir/ ist nicht beschreibbar"
            fi
        else
            check_warn "$dir/ existiert nicht"
            if [[ "$FIX_MODE" == "true" ]]; then
                mkdir -p "$CHAINGUARD_HOME/$dir"
                echo "       [FIXED] Verzeichnis erstellt"
            fi
        fi
    done
}

verify_python() {
    section "Python Umgebung"

    local VENV_PYTHON="$CHAINGUARD_HOME/venv/bin/python"

    # venv prüfen
    if [[ -x "$VENV_PYTHON" ]]; then
        local py_version=$("$VENV_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
        check_pass "venv Python" "$py_version ($VENV_PYTHON)"
    else
        check_fail "venv Python nicht gefunden" "Erwartet: $VENV_PYTHON"
        # Fallback auf System-Python für restliche Checks
        if command -v python3 &> /dev/null; then
            VENV_PYTHON="python3"
            check_warn "Fallback auf System-Python"
        else
            check_fail "Python3 nicht gefunden"
            return 1
        fi
    fi

    # Erforderliche Module
    local required_modules=("mcp" "aiofiles" "yaml")
    for module in "${required_modules[@]}"; do
        if "$VENV_PYTHON" -c "import $module" 2>/dev/null; then
            local version=$("$VENV_PYTHON" -c "import $module; print(getattr($module, '__version__', 'unknown'))" 2>/dev/null || echo "installed")
            check_pass "Python-Modul: $module" "$version"
        else
            check_fail "Python-Modul: $module fehlt"
        fi
    done

    # Empfohlene Module
    if "$VENV_PYTHON" -c "import aiohttp" 2>/dev/null; then
        check_pass "Python-Modul: aiohttp (HTTP Testing)"
    else
        check_warn "Python-Modul: aiohttp nicht installiert (für HTTP Endpoint-Testing)"
    fi

    # Long-Term Memory Module (v6.9)
    if "$VENV_PYTHON" -c "from fastembed import TextEmbedding" 2>/dev/null; then
        check_pass "Python-Modul: fastembed (Embeddings)"
    else
        check_warn "Python-Modul: fastembed nicht installiert (für Long-Term Memory)"
    fi

    if "$VENV_PYTHON" -c "import numpy" 2>/dev/null; then
        check_pass "Python-Modul: numpy (Vector Operations)"
    else
        check_warn "Python-Modul: numpy nicht installiert (für Long-Term Memory)"
    fi

    # Optionale Module
    local optional_modules=("anthropic")
    for module in "${optional_modules[@]}"; do
        if "$VENV_PYTHON" -c "import $module" 2>/dev/null; then
            check_pass "Python-Modul: $module (optional)"
        else
            check_warn "Python-Modul: $module nicht installiert (optional)"
        fi
    done
}

verify_mcp_server() {
    section "MCP Server"

    local mcp_file="$CHAINGUARD_HOME/chainguard_mcp.py"

    if [[ ! -f "$mcp_file" ]]; then
        check_fail "MCP Server Datei nicht gefunden"
        return 1
    fi

    local VENV_PYTHON="$CHAINGUARD_HOME/venv/bin/python"
    local CHECK_PYTHON="${VENV_PYTHON}"
    if [[ ! -x "$VENV_PYTHON" ]]; then
        CHECK_PYTHON="python3"
    fi

    # Syntax-Check
    if "$CHECK_PYTHON" -m py_compile "$mcp_file" 2>/dev/null; then
        check_pass "Python-Syntax korrekt"
    else
        check_fail "Python-Syntax fehlerhaft"
        return 1
    fi

    # Import-Test
    if "$CHECK_PYTHON" -c "
import sys
sys.path.insert(0, '$CHAINGUARD_HOME')
try:
    from chainguard.config import VERSION
    print(f'Chainguard v{VERSION}')
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location('chainguard_mcp', '$mcp_file')
    module = importlib.util.module_from_spec(spec)
" 2>/dev/null; then
        check_pass "MCP Server ladbar"
    else
        check_fail "MCP Server kann nicht geladen werden"
    fi

    # Version im Code prüfen (modulares Package)
    local version_file="$CHAINGUARD_HOME/chainguard/config.py"
    if [[ -f "$version_file" ]]; then
        local code_version=$(grep -o 'VERSION = "[^"]*"' "$version_file" | grep -o '"[^"]*"' | tr -d '"')
        if [[ -n "$code_version" ]]; then
            check_pass "MCP Server Version" "$code_version"
        fi
    fi

    # Tool-Definitionen prüfen (im tools.py des Packages)
    local tools_file="$CHAINGUARD_HOME/chainguard/tools.py"
    if [[ -f "$tools_file" ]]; then
        local tool_count=$(grep -c "@server.tool" "$tools_file" 2>/dev/null || echo "0")
        if [[ "$tool_count" -gt 0 ]]; then
            check_pass "MCP Tools definiert" "$tool_count Tools"
        else
            check_warn "Keine MCP Tools gefunden"
        fi
    fi
}

verify_claude_code_config() {
    section "Claude Code Konfiguration"

    local settings_file="$HOME/.claude/settings.json"

    if [[ ! -f "$settings_file" ]]; then
        check_warn "Claude Code settings.json nicht gefunden" "$settings_file"
        return 0
    fi

    check_pass "settings.json existiert"

    # Prüfe ob jq verfügbar
    if command -v jq &> /dev/null; then
        # MCP Server registriert?
        if jq -e '.mcpServers.chainguard' "$settings_file" > /dev/null 2>&1; then
            check_pass "Chainguard MCP Server registriert"

            # Korrekter Pfad?
            local configured_path=$(jq -r '.mcpServers.chainguard.args[0]' "$settings_file" 2>/dev/null)
            if [[ "$configured_path" == "$CHAINGUARD_HOME/chainguard_mcp.py" ]]; then
                check_pass "MCP Server Pfad korrekt" "$configured_path"
            else
                check_warn "MCP Server Pfad weicht ab" "Konfiguriert: $configured_path, Erwartet: $CHAINGUARD_HOME/chainguard_mcp.py"
            fi

            # Python Command?
            local configured_cmd=$(jq -r '.mcpServers.chainguard.command' "$settings_file" 2>/dev/null)
            if [[ "$configured_cmd" == *"/.chainguard/venv/bin/python"* ]]; then
                check_pass "Python-Befehl korrekt (venv)" "$configured_cmd"
            elif [[ "$configured_cmd" == "python3" ]] || [[ "$configured_cmd" == "python" ]]; then
                check_warn "System-Python statt venv" "Empfohlen: $CHAINGUARD_HOME/venv/bin/python"
                if [[ "$FIX_MODE" == "true" ]]; then
                    jq --arg cmd "$CHAINGUARD_HOME/venv/bin/python" '.mcpServers.chainguard.command = $cmd' "$settings_file" > "$settings_file.tmp" && mv "$settings_file.tmp" "$settings_file"
                    echo "       [FIXED] Auf venv-Python umgestellt"
                fi
            else
                check_warn "Python-Befehl ungewöhnlich" "$configured_cmd"
            fi
        else
            check_fail "Chainguard MCP Server NICHT registriert"
            if [[ "$FIX_MODE" == "true" ]]; then
                echo "       [FIXING] Registriere MCP Server..."
                jq --arg path "$CHAINGUARD_HOME/chainguard_mcp.py" '
                    .mcpServers = (.mcpServers // {}) |
                    .mcpServers.chainguard = {"command": "python3", "args": [$path]}
                ' "$settings_file" > "$settings_file.tmp" && mv "$settings_file.tmp" "$settings_file"
                echo "       [FIXED] MCP Server registriert"
            fi
        fi

        # Hooks konfiguriert?
        if jq -e '.hooks.PostToolUse' "$settings_file" > /dev/null 2>&1; then
            local hook_count=$(jq '.hooks.PostToolUse | length' "$settings_file" 2>/dev/null)
            check_pass "Hooks konfiguriert" "$hook_count Hook(s)"
        else
            check_warn "Keine Hooks konfiguriert (optional)"
        fi
    else
        # Fallback ohne jq
        if grep -q "chainguard" "$settings_file" 2>/dev/null; then
            check_pass "Chainguard vermutlich registriert (jq nicht verfügbar für Details)"
        else
            check_fail "Chainguard nicht in settings.json gefunden"
        fi
    fi
}

verify_project_identifier() {
    section "Project Identifier"

    local pi_script="$CHAINGUARD_HOME/hooks/project-identifier.sh"

    if [[ ! -f "$pi_script" ]]; then
        check_fail "project-identifier.sh nicht gefunden"
        return 1
    fi

    if [[ ! -x "$pi_script" ]]; then
        check_warn "project-identifier.sh nicht ausführbar"
        if [[ "$FIX_MODE" == "true" ]]; then
            chmod +x "$pi_script"
            echo "       [FIXED]"
        fi
    fi

    # Funktionstest
    if output=$("$pi_script" --identify 2>&1); then
        check_pass "Project Identifier funktioniert" "$output"
    else
        check_warn "Project Identifier Ausführung fehlgeschlagen" "$output"
    fi

    # JSON-Output Test
    if output=$("$pi_script" --json 2>&1); then
        if echo "$output" | head -1 | grep -q "project_id" 2>/dev/null; then
            check_pass "JSON-Output korrekt"
        else
            check_warn "JSON-Output möglicherweise fehlerhaft"
        fi
    fi
}

verify_templates() {
    section "Templates (v4.2)"

    local template_file="$CHAINGUARD_HOME/templates/CHAINGUARD.md.block"
    if [[ -f "$template_file" ]]; then
        check_pass "CHAINGUARD.md.block Template vorhanden"

        # Version prüfen
        local template_version=$(grep "CHAINGUARD-MANDATORY-START" "$template_file" 2>/dev/null | grep -o 'v[0-9.]*' | head -1)
        if [[ -n "$template_version" ]]; then
            check_pass "Template Version" "$template_version"
        else
            check_warn "Template Version nicht gefunden"
        fi
    else
        check_warn "CHAINGUARD.md.block Template nicht gefunden (v4.2 Feature)"
        if [[ "$FIX_MODE" == "true" ]]; then
            mkdir -p "$CHAINGUARD_HOME/templates"
            echo "       [INFO] Führe install.sh erneut aus um Template zu installieren"
        fi
    fi
}

verify_hooks() {
    section "Hooks"

    # Scope-Reminder Hook (UserPromptSubmit)
    local scope_reminder="$CHAINGUARD_HOME/hooks/scope-reminder.sh"
    if [[ -f "$scope_reminder" ]]; then
        if [[ -x "$scope_reminder" ]]; then
            check_pass "scope-reminder.sh vorhanden und ausführbar"

            # v2.0 Feature prüfen
            if grep -q "sync_claude_md" "$scope_reminder" 2>/dev/null; then
                check_pass "scope-reminder.sh hat Auto-Sync (v2.0)"
            else
                check_warn "scope-reminder.sh ist alte Version (kein Auto-Sync)"
            fi
        else
            check_warn "scope-reminder.sh nicht ausführbar"
            if [[ "$FIX_MODE" == "true" ]]; then
                chmod +x "$scope_reminder"
                echo "       [FIXED]"
            fi
        fi
    else
        check_fail "scope-reminder.sh nicht gefunden"
    fi

    # Auto-Track Hook (PostToolUse)
    local auto_track="$CHAINGUARD_HOME/hooks/auto-track.sh"
    if [[ -f "$auto_track" ]]; then
        if [[ -x "$auto_track" ]]; then
            check_pass "auto-track.sh vorhanden und ausführbar"
        else
            check_warn "auto-track.sh nicht ausführbar"
            if [[ "$FIX_MODE" == "true" ]]; then
                chmod +x "$auto_track"
                echo "       [FIXED]"
            fi
        fi
    else
        check_fail "auto-track.sh nicht gefunden"
    fi

    # Observer Hook (optional)
    local observer="$CHAINGUARD_HOME/hooks/observer-hook.sh"
    if [[ -f "$observer" ]]; then
        if [[ -x "$observer" ]]; then
            check_pass "observer-hook.sh vorhanden und ausführbar"
        else
            check_warn "observer-hook.sh nicht ausführbar"
        fi
    else
        check_warn "observer-hook.sh nicht gefunden (optional)"
    fi
}

verify_system_tools() {
    section "System-Tools"

    # Erforderliche Tools
    local tools=("python3" "bash")
    for tool in "${tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            check_pass "$tool verfügbar"
        else
            check_fail "$tool nicht gefunden"
        fi
    done

    # Empfohlene Tools
    local recommended=("jq" "git" "curl")
    for tool in "${recommended[@]}"; do
        if command -v "$tool" &> /dev/null; then
            check_pass "$tool verfügbar (empfohlen)"
        else
            check_warn "$tool nicht gefunden (empfohlen)"
        fi
    done
}

# =============================================================================
# Zusammenfassung
# =============================================================================
print_summary() {
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo "{"
        echo "  \"summary\": {"
        echo "    \"total\": $CHECKS_TOTAL,"
        echo "    \"passed\": $CHECKS_PASSED,"
        echo "    \"warned\": $CHECKS_WARNED,"
        echo "    \"failed\": $CHECKS_FAILED"
        echo "  },"
        echo "  \"checks\": ["
        local first=true
        for result in "${JSON_RESULTS[@]}"; do
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo ","
            fi
            echo -n "    $result"
        done
        echo ""
        echo "  ]"
        echo "}"
    else
        echo ""
        echo -e "${CYAN}━━━ Zusammenfassung ━━━${NC}"
        echo ""
        echo -e "  Gesamt:    $CHECKS_TOTAL Checks"
        echo -e "  ${GREEN}Bestanden:${NC} $CHECKS_PASSED"
        echo -e "  ${YELLOW}Warnungen:${NC} $CHECKS_WARNED"
        echo -e "  ${RED}Fehler:${NC}    $CHECKS_FAILED"
        echo ""

        if [[ $CHECKS_FAILED -eq 0 ]]; then
            if [[ $CHECKS_WARNED -eq 0 ]]; then
                echo -e "${GREEN}${BOLD}Installation vollständig und funktionsfähig!${NC}"
            else
                echo -e "${YELLOW}${BOLD}Installation funktionsfähig mit Warnungen.${NC}"
            fi
        else
            echo -e "${RED}${BOLD}Installation hat Fehler. Bitte beheben!${NC}"
            echo ""
            echo "Tipps:"
            echo "  - Führe './installer/install.sh' erneut aus"
            echo "  - Oder './installer/verify.sh --fix' zum automatischen Beheben"
        fi
        echo ""
    fi
}

# =============================================================================
# Hilfe
# =============================================================================
show_help() {
    echo "CHAINGUARD VERIFICATION v2.0"
    echo ""
    echo "Verwendung: $0 [OPTIONEN]"
    echo ""
    echo "Optionen:"
    echo "  --fix       Versucht Probleme automatisch zu beheben"
    echo "  --verbose   Ausführliche Ausgabe"
    echo "  --json      Ausgabe als JSON (für Scripts)"
    echo "  --help      Diese Hilfe anzeigen"
    echo ""
    echo "Exit-Codes:"
    echo "  0  Alle Checks bestanden"
    echo "  1  Fehler gefunden"
    echo "  2  Nur Warnungen"
}

# =============================================================================
# Hauptprogramm
# =============================================================================
main() {
    # Argumente parsen
    while [[ $# -gt 0 ]]; do
        case $1 in
            --fix)
                FIX_MODE=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                echo "Unbekannte Option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    if [[ "$JSON_OUTPUT" != "true" ]]; then
        echo ""
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              ${BOLD}CHAINGUARD VERIFICATION${NC}${GREEN}                               ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    fi

    # Verifizierungen durchführen
    verify_installation_exists || true
    verify_required_files
    verify_permissions
    verify_python
    verify_mcp_server
    verify_claude_code_config
    verify_templates
    verify_project_identifier
    verify_hooks
    verify_system_tools

    # Zusammenfassung
    print_summary

    # Exit-Code
    if [[ $CHECKS_FAILED -gt 0 ]]; then
        exit 1
    elif [[ $CHECKS_WARNED -gt 0 ]]; then
        exit 2
    else
        exit 0
    fi
}

main "$@"
