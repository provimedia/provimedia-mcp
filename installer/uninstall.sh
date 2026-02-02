#!/bin/bash
# =============================================================================
# CHAINGUARD - Uninstaller
# =============================================================================
# Entfernt Chainguard vollständig vom System.
#
# Verwendung:
#   ./uninstall.sh [--force] [--keep-data] [--keep-config]
#
# Optionen:
#   --force        Keine Bestätigung erforderlich
#   --keep-data    Projekt-Daten behalten
#   --keep-config  Konfiguration behalten
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
FORCE_MODE=false
KEEP_DATA=false
KEEP_CONFIG=false

# =============================================================================
# Hilfsfunktionen
# =============================================================================
info() {
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
# Deinstallation
# =============================================================================
remove_claude_code_config() {
    step "Entferne Claude Code Konfiguration"

    local settings_file="$HOME/.claude/settings.json"

    if [[ ! -f "$settings_file" ]]; then
        info "settings.json nicht gefunden, überspringe..."
        return 0
    fi

    # Backup erstellen
    local backup_file="$settings_file.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$settings_file" "$backup_file"
    info "Backup erstellt: $backup_file"

    if command -v jq &> /dev/null; then
        # MCP Server entfernen
        if jq -e '.mcpServers.chainguard' "$settings_file" > /dev/null 2>&1; then
            jq 'del(.mcpServers.chainguard)' "$settings_file" > "$settings_file.tmp"
            mv "$settings_file.tmp" "$settings_file"
            success "Chainguard MCP Server entfernt"
        else
            info "Chainguard MCP Server war nicht registriert"
        fi

        # Hooks entfernen die auf chainguard zeigen
        if jq -e '.hooks.PostToolUse' "$settings_file" > /dev/null 2>&1; then
            jq '.hooks.PostToolUse = [.hooks.PostToolUse[] | select(.command | contains("chainguard") | not)]' "$settings_file" > "$settings_file.tmp"
            mv "$settings_file.tmp" "$settings_file"
            success "Chainguard Hooks entfernt"
        fi

        # Leere mcpServers entfernen
        if jq -e '.mcpServers == {}' "$settings_file" > /dev/null 2>&1; then
            jq 'del(.mcpServers)' "$settings_file" > "$settings_file.tmp"
            mv "$settings_file.tmp" "$settings_file"
        fi

        # Leere hooks entfernen
        if jq -e '.hooks.PostToolUse == []' "$settings_file" > /dev/null 2>&1; then
            jq 'del(.hooks.PostToolUse)' "$settings_file" > "$settings_file.tmp"
            mv "$settings_file.tmp" "$settings_file"
        fi
        if jq -e '.hooks == {}' "$settings_file" > /dev/null 2>&1; then
            jq 'del(.hooks)' "$settings_file" > "$settings_file.tmp"
            mv "$settings_file.tmp" "$settings_file"
        fi

    else
        warn "jq nicht verfügbar. Bitte manuell aus settings.json entfernen:"
        echo "  - mcpServers.chainguard"
        echo "  - hooks mit 'chainguard' im Pfad"
    fi
}

remove_installation() {
    step "Entferne Chainguard Installation"

    if [[ ! -d "$CHAINGUARD_HOME" ]]; then
        info "Chainguard ist nicht installiert (Verzeichnis existiert nicht)"
        return 0
    fi

    # Statistiken sammeln
    local total_files=$(find "$CHAINGUARD_HOME" -type f 2>/dev/null | wc -l | tr -d ' ')
    local total_size=$(du -sh "$CHAINGUARD_HOME" 2>/dev/null | cut -f1)
    local project_count=$(ls -d "$CHAINGUARD_HOME/projects/"*/ 2>/dev/null | wc -l | tr -d ' ')

    info "Zu löschende Dateien: $total_files"
    info "Größe: $total_size"
    info "Projekte: $project_count"

    if [[ "$KEEP_DATA" == "true" ]]; then
        info "Behalte Projekt-Daten (--keep-data)"
        # Lösche alles außer projects/
        find "$CHAINGUARD_HOME" -mindepth 1 -maxdepth 1 ! -name "projects" -exec rm -rf {} \;
        success "Installation entfernt (Daten behalten)"
    elif [[ "$KEEP_CONFIG" == "true" ]]; then
        info "Behalte Konfiguration (--keep-config)"
        # Lösche alles außer config/
        find "$CHAINGUARD_HOME" -mindepth 1 -maxdepth 1 ! -name "config" -exec rm -rf {} \;
        success "Installation entfernt (Konfiguration behalten)"
    else
        # Alles löschen
        rm -rf "$CHAINGUARD_HOME"
        success "Chainguard vollständig entfernt"
    fi
}

cleanup_venv() {
    step "Python venv"

    local VENV_DIR="$CHAINGUARD_HOME/venv"

    if [[ -d "$VENV_DIR" ]]; then
        local venv_size=$(du -sh "$VENV_DIR" 2>/dev/null | cut -f1)
        info "Python venv gefunden: $VENV_DIR ($venv_size)"
        info "Das venv wird zusammen mit dem Chainguard-Verzeichnis entfernt."
        success "Keine separaten pip-Pakete zu deinstallieren (alles im venv)"
    else
        info "Kein Python venv gefunden"
    fi
}

# =============================================================================
# Zusammenfassung
# =============================================================================
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ${BOLD}DEINSTALLATION ABGESCHLOSSEN${NC}${GREEN}                          ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    echo "Chainguard wurde vom System entfernt."
    echo ""

    if [[ "$KEEP_DATA" == "true" ]]; then
        echo -e "${YELLOW}Hinweis:${NC} Projekt-Daten wurden behalten in:"
        echo "  $CHAINGUARD_HOME/projects/"
        echo ""
    fi

    if [[ "$KEEP_CONFIG" == "true" ]]; then
        echo -e "${YELLOW}Hinweis:${NC} Konfiguration wurde behalten in:"
        echo "  $CHAINGUARD_HOME/config/"
        echo ""
    fi

    echo "Zur Neuinstallation:"
    echo "  ./installer/install.sh"
    echo ""
}

