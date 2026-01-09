"""
Tests for chainguard.handlers module.

Tests HandlerRegistry and individual handler functions.
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dataclasses import dataclass

# Mock TextContent before importing handlers
@dataclass
class MockTextContent:
    """Mock for mcp.types.TextContent."""
    type: str
    text: str

# Patch mcp.types before import
mock_mcp_types = MagicMock()
mock_mcp_types.TextContent = MockTextContent
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.types'] = mock_mcp_types

from chainguard.handlers import (
    HandlerRegistry,
    handler,
    _text,
    _check_context,
    handle_set_scope,
    handle_track,
    handle_track_batch,
    handle_status,
    handle_context,
    handle_set_phase,
    handle_run_checklist,
    handle_check_criteria,
    handle_validate,
    handle_alert,
    handle_clear_alerts,
    handle_projects,
    handle_config,
    handle_finish,
    handle_test_config,
    handle_run_tests,
    handle_test_status,
    handle_recall,
    handle_history,
    handle_learn,
)
from chainguard.models import ScopeDefinition, ProjectState
from chainguard.config import CONTEXT_MARKER, CONTEXT_REFRESH_TEXT

# Patch TextContent in the handlers module
import chainguard.handlers as handlers_module
handlers_module.TextContent = MockTextContent


# =============================================================================
# XML/PlainText Response Helpers
# =============================================================================

def is_blocked_response(text: str) -> bool:
    """Check if response indicates blocked status (XML or plain text)."""
    return "<status>blocked</status>" in text or "BLOCKIERT" in text


def is_success_response(text: str) -> bool:
    """Check if response indicates success (XML or plain text)."""
    return "<status>success</status>" in text or "✓" in text


def is_error_response(text: str) -> bool:
    """Check if response indicates error (XML or plain text)."""
    return "<status>error</status>" in text or "✗" in text


def has_scope_info(text: str) -> bool:
    """Check if response contains scope information."""
    return "<scope>" in text or "Scope:" in text


def has_criteria_count(text: str, count: int) -> bool:
    """Check if response contains criteria count."""
    return f"<criteria_count>{count}</criteria_count>" in text or f"Criteria: {count}" in text


def has_long_desc_warning(text: str) -> bool:
    """Check if response contains long description warning."""
    return (
        "<type>description_too_long</type>" in text  # XML mode
        or "<desc_warning>" in text  # Alternative XML format
        or "Description lang" in text  # Plain text mode
    )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_state():
    """Create a mock ProjectState for testing."""
    state = ProjectState(
        project_id="test-project-123",
        project_name="TestProject",
        project_path="/tmp/test-project"
    )
    state.scope = ScopeDefinition(
        description="Test task",
        modules=["src/*.py"],
        acceptance_criteria=["Tests pass", "Docs updated"],
        created_at="2024-01-01T00:00:00"
    )
    state.phase = "implementation"
    return state


@pytest.fixture
def mock_state_no_scope():
    """Create a mock ProjectState without scope."""
    return ProjectState(
        project_id="test-project-456",
        project_name="NoScopeProject",
        project_path="/tmp/no-scope"
    )


@pytest.fixture
def mock_pm(mock_state):
    """Create a mock project_manager."""
    pm_mock = AsyncMock()
    pm_mock.get_async = AsyncMock(return_value=mock_state)
    pm_mock.save_async = AsyncMock()
    return pm_mock


# =============================================================================
# Test HandlerRegistry
# =============================================================================

class TestHandlerRegistry:
    """Tests for HandlerRegistry class."""

    def test_register_decorator(self):
        """Test that register decorator adds handler to registry."""
        # Clear existing for isolation
        original_handlers = HandlerRegistry._handlers.copy()

        @HandlerRegistry.register("test_handler_xyz")
        async def test_handler(args):
            return _text("test response")

        assert "test_handler_xyz" in HandlerRegistry._handlers
        assert HandlerRegistry._handlers["test_handler_xyz"] == test_handler

        # Cleanup
        del HandlerRegistry._handlers["test_handler_xyz"]

    def test_list_handlers(self):
        """Test listing all registered handlers."""
        handlers = HandlerRegistry.list_handlers()

        # Should include core handlers
        assert "chainguard_set_scope" in handlers
        assert "chainguard_track" in handlers
        assert "chainguard_status" in handlers
        assert "chainguard_validate" in handlers

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler(self, mock_state):
        """Test that dispatch calls the correct handler."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await HandlerRegistry.dispatch(
                "chainguard_status",
                {"working_dir": "/tmp/test", "ctx": CONTEXT_MARKER}
            )

            assert len(result) == 1
            assert result[0].type == "text"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_handler(self, mock_state):
        """Test dispatch with unknown handler name."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await HandlerRegistry.dispatch(
                "chainguard_nonexistent",
                {"working_dir": "/tmp"}
            )

            assert "Unknown" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_blocks_without_scope(self, mock_state_no_scope):
        """Test that dispatch blocks tools when no scope is set."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)

            # chainguard_track should be blocked without scope
            result = await HandlerRegistry.dispatch(
                "chainguard_track",
                {"working_dir": "/tmp", "file": "test.py"}
            )

            assert is_blocked_response(result[0].text)

    @pytest.mark.asyncio
    async def test_dispatch_allows_set_scope_without_scope(self, mock_state_no_scope):
        """Test that set_scope is allowed even without existing scope."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)
            pm_mock.save_async = AsyncMock()

            result = await HandlerRegistry.dispatch(
                "chainguard_set_scope",
                {"working_dir": "/tmp", "description": "New scope"}
            )

            # Should succeed, not be blocked
            assert not is_blocked_response(result[0].text)
            assert has_scope_info(result[0].text)


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_text_creates_text_content(self):
        """Test _text creates proper TextContent list."""
        result = _text("Hello World")

        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "Hello World"

    def test_check_context_with_marker(self):
        """Test context check with correct marker."""
        result = _check_context({"ctx": CONTEXT_MARKER})
        assert result == ""

    def test_check_context_without_marker(self):
        """Test context check without marker returns refresh text."""
        result = _check_context({})
        assert result == CONTEXT_REFRESH_TEXT

    def test_check_context_wrong_marker(self):
        """Test context check with wrong marker."""
        result = _check_context({"ctx": "wrong"})
        assert result == CONTEXT_REFRESH_TEXT


# =============================================================================
# Test Core Handlers
# =============================================================================

class TestHandleSetScope:
    """Tests for handle_set_scope handler."""

    @pytest.mark.asyncio
    async def test_set_scope_basic(self, mock_state_no_scope):
        """Test basic scope setting."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)
            pm_mock.save_async = AsyncMock()

            result = await handle_set_scope({
                "working_dir": "/tmp",
                "description": "Implement feature X"
            })

            assert is_success_response(result[0].text)
            assert "Implement feature X" in result[0].text

    @pytest.mark.asyncio
    async def test_set_scope_with_criteria(self, mock_state_no_scope):
        """Test scope setting with acceptance criteria."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)
            pm_mock.save_async = AsyncMock()

            result = await handle_set_scope({
                "working_dir": "/tmp",
                "description": "Test task",
                "acceptance_criteria": ["Done", "Tested"],
                "modules": ["src/"]
            })

            assert has_criteria_count(result[0].text, 2)

    @pytest.mark.asyncio
    async def test_set_scope_long_description_warning(self, mock_state_no_scope):
        """Test warning for long descriptions."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)
            pm_mock.save_async = AsyncMock()

            long_desc = "A" * 600  # Over 500 char limit
            result = await handle_set_scope({
                "working_dir": "/tmp",
                "description": long_desc
            })

            assert has_long_desc_warning(result[0].text)


