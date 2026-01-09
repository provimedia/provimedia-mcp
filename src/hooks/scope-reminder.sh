#!/bin/bash
# =============================================================================
# CHAINGUARD Scope Reminder Hook v2.2 (Project ID fix)
# =============================================================================
# Wird bei UserPromptSubmit aufgerufen und:
# 1. Prüft/ergänzt CLAUDE.md mit Pflicht-Anweisungen (Auto-Sync)
# 2. Erinnert Claude an chainguard_set_scope wenn kein aktiver Scope existiert
# =============================================================================

CHAINGUARD_HOME="${CHAINGUARD_HOME:-$HOME/.chainguard}"
TEMPLATE_FILE="$CHAINGUARD_HOME/templates/CHAINGUARD.md.block"
MARKER_START="<!-- CHAINGUARD-MANDATORY-START"
MARKER_END="<!-- CHAINGUARD-MANDATORY-END -->"

# Hook-Input von Claude Code lesen
HOOK_INPUT=""
if [[ ! -t 0 ]]; then
    HOOK_INPUT=$(cat)
fi

# Working Directory aus Hook-Input oder PWD
WORK_DIR=$(echo "$HOOK_INPUT" | jq -r '.cwd // ""' 2>/dev/null)
if [[ -z "$WORK_DIR" || "$WORK_DIR" == "null" ]]; then
    WORK_DIR=$(pwd)
fi

CLAUDE_MD="$WORK_DIR/CLAUDE.md"
MESSAGES=""

# =============================================================================
# CLAUDE.md Auto-Sync
# =============================================================================
sync_claude_md() {
    # Nur wenn Template existiert
    if [[ ! -f "$TEMPLATE_FILE" ]]; then
        return 0
    fi

    # Template-Version extrahieren
    TEMPLATE_VERSION=$(grep "$MARKER_START" "$TEMPLATE_FILE" 2>/dev/null | grep -o 'v[0-9.]*' | head -1)

    if [[ -f "$CLAUDE_MD" ]]; then
        # Prüfen ob Block vorhanden
        if ! grep -q "$MARKER_START" "$CLAUDE_MD" 2>/dev/null; then
            # Block am Anfang einfügen
            TEMP_FILE=$(mktemp)
            cat "$TEMPLATE_FILE" > "$TEMP_FILE"
            echo "" >> "$TEMP_FILE"
            cat "$CLAUDE_MD" >> "$TEMP_FILE"
            mv "$TEMP_FILE" "$CLAUDE_MD"
            MESSAGES="${MESSAGES}CHAINGUARD: CLAUDE.md mit Pflicht-Anweisungen ergänzt. "
        else
            # Prüfen ob Version aktuell
            CURRENT_VERSION=$(grep "$MARKER_START" "$CLAUDE_MD" 2>/dev/null | grep -o 'v[0-9.]*' | head -1)
            if [[ -n "$TEMPLATE_VERSION" && -n "$CURRENT_VERSION" && "$TEMPLATE_VERSION" != "$CURRENT_VERSION" ]]; then
                # Auto-Update: Alten Block ersetzen
                TEMP_FILE=$(mktemp)

                # Neuen Block schreiben
                cat "$TEMPLATE_FILE" > "$TEMP_FILE"
                echo "" >> "$TEMP_FILE"

                # Rest der Datei (nach dem alten Block) anhängen
                sed -n "/$MARKER_END/,\$p" "$CLAUDE_MD" | tail -n +2 >> "$TEMP_FILE"

                mv "$TEMP_FILE" "$CLAUDE_MD"
                MESSAGES="${MESSAGES}CHAINGUARD: CLAUDE.md Block aktualisiert ($CURRENT_VERSION -> $TEMPLATE_VERSION). "
            fi
        fi
    else
        # Prüfen ob wir in einem Projekt-Verzeichnis sind (nicht Home, nicht tmp, etc.)
        if [[ "$WORK_DIR" != "$HOME" && "$WORK_DIR" != "/tmp"* && "$WORK_DIR" != "/var"* ]]; then
            # Prüfen ob es ein Git-Repo ist oder eine package.json/composer.json hat
            if [[ -d "$WORK_DIR/.git" || -f "$WORK_DIR/package.json" || -f "$WORK_DIR/composer.json" ]]; then
                # Neue CLAUDE.md mit Template erstellen
                cp "$TEMPLATE_FILE" "$CLAUDE_MD"
                MESSAGES="${MESSAGES}CHAINGUARD: CLAUDE.md mit Pflicht-Anweisungen erstellt. "
            fi
        fi
    fi
}

# =============================================================================
# Scope-Prüfung
# =============================================================================

# v2.2: Project ID berechnen wie im MCP Server (3-stufig)
get_project_id() {
    local dir="$1"

    # 1. Try git remote URL
    local remote_url
    remote_url=$(git -C "$dir" remote get-url origin 2>/dev/null)
    if [[ -n "$remote_url" ]]; then
        echo -n "$remote_url" | shasum -a 256 | cut -c1-16
        return
    fi

    # 2. Try git root path
    local git_root
    git_root=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)
    if [[ -n "$git_root" ]]; then
        echo -n "$git_root" | shasum -a 256 | cut -c1-16
        return
    fi

    # 3. Fallback: working dir path
    echo -n "$dir" | shasum -a 256 | cut -c1-16
}

check_scope() {
    # v2.2: Project ID wie MCP Server berechnen
    PROJECT_ID=$(get_project_id "$WORK_DIR")
    PROJECT_FILE="$CHAINGUARD_HOME/projects/$PROJECT_ID/state.json"

    # Prüfen ob aktiver Scope existiert
    if [[ -f "$PROJECT_FILE" ]]; then
        # Prüfen ob Phase != "done" (also aktiv)
        PHASE=$(jq -r '.phase // "done"' "$PROJECT_FILE" 2>/dev/null)
        if [[ "$PHASE" != "done" && "$PHASE" != "unknown" ]]; then
            # Aktiver Scope vorhanden
            return 0
        fi
    fi

    # Kein aktiver Scope
    MESSAGES="${MESSAGES}CHAINGUARD: Kein aktiver Scope. Bitte chainguard_set_scope() aufrufen!"
    return 1
}

# =============================================================================
# Hauptlogik
# =============================================================================

# 1. CLAUDE.md synchronisieren
sync_claude_md

# 2. Scope prüfen
check_scope

# 3. Nachrichten ausgeben (falls vorhanden)
if [[ -n "$MESSAGES" ]]; then
    echo "$MESSAGES"
fi

exit 0