# =============================================================================
# Hilfe
# =============================================================================
show_help() {
    echo "CHAINGUARD UNINSTALLER"
    echo ""
    echo "Verwendung: $0 [OPTIONEN]"
    echo ""
    echo "Optionen:"
    echo "  --force        Keine Bestätigung erforderlich"
    echo "  --keep-data    Projekt-Daten behalten (~/.chainguard/projects/)"
    echo "  --keep-config  Konfiguration behalten (~/.chainguard/config/)"
    echo "  --help         Diese Hilfe anzeigen"
    echo ""
    echo "Umgebungsvariablen:"
    echo "  CHAINGUARD_HOME  Installationsverzeichnis (Standard: ~/.chainguard)"
}

# =============================================================================
# Hauptprogramm
# =============================================================================
main() {
    # Argumente parsen
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                FORCE_MODE=true
                shift
                ;;
            --keep-data)
                KEEP_DATA=true
                shift
                ;;
            --keep-config)
                KEEP_CONFIG=true
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

    # Banner
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║              ${BOLD}CHAINGUARD UNINSTALLER${NC}${RED}                                 ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Prüfen ob installiert
    if [[ ! -d "$CHAINGUARD_HOME" ]]; then
        info "Chainguard ist nicht installiert (Verzeichnis existiert nicht: $CHAINGUARD_HOME)"
        echo ""
        echo "Falls Claude Code Konfiguration bereinigt werden soll:"
        echo "  Bearbeite ~/.claude/settings.json manuell"
        exit 0
    fi

    # Statistiken anzeigen
    local total_files=$(find "$CHAINGUARD_HOME" -type f 2>/dev/null | wc -l | tr -d ' ')
    local total_size=$(du -sh "$CHAINGUARD_HOME" 2>/dev/null | cut -f1)
    local project_count=$(ls -d "$CHAINGUARD_HOME/projects/"*/ 2>/dev/null | wc -l | tr -d ' ')

    echo "Folgendes wird entfernt:"
    echo ""
    echo -e "  ${BOLD}Verzeichnis:${NC} $CHAINGUARD_HOME"
    echo -e "  ${BOLD}Dateien:${NC}     $total_files"
    echo -e "  ${BOLD}Größe:${NC}       $total_size"
    echo -e "  ${BOLD}Projekte:${NC}    $project_count"
    echo ""

    # Bestätigung
    if [[ "$FORCE_MODE" != "true" ]]; then
        echo -e "${YELLOW}WARNUNG: Dies kann nicht rückgängig gemacht werden!${NC}"
        echo ""
        read -p "Fortfahren mit Deinstallation? [y/N] " -n 1 -r
        echo

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "Abgebrochen."
            exit 0
        fi
    fi

    # Deinstallation durchführen
    remove_claude_code_config
    cleanup_venv
    remove_installation

    # Zusammenfassung
    print_summary
}

main "$@"