class TestHandleTrack:
    """Tests for handle_track handler."""

    @pytest.mark.asyncio
    async def test_track_file_basic(self, mock_state):
        """Test basic file tracking."""
        # Ensure file is in scope
        mock_state.scope = ScopeDefinition(
            description="Test",
            modules=["src/"]  # All src files in scope
        )

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                sv_mock.validate_file = AsyncMock(return_value={"valid": True, "errors": []})

                with patch('chainguard.handlers.HistoryManager') as hm_mock:
                    hm_mock.log_change = AsyncMock()

                    with patch('chainguard.handlers.sanitize_path', return_value="src/test.py"):
                        result = await handle_track({
                            "working_dir": "/tmp",
                            "file": "src/test.py",
                            "action": "edit",
                            "ctx": CONTEXT_MARKER
                        })

                        # Should be silent on success with context marker (or validation msg)
                        assert "✗" not in result[0].text  # No errors

    @pytest.mark.asyncio
    async def test_track_file_syntax_error(self, mock_state):
        """Test tracking file with syntax error."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                sv_mock.validate_file = AsyncMock(return_value={
                    "valid": False,
                    "errors": [{"type": "PHP Syntax", "message": "Unexpected }"}]
                })

                with patch('chainguard.handlers.HistoryManager') as hm_mock:
                    hm_mock.log_change = AsyncMock()
                    hm_mock.index_error = AsyncMock()
                    hm_mock.find_similar_errors = AsyncMock(return_value=[])

                    result = await handle_track({
                        "working_dir": "/tmp",
                        "file": "test.php",
                        "ctx": CONTEXT_MARKER
                    })

                    assert is_error_response(result[0].text)
                    assert "PHP Syntax" in result[0].text

    @pytest.mark.asyncio
    async def test_track_file_out_of_scope(self, mock_state):
        """Test tracking file outside of scope."""
        mock_state.scope = ScopeDefinition(
            description="Test",
            modules=["src/"]
        )

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                sv_mock.validate_file = AsyncMock(return_value={"valid": True, "errors": []})

                with patch('chainguard.handlers.HistoryManager') as hm_mock:
                    hm_mock.log_change = AsyncMock()

                    # Patch sanitize_path to return the file as-is
                    with patch('chainguard.handlers.sanitize_path', return_value="docs/readme.md"):
                        result = await handle_track({
                            "working_dir": "/tmp",
                            "file": "docs/readme.md",
                            "ctx": CONTEXT_MARKER
                        })

                        assert "OOS" in result[0].text

    @pytest.mark.asyncio
    async def test_track_skip_validation(self, mock_state):
        """Test tracking with skip_validation flag."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                with patch('chainguard.handlers.HistoryManager') as hm_mock:
                    hm_mock.log_change = AsyncMock()

                    await handle_track({
                        "working_dir": "/tmp",
                        "file": "test.py",
                        "skip_validation": True,
                        "ctx": CONTEXT_MARKER
                    })

                    # Validator should not be called
                    sv_mock.validate_file.assert_not_called()


