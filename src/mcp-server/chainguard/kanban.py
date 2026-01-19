"""
CHAINGUARD MCP Server - Kanban Module (v6.5)

Persistent task management for complex, multi-day projects.
- YAML-based board storage
- Markdown files for detailed task descriptions
- Pipeline support with dependencies
- Survives session restarts

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
"""

import os
import uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

from .config import logger, KANBAN_ENABLED


# =============================================================================
# Constants
# =============================================================================
KANBAN_DIR = ".claude"
KANBAN_FILE = "kanban.yaml"
CARDS_DIR = "cards"
ARCHIVE_FILE = "archive.yaml"

DEFAULT_COLUMNS = ["backlog", "in_progress", "review", "done"]

# Vorlagen für verschiedene Projekt-Typen
COLUMN_PRESETS = {
    "default": ["backlog", "in_progress", "review", "done"],
    "programming": ["backlog", "in_progress", "testing", "review", "done"],
    "content": ["ideen", "entwurf", "überarbeitung", "lektorat", "fertig"],
    "devops": ["geplant", "vorbereitung", "deployment", "testing", "live"],
    "research": ["zu_untersuchen", "in_recherche", "analyse", "verifiziert", "dokumentiert"],
    "agile": ["backlog", "sprint", "in_progress", "review", "done"],
    "simple": ["todo", "doing", "done"],
}


# =============================================================================
# Enums
# =============================================================================
class CardPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __str__(self) -> str:
        return self.value


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class KanbanCard:
    """A single Kanban card."""
    id: str
    title: str
    column: str = "backlog"
    priority: str = "medium"
    detail_file: Optional[str] = None  # Path to .md file with details
    depends_on: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "column": self.column,
            "priority": self.priority,
            "detail_file": self.detail_file,
            "depends_on": self.depends_on,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KanbanCard":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            title=data.get("title", "Untitled"),
            column=data.get("column", "backlog"),
            priority=data.get("priority", "medium"),
            detail_file=data.get("detail_file"),
            depends_on=data.get("depends_on", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            tags=data.get("tags", [])
        )


