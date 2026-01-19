"""
Unit tests for Kanban System (v6.5)

Tests:
- KanbanCard creation and serialization
- KanbanBoard operations
- KanbanManager CRUD operations
- Dependency/blocking logic
- Archive functionality
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from chainguard.kanban import (
    KanbanCard, KanbanBoard, KanbanManager,
    CardPriority, DEFAULT_COLUMNS, COLUMN_PRESETS, YAML_AVAILABLE
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    dir_path = tempfile.mkdtemp(prefix="kanban_test_")
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def manager():
    """Create a fresh KanbanManager instance."""
    return KanbanManager()


# =============================================================================
# KanbanCard Tests
# =============================================================================

class TestKanbanCard:
    """Tests for KanbanCard dataclass."""

    def test_card_creation_minimal(self):
        """Test creating a card with minimal fields."""
        card = KanbanCard(id="abc123", title="Test Task")
        assert card.id == "abc123"
        assert card.title == "Test Task"
        assert card.column == "backlog"
        assert card.priority == "medium"
        assert card.detail_file is None
        assert card.depends_on == []
        assert card.tags == []

    def test_card_creation_full(self):
        """Test creating a card with all fields."""
        card = KanbanCard(
            id="xyz789",
            title="Full Task",
            column="in_progress",
            priority="critical",
            detail_file="cards/xyz789.md",
            depends_on=["abc123"],
            tags=["backend", "urgent"]
        )
        assert card.column == "in_progress"
        assert card.priority == "critical"
        assert card.detail_file == "cards/xyz789.md"
        assert "abc123" in card.depends_on
        assert "backend" in card.tags

    def test_card_to_dict(self):
        """Test card serialization to dictionary."""
        card = KanbanCard(id="test1", title="Dict Test", priority="high")
        d = card.to_dict()
        assert d["id"] == "test1"
        assert d["title"] == "Dict Test"
        assert d["priority"] == "high"
        assert "created_at" in d
        assert "updated_at" in d

    def test_card_from_dict(self):
        """Test card deserialization from dictionary."""
        data = {
            "id": "from_dict",
            "title": "From Dict",
            "column": "review",
            "priority": "low",
            "tags": ["test"]
        }
        card = KanbanCard.from_dict(data)
        assert card.id == "from_dict"
        assert card.title == "From Dict"
        assert card.column == "review"
        assert card.priority == "low"
        assert "test" in card.tags

    def test_card_from_dict_defaults(self):
        """Test card from dict uses defaults for missing fields."""
        data = {"title": "Minimal"}
        card = KanbanCard.from_dict(data)
        assert card.title == "Minimal"
        assert card.column == "backlog"
        assert card.priority == "medium"
        assert len(card.id) == 8  # Auto-generated


# =============================================================================
# KanbanBoard Tests
# =============================================================================

class TestKanbanBoard:
    """Tests for KanbanBoard dataclass."""

    def test_board_creation_default(self):
        """Test creating a board with defaults."""
        board = KanbanBoard()
        assert board.columns == DEFAULT_COLUMNS
        assert board.cards == []
        assert board.created_at is not None
        assert board.updated_at is not None

    def test_board_get_card(self):
        """Test getting a card by ID."""
        board = KanbanBoard()
        card = KanbanCard(id="findme", title="Find Me")
        board.cards.append(card)

        found = board.get_card("findme")
        assert found is not None
        assert found.title == "Find Me"

        not_found = board.get_card("notexist")
        assert not_found is None

    def test_board_get_cards_by_column(self):
        """Test filtering cards by column."""
        board = KanbanBoard()
        board.cards.extend([
            KanbanCard(id="1", title="Task 1", column="backlog"),
            KanbanCard(id="2", title="Task 2", column="backlog"),
            KanbanCard(id="3", title="Task 3", column="in_progress"),
        ])

        backlog = board.get_cards_by_column("backlog")
        assert len(backlog) == 2

        in_progress = board.get_cards_by_column("in_progress")
        assert len(in_progress) == 1

        done = board.get_cards_by_column("done")
        assert len(done) == 0

    def test_board_to_dict(self):
        """Test board serialization."""
        board = KanbanBoard()
        board.cards.append(KanbanCard(id="x", title="Test"))
        d = board.to_dict()
        assert "columns" in d
        assert "cards" in d
        assert len(d["cards"]) == 1

    def test_board_from_dict(self):
        """Test board deserialization."""
        data = {
            "columns": ["todo", "doing", "done"],
            "cards": [
                {"id": "1", "title": "Task 1"},
                {"id": "2", "title": "Task 2", "column": "doing"}
            ]
        }
        board = KanbanBoard.from_dict(data)
        assert board.columns == ["todo", "doing", "done"]
        assert len(board.cards) == 2
        assert board.cards[1].column == "doing"


# =============================================================================
# KanbanManager Tests
# =============================================================================

@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestKanbanManager:
    """Tests for KanbanManager."""

    def test_load_board_creates_new(self, manager, temp_dir):
        """Test loading a board creates new if not exists."""
        board = manager.load_board(temp_dir)
        assert isinstance(board, KanbanBoard)
        assert board.columns == DEFAULT_COLUMNS

    def test_save_and_load_board(self, manager, temp_dir):
        """Test saving and loading persists data."""
        # Add a card and save
        card = manager.add_card(temp_dir, "Persist Test")

        # Create new manager to clear cache
        manager2 = KanbanManager()
        board = manager2.load_board(temp_dir)

        assert len(board.cards) == 1
        assert board.cards[0].title == "Persist Test"

    def test_add_card_basic(self, manager, temp_dir):
        """Test adding a basic card."""
        card = manager.add_card(temp_dir, "Basic Card")
        assert card.title == "Basic Card"
        assert card.column == "backlog"
        assert len(card.id) == 8

    def test_add_card_with_options(self, manager, temp_dir):
        """Test adding a card with all options."""
        card = manager.add_card(
            working_dir=temp_dir,
            title="Full Card",
            column="in_progress",
            priority="critical",
            depends_on=["other_id"],
            tags=["test", "important"]
        )
        assert card.column == "in_progress"
        assert card.priority == "critical"
        assert "other_id" in card.depends_on
        assert "test" in card.tags

    def test_add_card_with_detail(self, manager, temp_dir):
        """Test adding a card creates detail file."""
        card = manager.add_card(
            working_dir=temp_dir,
            title="Detail Card",
            detail_content="# My Task\n\nDetails here."
        )
        assert card.detail_file is not None

        detail = manager.get_card_detail(temp_dir, card.id)
        assert "My Task" in detail
        assert "Details here" in detail

    def test_move_card(self, manager, temp_dir):
        """Test moving a card to different column."""
        card = manager.add_card(temp_dir, "Move Me")
        assert card.column == "backlog"

        moved = manager.move_card(temp_dir, card.id, "in_progress")
        assert moved.column == "in_progress"

        # Verify persistence
        board = manager.load_board(temp_dir)
        assert board.get_card(card.id).column == "in_progress"

    def test_move_card_invalid_column(self, manager, temp_dir):
        """Test moving to invalid column returns None."""
        card = manager.add_card(temp_dir, "Invalid Move")
        result = manager.move_card(temp_dir, card.id, "invalid_column")
        assert result is None

    def test_move_card_not_found(self, manager, temp_dir):
        """Test moving non-existent card returns None."""
        result = manager.move_card(temp_dir, "notexist", "done")
        assert result is None

    def test_update_card(self, manager, temp_dir):
        """Test updating card properties."""
        card = manager.add_card(temp_dir, "Update Me", priority="low")

        updated = manager.update_card(
            working_dir=temp_dir,
            card_id=card.id,
            title="Updated Title",
            priority="high",
            tags=["updated"]
        )
        assert updated.title == "Updated Title"
        assert updated.priority == "high"
        assert "updated" in updated.tags

    def test_delete_card(self, manager, temp_dir):
        """Test deleting a card."""
        card = manager.add_card(temp_dir, "Delete Me")
        card_id = card.id

        success = manager.delete_card(temp_dir, card_id)
        assert success

        board = manager.load_board(temp_dir)
        assert board.get_card(card_id) is None

    def test_delete_card_removes_detail_file(self, manager, temp_dir):
        """Test deleting a card removes its detail file."""
        card = manager.add_card(
            temp_dir,
            "Delete With Detail",
            detail_content="Some content"
        )
        detail_path = Path(temp_dir) / ".claude" / card.detail_file
        assert detail_path.exists()

        manager.delete_card(temp_dir, card.id)
        assert not detail_path.exists()

    def test_archive_card(self, manager, temp_dir):
        """Test archiving a card."""
        card = manager.add_card(temp_dir, "Archive Me")
        card_id = card.id

        success = manager.archive_card(temp_dir, card_id)
        assert success

        # Card should be removed from board
        board = manager.load_board(temp_dir)
        assert board.get_card(card_id) is None

        # Card should be in archive
        archive_view = manager.get_archive_view(temp_dir)
        assert card_id in archive_view

    def test_board_exists(self, manager, temp_dir):
        """Test board_exists check."""
        assert not manager.board_exists(temp_dir)

        manager.add_card(temp_dir, "Create Board")
        assert manager.board_exists(temp_dir)


# =============================================================================
# Board Initialization Tests
# =============================================================================

@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestBoardInitialization:
    """Tests for board initialization with presets and custom columns."""

    def test_init_board_default(self, manager, temp_dir):
        """Test init_board with default columns."""
        board = manager.init_board(temp_dir)
        assert board.columns == DEFAULT_COLUMNS

    def test_init_board_preset_programming(self, manager, temp_dir):
        """Test init_board with programming preset."""
        board = manager.init_board(temp_dir, preset="programming")
        assert board.columns == COLUMN_PRESETS["programming"]
        assert "testing" in board.columns

    def test_init_board_preset_content(self, manager, temp_dir):
        """Test init_board with content preset."""
        board = manager.init_board(temp_dir, preset="content")
        assert board.columns == COLUMN_PRESETS["content"]
        assert "entwurf" in board.columns

    def test_init_board_preset_devops(self, manager, temp_dir):
        """Test init_board with devops preset."""
        board = manager.init_board(temp_dir, preset="devops")
        assert board.columns == COLUMN_PRESETS["devops"]
        assert "deployment" in board.columns

    def test_init_board_preset_research(self, manager, temp_dir):
        """Test init_board with research preset."""
        board = manager.init_board(temp_dir, preset="research")
        assert board.columns == COLUMN_PRESETS["research"]
        assert "verifiziert" in board.columns

    def test_init_board_preset_simple(self, manager, temp_dir):
        """Test init_board with simple preset."""
        board = manager.init_board(temp_dir, preset="simple")
        assert board.columns == ["todo", "doing", "done"]

    def test_init_board_custom_columns(self, manager, temp_dir):
        """Test init_board with custom columns."""
        custom = ["planning", "development", "qa", "deployed"]
        board = manager.init_board(temp_dir, columns=custom)
        assert board.columns == custom

    def test_init_board_custom_overrides_preset(self, manager, temp_dir):
        """Test custom columns override preset."""
        custom = ["a", "b", "c"]
        board = manager.init_board(temp_dir, preset="programming", columns=custom)
        assert board.columns == custom  # Custom wins

    def test_init_board_invalid_preset_uses_default(self, manager, temp_dir):
        """Test invalid preset falls back to default."""
        board = manager.init_board(temp_dir, preset="nonexistent")
        assert board.columns == DEFAULT_COLUMNS

    def test_get_available_presets(self, manager):
        """Test getting available presets."""
        presets = manager.get_available_presets()
        assert "default" in presets
        assert "programming" in presets
        assert "content" in presets
        assert "devops" in presets
        assert "research" in presets
        assert "agile" in presets
        assert "simple" in presets
        # Check presets have column lists
        for name, columns in presets.items():
            assert isinstance(columns, list)
            assert len(columns) >= 3

    def test_init_board_preserves_existing_cards(self, manager, temp_dir):
        """Test init_board preserves cards when changing columns."""
        # Create board with cards
        manager.add_card(temp_dir, "Task 1", column="backlog")
        manager.add_card(temp_dir, "Task 2", column="in_progress")

        # Re-init with new columns
        board = manager.init_board(temp_dir, columns=["todo", "doing", "done"])

        # Cards should still exist
        assert len(board.cards) == 2
        # Cards in old columns should move to first column
        for card in board.cards:
            assert card.column == "todo"

    def test_column_presets_structure(self):
        """Test COLUMN_PRESETS has expected structure."""
        assert isinstance(COLUMN_PRESETS, dict)
        assert len(COLUMN_PRESETS) >= 7
        for preset_name, columns in COLUMN_PRESETS.items():
            assert isinstance(columns, list)
            assert all(isinstance(col, str) for col in columns)


# =============================================================================
# Dependency/Blocking Tests
# =============================================================================

@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestDependencies:
    """Tests for dependency and blocking logic."""

    def test_blocked_cards_with_pending_dependency(self, manager, temp_dir):
        """Test card is blocked when dependency is not done."""
        parent = manager.add_card(temp_dir, "Parent", column="in_progress")
        child = manager.add_card(temp_dir, "Child", depends_on=[parent.id])

        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 1
        assert blocked[0].id == child.id

    def test_blocked_cards_with_done_dependency(self, manager, temp_dir):
        """Test card is not blocked when dependency is done."""
        parent = manager.add_card(temp_dir, "Parent", column="done")
        child = manager.add_card(temp_dir, "Child", depends_on=[parent.id])

        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 0

    def test_blocked_cards_with_archived_dependency(self, manager, temp_dir):
        """Test card is not blocked when dependency is archived."""
        parent = manager.add_card(temp_dir, "Parent")
        child = manager.add_card(temp_dir, "Child", depends_on=[parent.id])

        # Initially blocked
        assert len(manager.get_blocked_cards(temp_dir)) == 1

        # Archive parent
        manager.move_card(temp_dir, parent.id, "done")
        manager.archive_card(temp_dir, parent.id)

        # No longer blocked
        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 0

    def test_blocked_cards_with_deleted_dependency(self, manager, temp_dir):
        """Test card is not blocked when dependency is deleted."""
        parent = manager.add_card(temp_dir, "Parent")
        child = manager.add_card(temp_dir, "Child", depends_on=[parent.id])

        # Delete parent
        manager.delete_card(temp_dir, parent.id)

        # No longer blocked (orphaned dependency)
        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 0

    def test_multiple_dependencies(self, manager, temp_dir):
        """Test card with multiple dependencies."""
        dep1 = manager.add_card(temp_dir, "Dep 1", column="done")
        dep2 = manager.add_card(temp_dir, "Dep 2", column="in_progress")
        child = manager.add_card(temp_dir, "Child", depends_on=[dep1.id, dep2.id])

        # Blocked because dep2 is not done
        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 1

        # Complete dep2
        manager.move_card(temp_dir, dep2.id, "done")

        # No longer blocked
        blocked = manager.get_blocked_cards(temp_dir)
        assert len(blocked) == 0


# =============================================================================
# Board View Tests
# =============================================================================

@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestBoardViews:
    """Tests for board view formatting."""

    def test_empty_board_view(self, manager, temp_dir):
        """Test view of empty board."""
        view = manager.get_board_view(temp_dir)
        assert "Leer" in view

    def test_board_view_compact(self, manager, temp_dir):
        """Test compact board view."""
        manager.add_card(temp_dir, "Task 1", priority="high")
        manager.add_card(temp_dir, "Task 2", priority="low")

        view = manager.get_board_view(temp_dir, compact=True)
        assert "BACKLOG" in view
        assert "Task 1" in view
        assert "Task 2" in view

    def test_board_view_shows_priority_icons(self, manager, temp_dir):
        """Test board view shows priority icons."""
        manager.add_card(temp_dir, "Critical", priority="critical")
        manager.add_card(temp_dir, "Low", priority="low")

        view = manager.get_board_view(temp_dir)
        assert "🔴" in view  # critical
        assert "🟢" in view  # low

    def test_board_view_shows_detail_marker(self, manager, temp_dir):
        """Test board view shows detail file marker."""
        manager.add_card(temp_dir, "With Detail", detail_content="Content")
        view = manager.get_board_view(temp_dir)
        assert "📎" in view

    def test_board_view_shows_dependency_marker(self, manager, temp_dir):
        """Test board view shows dependency marker."""
        parent = manager.add_card(temp_dir, "Parent")
        manager.add_card(temp_dir, "Child", depends_on=[parent.id])

        view = manager.get_board_view(temp_dir)
        assert "⛓️" in view

    def test_archive_view_empty(self, manager, temp_dir):
        """Test empty archive view."""
        view = manager.get_archive_view(temp_dir)
        assert "Leer" in view

    def test_archive_view_with_items(self, manager, temp_dir):
        """Test archive view with archived items."""
        card = manager.add_card(temp_dir, "To Archive")
        manager.archive_card(temp_dir, card.id)

        view = manager.get_archive_view(temp_dir)
        assert "To Archive" in view
        assert "Archiv" in view


# =============================================================================
# CardPriority Enum Tests
# =============================================================================

class TestCardPriority:
    """Tests for CardPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        assert str(CardPriority.LOW) == "low"
        assert str(CardPriority.MEDIUM) == "medium"
        assert str(CardPriority.HIGH) == "high"
        assert str(CardPriority.CRITICAL) == "critical"