class TestHandleTrackBatch:
    """Tests for handle_track_batch handler."""

    @pytest.mark.asyncio
    async def test_track_batch_basic(self, mock_state):
        """Test batch file tracking."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                sv_mock.validate_file = AsyncMock(return_value={"valid": True, "errors": []})

                result = await handle_track_batch({
                    "working_dir": "/tmp",
                    "files": ["a.py", "b.py", "c.py"],
                    "action": "edit"
                })

                assert "3/3" in result[0].text or "tracked" in result[0].text

    @pytest.mark.asyncio
    async def test_track_batch_empty(self, mock_state):
        """Test batch tracking with no files."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_track_batch({
                "working_dir": "/tmp",
                "files": []
            })

            assert "No files" in result[0].text

    @pytest.mark.asyncio
    async def test_track_batch_with_errors(self, mock_state):
        """Test batch tracking with some validation errors."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.SyntaxValidator') as sv_mock:
                # First file valid, second invalid
                sv_mock.validate_file = AsyncMock(side_effect=[
                    {"valid": True, "errors": []},
                    {"valid": False, "errors": [{"type": "Syntax", "message": "Error"}]}
                ])

                result = await handle_track_batch({
                    "working_dir": "/tmp",
                    "files": ["good.py", "bad.py"]
                })

                assert "✗" in result[0].text


class TestHandleStatus:
    """Tests for handle_status handler."""

    @pytest.mark.asyncio
    async def test_status_basic(self, mock_state):
        """Test basic status output."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_status({
                "working_dir": "/tmp",
                "ctx": CONTEXT_MARKER
            })

            assert "TestProject" in result[0].text

    @pytest.mark.asyncio
    async def test_status_without_context_marker(self, mock_state):
        """Test status returns valid response when context marker missing."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_status({
                "working_dir": "/tmp"
            })

            # In XML mode: returns valid XML response
            # In plain text mode: includes context refresh text
            text = result[0].text
            is_valid = (
                "<chainguard" in text  # XML mode
                or CONTEXT_REFRESH_TEXT in text  # Plain text mode with refresh
            )
            assert is_valid


class TestHandleContext:
    """Tests for handle_context handler."""

    @pytest.mark.asyncio
    async def test_context_with_scope(self, mock_state):
        """Test full context output with scope."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_context({"working_dir": "/tmp"})

            assert "TestProject" in result[0].text
            # XML uses <scope> tag, plain text uses "Scope:"
            assert "<scope>" in result[0].text or "Scope" in result[0].text

    @pytest.mark.asyncio
    async def test_context_without_scope(self, mock_state_no_scope):
        """Test context shows warning when no scope."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)

            result = await handle_context({"working_dir": "/tmp"})

            assert "NO SCOPE" in result[0].text


class TestHandleSetPhase:
    """Tests for handle_set_phase handler."""

    @pytest.mark.asyncio
    async def test_set_phase_basic(self, mock_state):
        """Test setting phase."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_set_phase({
                "working_dir": "/tmp",
                "phase": "testing"
            })

            assert "testing" in result[0].text

    @pytest.mark.asyncio
    async def test_set_phase_done_with_incomplete_criteria(self, mock_state):
        """Test setting phase to done with incomplete criteria shows warning."""
        mock_state.criteria_status = {"Tests pass": True}  # Only 1 of 2 done

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_set_phase({
                "working_dir": "/tmp",
                "phase": "done"
            })

            assert "Warnung" in result[0].text or "⚠" in result[0].text