@dataclass
class KanbanBoard:
    """The Kanban board with all cards."""
    columns: List[str] = field(default_factory=lambda: DEFAULT_COLUMNS.copy())
    cards: List[KanbanCard] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "columns": self.columns,
            "cards": [c.to_dict() for c in self.cards],
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KanbanBoard":
        """Create from dictionary."""
        return cls(
            columns=data.get("columns", DEFAULT_COLUMNS.copy()),
            cards=[KanbanCard.from_dict(c) for c in data.get("cards", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat())
        )

    def get_card(self, card_id: str) -> Optional[KanbanCard]:
        """Get a card by ID."""
        for card in self.cards:
            if card.id == card_id:
                return card
        return None

    def get_cards_by_column(self, column: str) -> List[KanbanCard]:
        """Get all cards in a column."""
        return [c for c in self.cards if c.column == column]


# =============================================================================
# Kanban Manager
# =============================================================================
class KanbanManager:
    """Manages Kanban boards for projects."""

    def __init__(self):
        self._boards: Dict[str, KanbanBoard] = {}

    def _get_kanban_path(self, working_dir: str) -> Path:
        """Get the path to the kanban.yaml file."""
        return Path(working_dir) / KANBAN_DIR / KANBAN_FILE

    def _get_cards_path(self, working_dir: str) -> Path:
        """Get the path to the cards directory."""
        return Path(working_dir) / KANBAN_DIR / CARDS_DIR

    def _get_archive_path(self, working_dir: str) -> Path:
        """Get the path to the archive.yaml file."""
        return Path(working_dir) / KANBAN_DIR / ARCHIVE_FILE

    def _ensure_dirs(self, working_dir: str) -> None:
        """Ensure the .claude directory structure exists."""
        kanban_dir = Path(working_dir) / KANBAN_DIR
        kanban_dir.mkdir(exist_ok=True)
        (kanban_dir / CARDS_DIR).mkdir(exist_ok=True)

    def load_board(self, working_dir: str) -> KanbanBoard:
        """Load or create a Kanban board for a project."""
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed - Kanban disabled")
            return KanbanBoard()

        kanban_path = self._get_kanban_path(working_dir)

        # Check cache first
        cache_key = str(kanban_path)
        if cache_key in self._boards:
            return self._boards[cache_key]

        # Load from file or create new
        if kanban_path.exists():
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                board = KanbanBoard.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load kanban: {e}")
                board = KanbanBoard()
        else:
            board = KanbanBoard()

        self._boards[cache_key] = board
        return board

    def save_board(self, working_dir: str, board: KanbanBoard) -> None:
        """Save a Kanban board to disk."""
        if not YAML_AVAILABLE:
            return

        self._ensure_dirs(working_dir)
        kanban_path = self._get_kanban_path(working_dir)

        board.updated_at = datetime.now().isoformat()

        try:
            with open(kanban_path, 'w', encoding='utf-8') as f:
                yaml.dump(board.to_dict(), f, default_flow_style=False, allow_unicode=True)

            # Update cache
            self._boards[str(kanban_path)] = board
        except Exception as e:
            logger.error(f"Failed to save kanban: {e}")

    def board_exists(self, working_dir: str) -> bool:
        """Check if a Kanban board exists for this project."""
        return self._get_kanban_path(working_dir).exists()

    def init_board(
        self,
        working_dir: str,
        columns: Optional[List[str]] = None,
        preset: Optional[str] = None
    ) -> KanbanBoard:
        """Initialize a new Kanban board with custom columns.

        Args:
            working_dir: Project directory
            columns: Custom column names (e.g., ["todo", "doing", "done"])
            preset: Use a preset ("programming", "content", "devops", "research", "agile", "simple")

        Returns:
            The initialized KanbanBoard
        """
        if not YAML_AVAILABLE:
            return KanbanBoard()

        # Determine columns
        if columns:
            board_columns = columns
        elif preset and preset in COLUMN_PRESETS:
            board_columns = COLUMN_PRESETS[preset]
        else:
            board_columns = DEFAULT_COLUMNS.copy()

        # Check if board already exists
        if self.board_exists(working_dir):
            # Load existing and update columns if different
            board = self.load_board(working_dir)
            if board.columns != board_columns:
                # Migrate cards to new column structure
                board = self._migrate_columns(board, board_columns)
        else:
            board = KanbanBoard(columns=board_columns)

        self.save_board(working_dir, board)
        return board

    def _migrate_columns(self, board: KanbanBoard, new_columns: List[str]) -> KanbanBoard:
        """Migrate cards when columns change.

        Cards in columns that no longer exist are moved to the first column.
        """
        first_column = new_columns[0] if new_columns else "backlog"

        for card in board.cards:
            if card.column not in new_columns:
                card.column = first_column
                card.updated_at = datetime.now().isoformat()

        board.columns = new_columns
        return board

    def get_available_presets(self) -> dict:
        """Get all available column presets."""
        return COLUMN_PRESETS.copy()

    # =========================================================================
    # Card Operations
    # =========================================================================
    def add_card(
        self,
        working_dir: str,
        title: str,
        column: str = "backlog",
        priority: str = "medium",
        depends_on: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        detail_content: Optional[str] = None
    ) -> KanbanCard:
        """Add a new card to the board."""
        board = self.load_board(working_dir)

        # Generate unique ID
        card_id = str(uuid.uuid4())[:8]

        # Create detail file if content provided
        detail_file = None
        if detail_content:
            detail_file = f"{CARDS_DIR}/{card_id}.md"
            self._write_detail_file(working_dir, card_id, title, detail_content)

        card = KanbanCard(
            id=card_id,
            title=title,
            column=column if column in board.columns else "backlog",
            priority=priority,
            detail_file=detail_file,
            depends_on=depends_on or [],
            tags=tags or []
        )

        board.cards.append(card)
        self.save_board(working_dir, board)

        return card

    def move_card(self, working_dir: str, card_id: str, to_column: str) -> Optional[KanbanCard]:
        """Move a card to a different column."""
        board = self.load_board(working_dir)
        card = board.get_card(card_id)

        if not card:
            return None

        if to_column not in board.columns:
            return None

        card.column = to_column
        card.updated_at = datetime.now().isoformat()

        self.save_board(working_dir, board)
        return card

    def delete_card(self, working_dir: str, card_id: str) -> bool:
        """Delete a card permanently."""
        board = self.load_board(working_dir)

        for i, card in enumerate(board.cards):
            if card.id == card_id:
                # Delete detail file if exists
                if card.detail_file:
                    detail_path = Path(working_dir) / KANBAN_DIR / card.detail_file
                    if detail_path.exists():
                        detail_path.unlink()

                board.cards.pop(i)
                self.save_board(working_dir, board)
                return True

        return False

    def archive_card(self, working_dir: str, card_id: str) -> bool:
        """Archive a card (move to archive.yaml)."""
        if not YAML_AVAILABLE:
            return False

        board = self.load_board(working_dir)
        card = board.get_card(card_id)

        if not card:
            return False

        # Load archive
        archive_path = self._get_archive_path(working_dir)
        archive = []
        if archive_path.exists():
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    archive = yaml.safe_load(f) or []
            except Exception:
                archive = []

        # Add to archive with timestamp
        archived_card = card.to_dict()
        archived_card["archived_at"] = datetime.now().isoformat()
        archive.append(archived_card)

        # Save archive
        self._ensure_dirs(working_dir)
        with open(archive_path, 'w', encoding='utf-8') as f:
            yaml.dump(archive, f, default_flow_style=False, allow_unicode=True)

        # Remove from board
        board.cards = [c for c in board.cards if c.id != card_id]
        self.save_board(working_dir, board)

        return True

    def update_card(
        self,
        working_dir: str,
        card_id: str,
        title: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None
    ) -> Optional[KanbanCard]:
        """Update card properties."""
        board = self.load_board(working_dir)
        card = board.get_card(card_id)

        if not card:
            return None

        if title:
            card.title = title
        if priority:
            card.priority = priority
        if tags is not None:
            card.tags = tags
        if depends_on is not None:
            card.depends_on = depends_on

        card.updated_at = datetime.now().isoformat()
        self.save_board(working_dir, board)

        return card

    # =========================================================================
    # Detail Files
    # =========================================================================
    def _write_detail_file(self, working_dir: str, card_id: str, title: str, content: str) -> None:
        """Write a detail markdown file for a card."""
        self._ensure_dirs(working_dir)
        detail_path = Path(working_dir) / KANBAN_DIR / CARDS_DIR / f"{card_id}.md"

        with open(detail_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(content)

    def get_card_detail(self, working_dir: str, card_id: str) -> Optional[str]:
        """Get the detail content for a card."""
        board = self.load_board(working_dir)
        card = board.get_card(card_id)

        if not card or not card.detail_file:
            return None

        detail_path = Path(working_dir) / KANBAN_DIR / card.detail_file

        if not detail_path.exists():
            return None

        try:
            with open(detail_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read detail file: {e}")
            return None

    def set_card_detail(self, working_dir: str, card_id: str, content: str) -> bool:
        """Set or update the detail content for a card."""
        board = self.load_board(working_dir)
        card = board.get_card(card_id)

        if not card:
            return False

        # Create detail file if not exists
        if not card.detail_file:
            card.detail_file = f"{CARDS_DIR}/{card_id}.md"
            self.save_board(working_dir, board)

        self._write_detail_file(working_dir, card_id, card.title, content)
        return True

    # =========================================================================
    # Board Views
    # =========================================================================
    def get_board_view(self, working_dir: str, compact: bool = True) -> str:
        """Get a formatted view of the board."""
        board = self.load_board(working_dir)

        if not board.cards:
            return "📋 Kanban: Leer (nutze kanban_add um Cards zu erstellen)"

        lines = ["📋 **Kanban Board**\n"]

        for column in board.columns:
            cards = board.get_cards_by_column(column)
            column_icon = {
                "backlog": "📥",
                "in_progress": "🔄",
                "review": "👀",
                "done": "✅"
            }.get(column, "📌")

            lines.append(f"{column_icon} **{column.upper()}** ({len(cards)})")

            if cards:
                for card in cards:
                    priority_icon = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢"
                    }.get(card.priority, "⚪")

                    detail_marker = "📎" if card.detail_file else ""
                    deps_marker = f"⛓️{len(card.depends_on)}" if card.depends_on else ""

                    if compact:
                        lines.append(f"  {priority_icon} `{card.id}` {card.title} {detail_marker}{deps_marker}")
                    else:
                        lines.append(f"  {priority_icon} **{card.id}**: {card.title}")
                        if card.tags:
                            lines.append(f"    Tags: {', '.join(card.tags)}")
                        if card.depends_on:
                            lines.append(f"    Depends: {', '.join(card.depends_on)}")
            else:
                lines.append("  (leer)")

            lines.append("")

        return "\n".join(lines)

    def get_full_board_view(self, working_dir: str) -> str:
        """Get a full graphical board view with all details including linked MD files.

        This is the 'show' view that displays everything in a visual format.
        """
        board = self.load_board(working_dir)

        if not board.cards:
            return self._render_empty_board()

        # Calculate statistics
        total = len(board.cards)
        by_column = {col: len(board.get_cards_by_column(col)) for col in board.columns}
        blocked = self.get_blocked_cards(working_dir)
        blocked_ids = {c.id for c in blocked}

        # Progress calculation
        done_count = by_column.get("done", 0)
        progress_pct = (done_count / total * 100) if total > 0 else 0

        lines = []

        # Header with progress bar
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + " 📋 KANBAN BOARD ".center(78) + "║")
        lines.append("╠" + "═" * 78 + "╣")

        # Progress bar
        bar_width = 40
        filled = int(bar_width * progress_pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        progress_line = f"  Progress: [{bar}] {progress_pct:.0f}% ({done_count}/{total} done)"
        lines.append("║" + progress_line.ljust(78) + "║")

        # Stats line
        stats = f"  📥 {by_column.get('backlog', 0)} │ 🔄 {by_column.get('in_progress', 0)} │ 👀 {by_column.get('review', 0)} │ ✅ {by_column.get('done', 0)}"
        if blocked:
            stats += f" │ ⛔ {len(blocked)} blocked"
        lines.append("║" + stats.ljust(78) + "║")
        lines.append("╠" + "═" * 78 + "╣")

        # Render each column
        column_icons = {
            "backlog": ("📥", "BACKLOG"),
            "in_progress": ("🔄", "IN PROGRESS"),
            "review": ("👀", "REVIEW"),
            "done": ("✅", "DONE")
        }

        for column in board.columns:
            icon, label = column_icons.get(column, ("📌", column.upper()))
            cards = board.get_cards_by_column(column)

            # Column header
            lines.append("║" + f" {icon} {label} ({len(cards)})".ljust(78) + "║")
            lines.append("║" + "─" * 78 + "║")

            if cards:
                for card in cards:
                    # Card rendering
                    lines.extend(self._render_card_full(card, working_dir, blocked_ids))
            else:
                lines.append("║" + "   (keine Cards)".ljust(78) + "║")

            lines.append("║" + " " * 78 + "║")

        # Footer
        lines.append("╠" + "═" * 78 + "╣")
        lines.append("║" + f" 🕐 Stand: {datetime.now().strftime('%Y-%m-%d %H:%M')}".ljust(78) + "║")
        lines.append("╚" + "═" * 78 + "╝")

        return "\n".join(lines)

    def _render_empty_board(self) -> str:
        """Render an empty board view."""
        lines = [
            "╔" + "═" * 78 + "╗",
            "║" + " 📋 KANBAN BOARD ".center(78) + "║",
            "╠" + "═" * 78 + "╣",
            "║" + " " * 78 + "║",
            "║" + "   Das Board ist leer.".ljust(78) + "║",
            "║" + " " * 78 + "║",
            "║" + "   Nutze chainguard_kanban_add(title=\"...\") um Cards zu erstellen.".ljust(78) + "║",
            "║" + " " * 78 + "║",
            "╚" + "═" * 78 + "╝"
        ]
        return "\n".join(lines)

    def _render_card_full(self, card: KanbanCard, working_dir: str, blocked_ids: set) -> List[str]:
        """Render a single card with full details."""
        lines = []

        # Priority icon and colors
        priority_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }
        p_icon = priority_icons.get(card.priority, "⚪")

        # Status indicators
        is_blocked = card.id in blocked_ids
        status_marker = "⛔ BLOCKED" if is_blocked else ""

        # Main card line
        card_header = f"   ┌─ {p_icon} [{card.id}] {card.title[:50]}"
        if status_marker:
            card_header += f" {status_marker}"
        lines.append("║" + card_header.ljust(78) + "║")

        # Card details
        details = []

        # Priority and dates
        created = card.created_at[:10] if card.created_at else "?"
        updated = card.updated_at[:10] if card.updated_at else "?"
        details.append(f"Priority: {card.priority.upper()} │ Created: {created} │ Updated: {updated}")

        # Tags
        if card.tags:
            tag_str = " ".join([f"#{t}" for t in card.tags])
            details.append(f"Tags: {tag_str}")

        # Dependencies
        if card.depends_on:
            dep_str = ", ".join(card.depends_on)
            details.append(f"⛓️ Depends on: {dep_str}")

        # Render detail lines
        for detail in details:
            lines.append("║" + f"   │  {detail[:72]}".ljust(78) + "║")

        # Linked MD file content (preview)
        if card.detail_file:
            detail_content = self.get_card_detail(working_dir, card.id)
            if detail_content:
                lines.append("║" + "   │  📄 Detail-Datei:".ljust(78) + "║")
                lines.append("║" + f"   │  ┌{'─' * 70}".ljust(78) + "║")

                # Show first 8 lines of the detail file
                detail_lines = detail_content.strip().split('\n')[:8]
                for dl in detail_lines:
                    # Truncate long lines
                    truncated = dl[:68] if len(dl) > 68 else dl
                    lines.append("║" + f"   │  │ {truncated}".ljust(78) + "║")

                if len(detail_content.strip().split('\n')) > 8:
                    lines.append("║" + f"   │  │ ... ({len(detail_content.strip().split(chr(10)))} Zeilen gesamt)".ljust(78) + "║")

                lines.append("║" + f"   │  └{'─' * 70}".ljust(78) + "║")
        else:
            lines.append("║" + "   │  (keine Detail-Datei verknüpft)".ljust(78) + "║")

        # Card footer
        lines.append("║" + "   └" + "─" * 74 + "║")

        return lines

    def get_archive_view(self, working_dir: str, limit: int = 10) -> str:
        """Get a view of archived cards."""
        if not YAML_AVAILABLE:
            return "PyYAML nicht installiert"

        archive_path = self._get_archive_path(working_dir)

        if not archive_path.exists():
            return "📦 Archiv: Leer"

        try:
            with open(archive_path, 'r', encoding='utf-8') as f:
                archive = yaml.safe_load(f) or []
        except Exception:
            return "📦 Archiv: Fehler beim Laden"

        if not archive:
            return "📦 Archiv: Leer"

        lines = [f"📦 **Archiv** ({len(archive)} Cards)\n"]

        for card in archive[-limit:]:
            lines.append(f"  - `{card.get('id', '?')}` {card.get('title', 'Untitled')}")
            lines.append(f"    Archiviert: {card.get('archived_at', '?')[:10]}")

        if len(archive) > limit:
            lines.append(f"\n  ... und {len(archive) - limit} weitere")

        return "\n".join(lines)

    def get_blocked_cards(self, working_dir: str) -> List[KanbanCard]:
        """Get cards that are blocked by dependencies.

        A card is blocked if it depends on another card that:
        - Is still in the board (not archived/deleted)
        - AND is not in the "done" column
        """
        board = self.load_board(working_dir)
        blocked = []

        # IDs of cards that are done or no longer in the board
        done_ids = {c.id for c in board.cards if c.column == "done"}
        all_card_ids = {c.id for c in board.cards}

        for card in board.cards:
            if card.column == "done":
                continue

            if card.depends_on:
                # Only consider dependencies that are still in the board and not done
                unmet = [
                    dep for dep in card.depends_on
                    if dep in all_card_ids and dep not in done_ids
                ]
                if unmet:
                    blocked.append(card)

        return blocked


# =============================================================================
# Singleton Instance
# =============================================================================
kanban_manager = KanbanManager()
