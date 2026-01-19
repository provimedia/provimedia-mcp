#!/usr/bin/env python3
"""
Test script for Kanban System (v6.5)

Run with: python3 test/test_kanban.py
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "mcp-server"))

from chainguard.kanban import KanbanManager, KanbanCard, KanbanBoard, YAML_AVAILABLE


def test_kanban_system():
    """Test the Kanban system."""
    print("=" * 60)
    print("KANBAN SYSTEM TEST (v6.5)")
    print("=" * 60)

    if not YAML_AVAILABLE:
        print("⚠️  PyYAML not installed - skipping tests")
        return False

    # Create temp directory for testing
    test_dir = tempfile.mkdtemp(prefix="kanban_test_")
    print(f"\n📁 Test directory: {test_dir}")

    try:
        manager = KanbanManager()

        # Test 0: Custom Column Initialization
        print("\n--- Test 0: Custom Column Initialization ---")

        # Test with preset
        board = manager.init_board(test_dir, preset="content")
        assert board.columns == ["ideen", "entwurf", "überarbeitung", "lektorat", "fertig"]
        print(f"✓ Preset 'content': {' → '.join(board.columns)}")

        # Test with custom columns
        custom_cols = ["planning", "development", "testing", "deployed"]
        board = manager.init_board(test_dir, columns=custom_cols)
        assert board.columns == custom_cols
        print(f"✓ Custom columns: {' → '.join(board.columns)}")

        # Test presets listing
        presets = manager.get_available_presets()
        assert "programming" in presets
        assert "devops" in presets
        print(f"✓ Available presets: {', '.join(presets.keys())}")

        # Reset to default for other tests
        board = manager.init_board(test_dir, preset="default")

        # Test 1: Create board
        print("\n--- Test 1: Board Creation ---")
        board = manager.load_board(test_dir)
        assert isinstance(board, KanbanBoard)
        assert board.columns == ["backlog", "in_progress", "review", "done"]
        print("✓ Board created with default columns")

        # Test 2: Add cards
        print("\n--- Test 2: Add Cards ---")
        card1 = manager.add_card(
            working_dir=test_dir,
            title="Implement Auth System",
            column="backlog",
            priority="high",
            tags=["backend", "security"]
        )
        print(f"✓ Card 1 added: {card1.id} - {card1.title}")

        card2 = manager.add_card(
            working_dir=test_dir,
            title="Build Login UI",
            column="backlog",
            priority="medium",
            depends_on=[card1.id],
            detail_content="## Requirements\n\n- Email/Password form\n- Remember me checkbox\n- Forgot password link"
        )
        print(f"✓ Card 2 added: {card2.id} - {card2.title} (depends on {card1.id})")

        card3 = manager.add_card(
            working_dir=test_dir,
            title="Write Tests",
            column="backlog",
            priority="low"
        )
        print(f"✓ Card 3 added: {card3.id} - {card3.title}")

        # Test 3: View board
        print("\n--- Test 3: View Board ---")
        board_view = manager.get_board_view(test_dir)
        print(board_view)

        # Test 4: Move card
        print("\n--- Test 4: Move Card ---")
        moved = manager.move_card(test_dir, card1.id, "in_progress")
        assert moved is not None
        assert moved.column == "in_progress"
        print(f"✓ Card {card1.id} moved to in_progress")

        # Test 5: Check blocked cards
        print("\n--- Test 5: Blocked Cards ---")
        blocked = manager.get_blocked_cards(test_dir)
        assert len(blocked) == 1  # card2 depends on card1 which is not done
        print(f"✓ Found {len(blocked)} blocked card(s): {blocked[0].id}")

        # Test 6: Get card detail
        print("\n--- Test 6: Card Detail ---")
        detail = manager.get_card_detail(test_dir, card2.id)
        assert detail is not None
        assert "Requirements" in detail
        print(f"✓ Card detail loaded ({len(detail)} chars)")

        # Test 7: Update card
        print("\n--- Test 7: Update Card ---")
        updated = manager.update_card(
            working_dir=test_dir,
            card_id=card3.id,
            priority="high",
            tags=["testing", "qa"]
        )
        assert updated is not None
        assert updated.priority == "high"
        print(f"✓ Card {card3.id} updated: priority={updated.priority}, tags={updated.tags}")

        # Test 8: Complete and archive
        print("\n--- Test 8: Complete & Archive ---")
        manager.move_card(test_dir, card1.id, "done")
        archived = manager.archive_card(test_dir, card1.id)
        assert archived
        print(f"✓ Card {card1.id} moved to done and archived")

        # Verify card2 is no longer blocked
        blocked_after = manager.get_blocked_cards(test_dir)
        assert len(blocked_after) == 0
        print("✓ Card 2 no longer blocked (dependency resolved)")

        # Test 9: View archive
        print("\n--- Test 9: Archive View ---")
        archive_view = manager.get_archive_view(test_dir)
        print(archive_view)

        # Test 10: Delete card
        print("\n--- Test 10: Delete Card ---")
        deleted = manager.delete_card(test_dir, card3.id)
        assert deleted
        print(f"✓ Card {card3.id} deleted")

        # Final board view (compact)
        print("\n--- Final Board State (Compact) ---")
        final_view = manager.get_board_view(test_dir)
        print(final_view)

        # Test 11: Full graphical show view
        print("\n--- Test 11: Full Graphical Show View ---")
        # Add some more cards for a better demo
        manager.add_card(
            working_dir=test_dir,
            title="API Endpoints implementieren",
            column="in_progress",
            priority="high",
            tags=["backend", "api"],
            detail_content="## API Endpoints\n\n- GET /users\n- POST /users\n- PUT /users/:id\n- DELETE /users/:id\n\n### Authentication\nJWT Token required"
        )
        manager.add_card(
            working_dir=test_dir,
            title="Unit Tests schreiben",
            column="backlog",
            priority="medium",
            depends_on=[card2.id],
            tags=["testing"]
        )
        manager.add_card(
            working_dir=test_dir,
            title="Setup erledigt",
            column="done",
            priority="low"
        )

        full_view = manager.get_full_board_view(test_dir)
        print(full_view)

        # Verify file structure
        print("\n--- File Structure ---")
        claude_dir = Path(test_dir) / ".claude"
        kanban_file = claude_dir / "kanban.yaml"
        cards_dir = claude_dir / "cards"
        archive_file = claude_dir / "archive.yaml"

        print(f"  .claude/kanban.yaml: {'✓' if kanban_file.exists() else '✗'}")
        print(f"  .claude/cards/: {'✓' if cards_dir.exists() else '✗'}")
        print(f"  .claude/archive.yaml: {'✓' if archive_file.exists() else '✗'}")

        if cards_dir.exists():
            card_files = list(cards_dir.glob("*.md"))
            print(f"  Card files: {len(card_files)}")

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return True

    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        print(f"\n🧹 Cleaned up test directory")


if __name__ == "__main__":
    success = test_kanban_system()
    sys.exit(0 if success else 1)