# =============================================================================
# Test Validation Handlers
# =============================================================================

class TestHandleCheckCriteria:
    """Tests for handle_check_criteria handler."""

    @pytest.mark.asyncio
    async def test_view_criteria(self, mock_state):
        """Test viewing criteria status."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_check_criteria({"working_dir": "/tmp"})

            assert "Tests pass" in result[0].text
            assert "Docs updated" in result[0].text

    @pytest.mark.asyncio
    async def test_mark_criterion_fulfilled(self, mock_state):
        """Test marking criterion as fulfilled."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_check_criteria({
                "working_dir": "/tmp",
                "criterion": "Tests pass",
                "fulfilled": True
            })

            # XML uses <fulfilled>true</fulfilled> or <status>success, plain text uses ✓
            text = result[0].text
            assert "<fulfilled>true</fulfilled>" in text or "✓" in text or is_success_response(text)

    @pytest.mark.asyncio
    async def test_no_criteria_defined(self, mock_state_no_scope):
        """Test when no criteria defined."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state_no_scope)

            result = await handle_check_criteria({"working_dir": "/tmp"})

            assert "No criteria" in result[0].text


class TestHandleValidate:
    """Tests for handle_validate handler."""

    @pytest.mark.asyncio
    async def test_validate_pass(self, mock_state):
        """Test passing validation."""
        mock_state.criteria_status = {"Tests pass": True, "Docs updated": True}

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_validate({
                "working_dir": "/tmp",
                "status": "PASS"
            })

            assert "PASS" in result[0].text

    @pytest.mark.asyncio
    async def test_validate_fail(self, mock_state):
        """Test failing validation."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_validate({
                "working_dir": "/tmp",
                "status": "FAIL",
                "note": "Tests failed"
            })

            assert "FAIL" in result[0].text
            assert mock_state.validations_failed == 1


class TestHandleRunChecklist:
    """Tests for handle_run_checklist handler."""

    @pytest.mark.asyncio
    async def test_run_checklist_no_checklist(self, mock_state):
        """Test when no checklist defined."""
        mock_state.scope.checklist = []

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_run_checklist({"working_dir": "/tmp"})

            assert "No checklist" in result[0].text

    @pytest.mark.asyncio
    async def test_run_checklist_with_items(self, mock_state):
        """Test running checklist with items."""
        mock_state.scope.checklist = [
            {"item": "File exists", "check": "test -f src/main.py"}
        ]

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.ChecklistRunner') as cr_mock:
                cr_mock.run_all_async = AsyncMock(return_value={
                    "passed": 1,
                    "total": 1,
                    "results": {"File exists": "✓"}
                })

                result = await handle_run_checklist({"working_dir": "/tmp"})

                assert "1/1" in result[0].text


# =============================================================================
# Test Alert Handlers
# =============================================================================

class TestHandleAlert:
    """Tests for handle_alert handler."""

    @pytest.mark.asyncio
    async def test_add_alert(self, mock_state):
        """Test adding an alert."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_alert({
                "working_dir": "/tmp",
                "message": "Something needs attention"
            })

            # XML uses <status>warning</status>, plain text uses ⚠
            text = result[0].text
            assert "<status>warning</status>" in text or "⚠" in text
            assert len(mock_state.alerts) == 1


class TestHandleClearAlerts:
    """Tests for handle_clear_alerts handler."""

    @pytest.mark.asyncio
    async def test_clear_alerts(self, mock_state):
        """Test clearing alerts."""
        mock_state.alerts = [
            {"msg": "Alert 1", "ack": False},
            {"msg": "Alert 2", "ack": False}
        ]

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_clear_alerts({"working_dir": "/tmp"})

            # XML uses <cleared_count>2</cleared_count>, plain text uses "2 alerts cleared"
            text = result[0].text
            assert "<cleared_count>2</cleared_count>" in text or "2 alerts cleared" in text
            assert all(a["ack"] for a in mock_state.alerts)


# =============================================================================
# Test Admin Handlers
# =============================================================================

class TestHandleProjects:
    """Tests for handle_projects handler."""

    @pytest.mark.asyncio
    async def test_list_projects_empty(self):
        """Test listing when no projects."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.list_all_projects_async = AsyncMock(return_value=[])

            result = await handle_projects({})

            assert "No projects" in result[0].text

    @pytest.mark.asyncio
    async def test_list_projects(self):
        """Test listing projects."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.list_all_projects_async = AsyncMock(return_value=[
                {"name": "Project1", "phase": "impl", "last": "10:00"},
                {"name": "Project2", "phase": "test", "last": "11:00"}
            ])

            result = await handle_projects({})

            assert "Project1" in result[0].text
            assert "Project2" in result[0].text


class TestHandleConfig:
    """Tests for handle_config handler."""

    @pytest.mark.asyncio
    async def test_view_config(self):
        """Test viewing config."""
        result = await handle_config({})

        assert "val_threshold" in result[0].text


# =============================================================================
# Test Finish Handler
# =============================================================================

class TestHandleFinish:
    """Tests for handle_finish handler."""

    @pytest.mark.asyncio
    async def test_finish_incomplete_blocked(self, mock_state):
        """Test finish blocked when criteria incomplete."""
        mock_state.criteria_status = {"Tests pass": True}  # Only 1 of 2

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_finish({"working_dir": "/tmp"})

            assert "Kann nicht abschließen" in result[0].text or "Offene Punkte" in result[0].text

    @pytest.mark.asyncio
    async def test_finish_with_force(self, mock_state):
        """Test finish with force flag."""
        mock_state.criteria_status = {}  # Nothing done
        mock_state.impact_check_pending = False

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_finish({
                "working_dir": "/tmp",
                "force": True,
                "confirmed": True
            })

            assert "erzwungen" in result[0].text or "abgeschlossen" in result[0].text


# =============================================================================
# Test Test Runner Handlers
# =============================================================================

class TestHandleTestConfig:
    """Tests for handle_test_config handler."""

    @pytest.mark.asyncio
    async def test_view_test_config_empty(self, mock_state):
        """Test viewing config when none set."""
        mock_state.test_config = {}

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_test_config({"working_dir": "/tmp"})

            assert "Kein Test-Command" in result[0].text

    @pytest.mark.asyncio
    async def test_set_test_config(self, mock_state):
        """Test setting test config."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            result = await handle_test_config({
                "working_dir": "/tmp",
                "command": "./vendor/bin/phpunit",
                "args": "tests/"
            })

            # v6.0: Support both XML and legacy responses
            assert "✓" in result[0].text or "<status>success</status>" in result[0].text
            assert "phpunit" in result[0].text


class TestHandleRunTests:
    """Tests for handle_run_tests handler."""

    @pytest.mark.asyncio
    async def test_run_tests_no_config(self, mock_state):
        """Test running tests without config."""
        mock_state.test_config = {}

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_run_tests({"working_dir": "/tmp"})

            assert "Kein Test-Command" in result[0].text

    @pytest.mark.asyncio
    async def test_run_tests_success(self, mock_state):
        """Test running tests successfully."""
        mock_state.test_config = {"command": "pytest", "args": "", "timeout": 300}

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.TestRunner') as tr_mock:
                from chainguard.test_runner import TestResult
                mock_result = TestResult(
                    success=True,
                    framework="pytest",
                    passed=10,
                    failed=0,
                    total=10,
                    duration=1.5,
                    error_lines=[]
                )
                tr_mock.run_async = AsyncMock(return_value=mock_result)
                tr_mock.format_result = MagicMock(return_value="✓ pytest: 10/10 passed")

                result = await handle_run_tests({"working_dir": "/tmp"})

                assert "10" in result[0].text or "passed" in result[0].text


class TestHandleTestStatus:
    """Tests for handle_test_status handler."""

    @pytest.mark.asyncio
    async def test_test_status_no_results(self, mock_state):
        """Test status when no tests run."""
        mock_state.test_results = {}

        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_test_status({"working_dir": "/tmp"})

            assert "Keine Tests" in result[0].text


# =============================================================================
# Test History Handlers
# =============================================================================

class TestHandleRecall:
    """Tests for handle_recall handler."""

    @pytest.mark.asyncio
    async def test_recall_no_query(self, mock_state):
        """Test recall without query."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_recall({
                "working_dir": "/tmp",
                "query": ""
            })

            assert "Query required" in result[0].text

    @pytest.mark.asyncio
    async def test_recall_no_results(self, mock_state):
        """Test recall with no matching results."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.HistoryManager') as hm_mock:
                hm_mock.recall = AsyncMock(return_value=[])

                result = await handle_recall({
                    "working_dir": "/tmp",
                    "query": "nonexistent error"
                })

                # v6.0: Support both XML (Eintraege) and legacy (Einträge)
                assert "Keine Einträge" in result[0].text or "Keine Eintraege" in result[0].text


class TestHandleHistory:
    """Tests for handle_history handler."""

    @pytest.mark.asyncio
    async def test_history_empty(self, mock_state):
        """Test history when empty."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            with patch('chainguard.handlers.HistoryManager') as hm_mock:
                hm_mock.get_history = AsyncMock(return_value=[])

                result = await handle_history({"working_dir": "/tmp"})

                assert "Keine History" in result[0].text


class TestHandleLearn:
    """Tests for handle_learn handler."""

    @pytest.mark.asyncio
    async def test_learn_no_resolution(self, mock_state):
        """Test learn without resolution."""
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)

            result = await handle_learn({
                "working_dir": "/tmp"
            })

            assert "resolution required" in result[0].text

    @pytest.mark.asyncio
    async def test_learn_success(self, mock_state):
        """Test successful learning with explicit file_pattern and error_type."""
        # When both file_pattern and error_type are provided, no need to look up recent errors
        with patch('chainguard.handlers.pm') as pm_mock:
            pm_mock.get_async = AsyncMock(return_value=mock_state)
            pm_mock.save_async = AsyncMock()

            with patch('chainguard.handlers.HistoryManager') as hm_mock:
                hm_mock.update_resolution = AsyncMock(return_value=True)

                result = await handle_learn({
                    "working_dir": "/tmp",
                    "resolution": "Missing semicolon",
                    "file_pattern": "*Controller.php",
                    "error_type": "PHP Syntax"
                })

                assert "✓" in result[0].text or "dokumentiert" in result[0].text
                hm_mock.update_resolution.assert_called_once()
