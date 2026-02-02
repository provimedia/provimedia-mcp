"""
Tests for v6.6 Enhanced Long-Term Memory Auto-Integration.

Tests memory health in set_scope, reindex in finish, comprehensive refresh,
and status memory indicator.
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, Any, List

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


# =============================================================================
# Test Helpers
# =============================================================================

def _make_mock_state(
    project_path="/tmp/test-project",
    project_name="test-project",
    phase="implementation",
    changed_files=None,
    recent_actions=None,
    task_mode="programming",
    acceptance_criteria=None,
    criteria_status=None,
):
    """Create a mock ProjectState for testing."""
    state = MagicMock()
    state.project_path = project_path
    state.project_name = project_name
    state.phase = phase
    state.changed_files = changed_files or []
    state.recent_actions = recent_actions or []
    state.task_mode = task_mode
    state.get_task_mode.return_value = task_mode
    state.alerts = []
    state.files_changed = len(changed_files) if changed_files else 0
    state.files_since_validation = 0
    state.validations_passed = 0
    state.validations_failed = 0
    state.symbol_warnings = []
    state.criteria_status = criteria_status or {}

    # Scope
    if acceptance_criteria is not None:
        scope = MagicMock()
        scope.description = "Test task"
        scope.acceptance_criteria = acceptance_criteria
        scope.modules = []
        scope.checklist = []
        state.scope = scope
    else:
        scope = MagicMock()
        scope.description = "Test task"
        scope.acceptance_criteria = []
        scope.modules = []
        scope.checklist = []
        state.scope = scope

    return state


# =============================================================================
# TestGetMemoryStatusInfo
# =============================================================================

class TestGetMemoryStatusInfo:
    """Tests for _get_memory_status_info helper."""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_memory_disabled(self):
        """Should return safe defaults when MEMORY_AVAILABLE is False."""
        from chainguard.handlers import _get_memory_status_info
        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            result = await _get_memory_status_info(state)

        assert result["initialized"] is False
        assert result["total_docs"] == 0
        assert result["stale"] is False
        assert result["days_since_update"] == -1

    @pytest.mark.asyncio
    async def test_returns_health_when_memory_available(self):
        """Should return health data when memory is available."""
        from chainguard.handlers import _get_memory_status_info

        state = _make_mock_state()
        mock_health = {
            "initialized": True,
            "total_docs": 150,
            "last_updated": "2026-01-15T10:00:00",
            "stale": False,
            "days_since_update": 5,
        }

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.get_project_id", return_value="test123"):
            mock_ci.get_memory_health = AsyncMock(return_value=mock_health)
            result = await _get_memory_status_info(state)

        assert result["initialized"] is True
        assert result["total_docs"] == 150
        assert result["stale"] is False

    @pytest.mark.asyncio
    async def test_staleness_detection(self):
        """Should detect stale memory (>30 days)."""
        from chainguard.handlers import _get_memory_status_info

        state = _make_mock_state()
        mock_health = {
            "initialized": True,
            "total_docs": 50,
            "last_updated": "2025-11-01T10:00:00",
            "stale": True,
            "days_since_update": 60,
        }

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.get_project_id", return_value="test123"):
            mock_ci.get_memory_health = AsyncMock(return_value=mock_health)
            result = await _get_memory_status_info(state)

        assert result["stale"] is True
        assert result["days_since_update"] == 60

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Should return safe defaults on exception."""
        from chainguard.handlers import _get_memory_status_info

        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", side_effect=Exception("test error")):
            result = await _get_memory_status_info(state)

        assert result["initialized"] is False
        assert result["total_docs"] == 0


# =============================================================================
# TestReindexChangedFiles
# =============================================================================

class TestReindexChangedFiles:
    """Tests for _reindex_changed_files helper."""

    @pytest.mark.asyncio
    async def test_basic_reindex(self):
        """Should reindex changed files and return stats."""
        from chainguard.handlers import _reindex_changed_files

        state = _make_mock_state(changed_files=["file1.py", "file2.py"])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update:
            mock_mm.memory_exists = AsyncMock(return_value=True)
            result = await _reindex_changed_files(state)

        assert result["files_reindexed"] == 2
        assert mock_update.call_count == 2

    @pytest.mark.asyncio
    async def test_disabled_memory(self):
        """Should return zeros when memory disabled."""
        from chainguard.handlers import _reindex_changed_files

        state = _make_mock_state(changed_files=["file1.py"])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            result = await _reindex_changed_files(state)

        assert result["files_reindexed"] == 0
        assert result["summaries_updated"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_error_per_file(self):
        """Should count errors per file but continue processing."""
        from chainguard.handlers import _reindex_changed_files

        state = _make_mock_state(changed_files=["file1.py", "file2.py", "file3.py"])

        call_count = 0

        async def failing_update(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Simulated error")

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._update_memory_for_file", side_effect=failing_update):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            result = await _reindex_changed_files(state)

        assert result["files_reindexed"] == 2  # 2 succeeded
        assert result["errors"] == 1  # 1 failed

    @pytest.mark.asyncio
    async def test_max_20_cap(self):
        """Should cap reindexing at 20 files."""
        from chainguard.handlers import _reindex_changed_files

        state = _make_mock_state(changed_files=[f"file{i}.py" for i in range(30)])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update:
            mock_mm.memory_exists = AsyncMock(return_value=True)
            result = await _reindex_changed_files(state)

        assert mock_update.call_count == 20
        assert result["files_reindexed"] == 20


# =============================================================================
# TestComprehensiveMemoryRefresh
# =============================================================================

class TestComprehensiveMemoryRefresh:
    """Tests for _trigger_comprehensive_memory_refresh helper."""

    @pytest.mark.asyncio
    async def test_under_threshold(self):
        """Should skip refresh when under threshold."""
        from chainguard.handlers import _trigger_comprehensive_memory_refresh

        state = _make_mock_state(changed_files=["a.py", "b.py"], recent_actions=[])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True):
            result = await _trigger_comprehensive_memory_refresh(state, ["a.py", "b.py"])

        assert result["refresh_triggered"] is False
        assert result["architecture_updated"] is False

    @pytest.mark.asyncio
    async def test_threshold_met_by_file_count(self):
        """Should trigger refresh when >= 10 files changed."""
        from chainguard.handlers import _trigger_comprehensive_memory_refresh

        files = [f"file{i}.py" for i in range(12)]
        state = _make_mock_state(changed_files=files, recent_actions=[])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.context_injector") as mock_ci:
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_memory = AsyncMock()
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_ci.invalidate_cache = MagicMock()

            # Mock architecture detector
            with patch("chainguard.handlers.architecture_detector", create=True) as mock_arch:
                mock_analysis = MagicMock()
                mock_analysis.pattern.value = "mvc"
                mock_analysis.framework = MagicMock()
                mock_analysis.framework.value = "django"
                mock_analysis.detected_layers = ["models", "views"]
                mock_analysis.detected_patterns = ["repository"]
                mock_analysis.confidence = 0.8

                # Patch the import inside the function
                with patch.dict("sys.modules", {"chainguard.architecture": MagicMock(architecture_detector=MagicMock(analyze=MagicMock(return_value=mock_analysis)))}):
                    result = await _trigger_comprehensive_memory_refresh(state, files)

        assert result["refresh_triggered"] is True

    @pytest.mark.asyncio
    async def test_threshold_met_by_new_files(self):
        """Should trigger refresh when new files are created."""
        from chainguard.handlers import _trigger_comprehensive_memory_refresh

        state = _make_mock_state(
            changed_files=["new.py", "other.py"],
            recent_actions=["14:30 create: new.py", "14:31 edit: other.py"]
        )

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.context_injector") as mock_ci:
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_memory = AsyncMock()
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_ci.invalidate_cache = MagicMock()

            result = await _trigger_comprehensive_memory_refresh(state, ["new.py", "other.py"])

        assert result["refresh_triggered"] is True

    @pytest.mark.asyncio
    async def test_disabled_memory(self):
        """Should return defaults when memory disabled."""
        from chainguard.handlers import _trigger_comprehensive_memory_refresh

        files = [f"file{i}.py" for i in range(15)]
        state = _make_mock_state(changed_files=files, recent_actions=[])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            result = await _trigger_comprehensive_memory_refresh(state, files)

        assert result["refresh_triggered"] is False

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Should handle errors gracefully."""
        from chainguard.handlers import _trigger_comprehensive_memory_refresh

        files = [f"file{i}.py" for i in range(12)]
        state = _make_mock_state(changed_files=files, recent_actions=[])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", side_effect=Exception("test")):
            result = await _trigger_comprehensive_memory_refresh(state, files)

        # Should not crash, refresh was triggered but failed
        assert result["refresh_triggered"] is True


# =============================================================================
# TestSetScopeMemoryBriefing
# =============================================================================

class TestSetScopeMemoryBriefing:
    """Tests for memory health display in set_scope."""

    @pytest.mark.asyncio
    async def test_memory_status_in_xml_response(self):
        """Should include memory_status in XML set_scope response."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state()
        mock_health = {
            "initialized": True,
            "total_docs": 100,
            "last_updated": "2026-01-20T10:00:00",
            "stale": False,
            "days_since_update": 5,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, return_value=mock_health), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": "/tmp/test-project"
            })

        assert len(result) > 0
        text = result[0].text
        assert "memory_status" in text or "total_docs" in text or "100" in text

    @pytest.mark.asyncio
    async def test_stale_memory_warning(self):
        """Should show warning when memory is stale."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state()
        mock_health = {
            "initialized": True,
            "total_docs": 50,
            "last_updated": "2025-11-01T10:00:00",
            "stale": True,
            "days_since_update": 60,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, return_value=mock_health), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": "/tmp/test-project"
            })

        text = result[0].text
        assert "memory_warning" in text or "veraltet" in text or "memory_init" in text

    @pytest.mark.asyncio
    async def test_memory_disabled_no_status(self):
        """Should not include memory info when disabled."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state()

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": "/tmp/test-project"
            })

        text = result[0].text
        assert "memory_status" not in text

    @pytest.mark.asyncio
    async def test_memory_error_graceful(self):
        """Should handle memory errors gracefully in set_scope."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state()

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, side_effect=Exception("test")), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            # Should not raise
            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": "/tmp/test-project"
            })

        assert len(result) > 0  # Response was still generated


# =============================================================================
# TestFinishMemoryConsolidation
# =============================================================================

class TestFinishMemoryConsolidation:
    """Tests for enhanced memory consolidation in finish."""

    @pytest.mark.asyncio
    async def test_richer_learning_content(self):
        """Should store richer learning content with mode and outcome."""
        from chainguard.handlers import _consolidate_session_learnings

        state = _make_mock_state(
            changed_files=["file1.py", "file2.py"],
            acceptance_criteria=["Criterion A", "Criterion B"],
            criteria_status={"Criterion A": True, "Criterion B": False},
        )

        mock_memory = AsyncMock()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._reindex_changed_files", new_callable=AsyncMock, return_value={"files_reindexed": 0, "summaries_updated": 0, "errors": 0}), \
             patch("chainguard.handlers._trigger_comprehensive_memory_refresh", new_callable=AsyncMock, return_value={"refresh_triggered": False, "architecture_updated": False, "summaries_generated": 0}):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)

            stats = await _consolidate_session_learnings(state, "Build auth system")

        # Check that memory.add was called with richer content
        assert mock_memory.add.called
        call_args = mock_memory.add.call_args
        content = call_args.kwargs.get("content", "") or call_args[1].get("content", "")
        metadata = call_args.kwargs.get("metadata", {}) or call_args[1].get("metadata", {})

        assert "Mode:" in content
        assert "Outcome:" in content
        assert metadata.get("task_mode") == "programming"
        assert metadata.get("criteria_fulfilled") == 1
        assert metadata.get("criteria_total") == 2

    @pytest.mark.asyncio
    async def test_stats_return_value(self):
        """Should return stats dict instead of None."""
        from chainguard.handlers import _consolidate_session_learnings

        state = _make_mock_state(changed_files=["file1.py"])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._reindex_changed_files", new_callable=AsyncMock, return_value={"files_reindexed": 1, "summaries_updated": 0, "errors": 0}), \
             patch("chainguard.handlers._trigger_comprehensive_memory_refresh", new_callable=AsyncMock, return_value={"refresh_triggered": False, "architecture_updated": False, "summaries_generated": 0}):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=AsyncMock())

            stats = await _consolidate_session_learnings(state, "Test task")

        assert isinstance(stats, dict)
        assert stats["learning_stored"] is True
        assert stats["files_reindexed"] == 1

    @pytest.mark.asyncio
    async def test_reindex_called(self):
        """Should call _reindex_changed_files during consolidation."""
        from chainguard.handlers import _consolidate_session_learnings

        state = _make_mock_state(changed_files=["a.py", "b.py"])

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers._reindex_changed_files", new_callable=AsyncMock, return_value={"files_reindexed": 2, "summaries_updated": 0, "errors": 0}) as mock_reindex, \
             patch("chainguard.handlers._trigger_comprehensive_memory_refresh", new_callable=AsyncMock, return_value={"refresh_triggered": False, "architecture_updated": False, "summaries_generated": 0}):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=AsyncMock())

            await _consolidate_session_learnings(state, "Test task")

        mock_reindex.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_memory_stats_in_finish_response(self):
        """Should include memory_update in finish XML response."""
        from chainguard.handlers import handle_finish

        state = _make_mock_state(
            changed_files=["file1.py"],
            acceptance_criteria=["Done"],
            criteria_status={"Done": True},
        )
        state.get_completion_status.return_value = {
            "complete": True,
            "criteria_done": 1,
            "criteria_total": 1,
            "issues": [],
        }
        state.impact_check_pending = True
        state.checklist_results = {}

        memory_stats = {
            "learning_stored": True,
            "files_reindexed": 1,
            "summaries_updated": 0,
            "refresh_triggered": False,
            "architecture_updated": False,
            "errors": 0,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._consolidate_session_learnings", new_callable=AsyncMock, return_value=memory_stats):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_finish({
                "confirmed": True,
                "working_dir": "/tmp/test-project",
            })

        text = result[0].text
        assert "memory_update" in text or "files_reindexed" in text

    @pytest.mark.asyncio
    async def test_memory_disabled_returns_stats(self):
        """Should return empty stats when memory disabled."""
        from chainguard.handlers import _consolidate_session_learnings

        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            stats = await _consolidate_session_learnings(state, "Test task")

        assert isinstance(stats, dict)
        assert stats["learning_stored"] is False
        assert stats["files_reindexed"] == 0

    @pytest.mark.asyncio
    async def test_consolidation_error_handling(self):
        """Should handle errors gracefully and return stats."""
        from chainguard.handlers import _consolidate_session_learnings

        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.get_project_id", side_effect=Exception("fail")):
            stats = await _consolidate_session_learnings(state, "Test task")

        assert isinstance(stats, dict)
        assert stats["learning_stored"] is False


# =============================================================================
# TestStatusMemoryIndicator
# =============================================================================

class TestStatusMemoryIndicator:
    """Tests for memory indicator in status."""

    @pytest.mark.asyncio
    async def test_xml_memory_indicator(self):
        """Should include memory data in XML status response."""
        from chainguard.handlers import handle_status

        state = _make_mock_state()
        mock_health = {
            "initialized": True,
            "total_docs": 200,
            "last_updated": "2026-01-25T10:00:00",
            "stale": False,
            "days_since_update": 2,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, return_value=mock_health):
            mock_pm.get_async = AsyncMock(return_value=state)

            result = await handle_status({"working_dir": "/tmp/test-project"})

        text = result[0].text
        assert "memory" in text or "200" in text

    @pytest.mark.asyncio
    async def test_legacy_memory_indicator(self):
        """Should append memory info to legacy status line."""
        from chainguard.handlers import handle_status

        state = _make_mock_state()
        state.get_status_line.return_value = "test|impl|F3/V1 test"
        mock_health = {
            "initialized": True,
            "total_docs": 150,
            "last_updated": "2026-01-25T10:00:00",
            "stale": False,
            "days_since_update": 2,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", False), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, return_value=mock_health), \
             patch("chainguard.handlers._check_context", return_value=""):
            mock_pm.get_async = AsyncMock(return_value=state)

            result = await handle_status({"working_dir": "/tmp/test-project"})

        text = result[0].text
        assert "Mem:150docs" in text
        assert "2026-01-25" in text

    @pytest.mark.asyncio
    async def test_memory_disabled_no_indicator(self):
        """Should not include memory info when disabled."""
        from chainguard.handlers import handle_status

        state = _make_mock_state()

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)

            result = await handle_status({"working_dir": "/tmp/test-project"})

        text = result[0].text
        assert "memory" not in text.lower() or "mem:" not in text.lower()

    @pytest.mark.asyncio
    async def test_memory_not_initialized(self):
        """Should not show memory info when not initialized."""
        from chainguard.handlers import handle_status

        state = _make_mock_state()
        mock_health = {
            "initialized": False,
            "total_docs": 0,
            "last_updated": None,
            "stale": False,
            "days_since_update": -1,
        }

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers._get_memory_status_info", new_callable=AsyncMock, return_value=mock_health):
            mock_pm.get_async = AsyncMock(return_value=state)

            result = await handle_status({"working_dir": "/tmp/test-project"})

        text = result[0].text
        # Memory key should not appear when not initialized
        assert "\"memory\"" not in text


# =============================================================================
# TestGetMemoryHealth (in memory.py)
# =============================================================================

class TestGetMemoryHealth:
    """Tests for SmartContextInjector.get_memory_health() method."""

    @pytest.mark.asyncio
    async def test_not_initialized(self):
        """Should return defaults when memory not initialized."""
        from chainguard.memory import SmartContextInjector, ProjectMemoryManager

        mm = MagicMock(spec=ProjectMemoryManager)
        mm.memory_exists = AsyncMock(return_value=False)
        injector = SmartContextInjector(mm)

        result = await injector.get_memory_health("test123")

        assert result["initialized"] is False
        assert result["total_docs"] == 0

    @pytest.mark.asyncio
    async def test_fresh_memory(self):
        """Should report healthy memory with correct stats."""
        from chainguard.memory import SmartContextInjector, ProjectMemoryManager, MemoryStats

        mm = MagicMock(spec=ProjectMemoryManager)
        mm.memory_exists = AsyncMock(return_value=True)

        mock_memory = AsyncMock()
        mock_stats = MemoryStats(
            project_id="test123",
            initialized_at="2026-01-01T00:00:00",
            last_update=datetime.now().isoformat(),
            collections={"code_structure": 50, "functions": 100},
            total_documents=150,
            storage_size_mb=5.0,
        )
        mock_memory.get_stats = AsyncMock(return_value=mock_stats)
        mm.get_memory = AsyncMock(return_value=mock_memory)

        injector = SmartContextInjector(mm)
        result = await injector.get_memory_health("test123")

        assert result["initialized"] is True
        assert result["total_docs"] == 150
        assert result["stale"] is False
        assert result["days_since_update"] >= 0

    @pytest.mark.asyncio
    async def test_stale_memory(self):
        """Should detect stale memory (>30 days old)."""
        from chainguard.memory import SmartContextInjector, ProjectMemoryManager, MemoryStats

        mm = MagicMock(spec=ProjectMemoryManager)
        mm.memory_exists = AsyncMock(return_value=True)

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_memory = AsyncMock()
        mock_stats = MemoryStats(
            project_id="test123",
            initialized_at="2025-01-01T00:00:00",
            last_update=old_date,
            collections={"code_structure": 10},
            total_documents=10,
            storage_size_mb=1.0,
        )
        mock_memory.get_stats = AsyncMock(return_value=mock_stats)
        mm.get_memory = AsyncMock(return_value=mock_memory)

        injector = SmartContextInjector(mm)
        result = await injector.get_memory_health("test123")

        assert result["initialized"] is True
        assert result["stale"] is True
        assert result["days_since_update"] >= 30

    @pytest.mark.asyncio
    async def test_exception_returns_defaults(self):
        """Should return safe defaults on exception."""
        from chainguard.memory import SmartContextInjector, ProjectMemoryManager

        mm = MagicMock(spec=ProjectMemoryManager)
        mm.memory_exists = AsyncMock(side_effect=Exception("boom"))

        injector = SmartContextInjector(mm)
        result = await injector.get_memory_health("test123")

        assert result["initialized"] is False
        assert result["total_docs"] == 0
        assert result["stale"] is False


# =============================================================================
# TestDetectPrdFiles (v6.7)
# =============================================================================

class TestDetectPrdFiles:
    """Tests for _detect_prd_files helper."""

    def test_no_path(self):
        """Should return empty list when no project path given."""
        from chainguard.handlers import _detect_prd_files
        assert _detect_prd_files("") == []
        assert _detect_prd_files(None) == []

    def test_empty_dir(self, tmp_path):
        """Should return empty list when no PRD files found."""
        from chainguard.handlers import _detect_prd_files
        result = _detect_prd_files(str(tmp_path))
        assert result == []

    def test_root_prd(self, tmp_path):
        """Should find PRD.md in project root."""
        from chainguard.handlers import _detect_prd_files
        prd = tmp_path / "PRD.md"
        prd.write_text("# Product Requirements\nThis is the product spec for v2.0\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) == 1
        assert result[0]["path"] == "PRD.md"
        assert "product spec" in result[0]["summary"].lower()

    def test_docs_subdir(self, tmp_path):
        """Should find PRD in docs/ subdirectory."""
        from chainguard.handlers import _detect_prd_files
        docs = tmp_path / "docs"
        docs.mkdir()
        prd = docs / "REQUIREMENTS.md"
        prd.write_text("# Requirements\nAll features must be tested.\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) == 1
        assert result[0]["path"] == "docs/REQUIREMENTS.md"

    def test_multiple_capped(self, tmp_path):
        """Should cap results at PRD_MAX_DISPLAY (3)."""
        from chainguard.handlers import _detect_prd_files
        # Create 4 PRD files in different locations
        (tmp_path / "PRD.md").write_text("# PRD\nFirst\n")
        (tmp_path / "SPEC.md").write_text("# Spec\nSecond\n")
        (tmp_path / "REQUIREMENTS.md").write_text("# Req\nThird\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "PRD.md").write_text("# PRD\nFourth\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) <= 3

    def test_skip_headings(self, tmp_path):
        """Should skip heading lines and return first content line."""
        from chainguard.handlers import _detect_prd_files
        prd = tmp_path / "PRD.md"
        prd.write_text("# Title\n## Subtitle\nActual content here\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) == 1
        assert result[0]["summary"] == "Actual content here"

    def test_truncation(self, tmp_path):
        """Should truncate long summaries with ellipsis."""
        from chainguard.handlers import _detect_prd_files
        prd = tmp_path / "PRD.md"
        long_line = "A" * 200
        prd.write_text(f"# Title\n{long_line}\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) == 1
        assert result[0]["summary"].endswith("...")
        assert len(result[0]["summary"]) <= 84  # 80 + "..."

    def test_mod_date(self, tmp_path):
        """Should include modification date in YYYY-MM-DD format."""
        from chainguard.handlers import _detect_prd_files
        prd = tmp_path / "PRD.md"
        prd.write_text("# PRD\nContent\n")

        result = _detect_prd_files(str(tmp_path))
        assert len(result) == 1
        # Should be today's date in YYYY-MM-DD format
        assert len(result[0]["mod_date"]) == 10
        assert "-" in result[0]["mod_date"]

    def test_exception_returns_empty(self):
        """Should return empty list on any exception."""
        from chainguard.handlers import _detect_prd_files
        result = _detect_prd_files("/nonexistent/path/that/does/not/exist")
        assert result == []


# =============================================================================
# TestPrdInSetScope (v6.7)
# =============================================================================

class TestPrdInSetScope:
    """Tests for PRD detection in set_scope."""

    @pytest.mark.asyncio
    async def test_xml_with_prd(self, tmp_path):
        """Should include prd_detected in XML set_scope response."""
        from chainguard.handlers import handle_set_scope

        # Create a PRD file
        prd = tmp_path / "PRD.md"
        prd.write_text("# Product Requirements\nBuild a login system\n")

        state = _make_mock_state(project_path=str(tmp_path))

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": str(tmp_path)
            })

        text = result[0].text
        assert "prd_detected" in text
        assert "PRD.md" in text

    @pytest.mark.asyncio
    async def test_no_prd_no_section(self, tmp_path):
        """Should not include prd_detected when no PRD files exist."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state(project_path=str(tmp_path))

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": str(tmp_path)
            })

        text = result[0].text
        assert "prd_detected" not in text

    @pytest.mark.asyncio
    async def test_error_graceful(self):
        """Should handle PRD detection errors gracefully."""
        from chainguard.handlers import handle_set_scope

        state = _make_mock_state(project_path="/nonexistent/path")

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False), \
             patch("chainguard.handlers.KANBAN_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            # Should not raise
            result = await handle_set_scope({
                "description": "Test task",
                "working_dir": "/nonexistent/path"
            })

        assert len(result) > 0  # Response was still generated


# =============================================================================
# TestPrdInFinish (v6.7)
# =============================================================================

class TestPrdInFinish:
    """Tests for PRD reminder in finish."""

    @pytest.mark.asyncio
    async def test_reminder_above_threshold(self, tmp_path):
        """Should show PRD reminder when files_changed >= threshold."""
        from chainguard.handlers import handle_finish

        # Create a PRD file
        prd = tmp_path / "PRD.md"
        prd.write_text("# PRD\nRequirements doc\n")

        state = _make_mock_state(
            project_path=str(tmp_path),
            changed_files=["a.py", "b.py", "c.py", "d.py"],
            acceptance_criteria=["Done"],
            criteria_status={"Done": True},
        )
        state.files_changed = 5  # Above PRD_MIN_CHANGES_FOR_REMINDER (3)
        state.get_completion_status.return_value = {
            "complete": True,
            "criteria_done": 1,
            "criteria_total": 1,
            "issues": [],
        }
        state.impact_check_pending = True
        state.checklist_results = {}

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_finish({
                "confirmed": True,
                "working_dir": str(tmp_path),
            })

        text = result[0].text
        assert "prd_reminder" in text
        assert "PRD.md" in text

    @pytest.mark.asyncio
    async def test_no_reminder_below_threshold(self, tmp_path):
        """Should NOT show PRD reminder when files_changed < threshold."""
        from chainguard.handlers import handle_finish

        # Create a PRD file
        prd = tmp_path / "PRD.md"
        prd.write_text("# PRD\nRequirements doc\n")

        state = _make_mock_state(
            project_path=str(tmp_path),
            changed_files=["a.py"],
            acceptance_criteria=["Done"],
            criteria_status={"Done": True},
        )
        state.files_changed = 1  # Below PRD_MIN_CHANGES_FOR_REMINDER (3)
        state.get_completion_status.return_value = {
            "complete": True,
            "criteria_done": 1,
            "criteria_total": 1,
            "issues": [],
        }
        state.impact_check_pending = True
        state.checklist_results = {}

        with patch("chainguard.handlers.pm") as mock_pm, \
             patch("chainguard.handlers.XML_RESPONSES_ENABLED", True), \
             patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            mock_pm.get_async = AsyncMock(return_value=state)
            mock_pm.save_async = AsyncMock()

            result = await handle_finish({
                "confirmed": True,
                "working_dir": str(tmp_path),
            })

        text = result[0].text
        assert "prd_reminder" not in text


# =============================================================================
# TestAutoRefreshStaleMemory (v6.8)
# =============================================================================

class TestAutoRefreshStaleMemory:
    """Tests for _auto_refresh_stale_memory helper."""

    @pytest.mark.asyncio
    async def test_disabled_when_memory_unavailable(self):
        """Should skip when MEMORY_AVAILABLE is False."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", False):
            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is False
        assert result["skipped_reason"] == "memory_unavailable"

    @pytest.mark.asyncio
    async def test_disabled_when_config_off(self):
        """Should skip when AUTO_REFRESH_STALE_MEMORY is False."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", False):
            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is False
        assert result["skipped_reason"] == "auto_refresh_disabled"

    @pytest.mark.asyncio
    async def test_skips_uninitialized_memory(self):
        """Should skip when memory is not initialized for the project."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm:
            mock_mm.memory_exists = AsyncMock(return_value=False)
            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is False
        assert result["skipped_reason"] == "memory_not_initialized"

    @pytest.mark.asyncio
    async def test_git_based_refresh(self):
        """Should find changed files via git and re-index them."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {
            "last_update": old_date,
            "include_patterns": ["**/*.py", "**/*.js"],
        }

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)
        mock_memory.save_metadata = AsyncMock()

        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "src/app.py\nsrc/utils.js\n\nsrc/app.py\n"

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 30), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update, \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.should_index_file", return_value=True):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result
            mock_ci.invalidate_cache = MagicMock()

            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is True
        assert result["method"] == "git"
        assert result["files_found"] == 2  # deduplicated: app.py + utils.js
        assert result["files_processed"] == 2
        assert mock_update.call_count == 2
        mock_memory.save_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_mtime_fallback(self, tmp_path):
        """Should fall back to mtime when git is not available."""
        from chainguard.handlers import _auto_refresh_stale_memory

        # Create test files with recent mtime
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("print('hello')")

        state = _make_mock_state(project_path=str(tmp_path))

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {
            "last_update": old_date,
            "include_patterns": ["**/*.py"],
        }

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)
        mock_memory.save_metadata = AsyncMock()

        # Git fails
        mock_git_result = MagicMock()
        mock_git_result.returncode = 1
        mock_git_result.stdout = ""

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 30), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update, \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.should_index_file", return_value=True):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result
            mock_ci.invalidate_cache = MagicMock()

            result = await _auto_refresh_stale_memory(state)

        assert result["method"] == "mtime"
        assert result["files_found"] >= 1
        assert result["refreshed"] is True

    @pytest.mark.asyncio
    async def test_caps_at_max_files(self):
        """Should cap processing at STALE_MEMORY_MAX_FILES."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {"last_update": old_date, "include_patterns": ["**/*.py"]}

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)
        mock_memory.save_metadata = AsyncMock()

        # Git returns 50 files
        files = "\n".join([f"file{i}.py" for i in range(50)])
        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = files

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 10), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update, \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.should_index_file", return_value=True):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result
            mock_ci.invalidate_cache = MagicMock()

            result = await _auto_refresh_stale_memory(state)

        assert result["files_processed"] <= 10
        assert mock_update.call_count <= 10

    @pytest.mark.asyncio
    async def test_handles_individual_file_errors(self):
        """Should continue processing even when individual files fail."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {"last_update": old_date, "include_patterns": ["**/*.py"]}

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)
        mock_memory.save_metadata = AsyncMock()

        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "a.py\nb.py\nc.py\n"

        call_count = 0

        async def failing_on_second(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Simulated error")

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 30), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess, \
             patch("chainguard.handlers._update_memory_for_file", side_effect=failing_on_second) as mock_update, \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.should_index_file", return_value=True):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result
            mock_ci.invalidate_cache = MagicMock()

            result = await _auto_refresh_stale_memory(state)

        assert result["files_processed"] == 2  # 2 succeeded
        assert result["errors"] == 1  # 1 failed
        assert result["refreshed"] is True  # Still counts as refreshed

    @pytest.mark.asyncio
    async def test_filters_non_matching_extensions(self):
        """Should only process files matching valid extensions."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {"last_update": old_date, "include_patterns": ["**/*.py"]}

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)
        mock_memory.save_metadata = AsyncMock()

        # Git returns mixed file types
        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "app.py\nstyle.css\nimage.png\nutils.py\n"

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 30), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess, \
             patch("chainguard.handlers._update_memory_for_file", new_callable=AsyncMock) as mock_update, \
             patch("chainguard.handlers.context_injector") as mock_ci, \
             patch("chainguard.handlers.should_index_file", return_value=True):
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result
            mock_ci.invalidate_cache = MagicMock()

            result = await _auto_refresh_stale_memory(state)

        # Only .py files should be processed
        assert result["files_found"] == 2
        assert result["files_processed"] == 2

    @pytest.mark.asyncio
    async def test_no_changed_files(self):
        """Should handle case where no files have changed."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        old_date = (datetime.now() - timedelta(days=45)).isoformat()
        mock_metadata = {"last_update": old_date, "include_patterns": ["**/*.py"]}

        mock_memory = AsyncMock()
        mock_memory.get_metadata = AsyncMock(return_value=mock_metadata)

        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = ""

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.STALE_MEMORY_THRESHOLD_DAYS", 30), \
             patch("chainguard.handlers.STALE_MEMORY_MAX_FILES", 30), \
             patch("chainguard.handlers.get_project_id", return_value="test123"), \
             patch("chainguard.handlers.memory_manager") as mock_mm, \
             patch("chainguard.handlers.subprocess") as mock_subprocess:
            mock_mm.memory_exists = AsyncMock(return_value=True)
            mock_mm.get_memory = AsyncMock(return_value=mock_memory)
            mock_subprocess.run.return_value = mock_git_result

            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is False
        assert result["files_found"] == 0
        assert result["skipped_reason"] == "no_changed_files"

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Should not propagate exceptions - set_scope must not break."""
        from chainguard.handlers import _auto_refresh_stale_memory
        state = _make_mock_state()

        with patch("chainguard.handlers.MEMORY_AVAILABLE", True), \
             patch("chainguard.handlers.AUTO_REFRESH_STALE_MEMORY", True), \
             patch("chainguard.handlers.get_project_id", side_effect=Exception("boom")):
            # Should NOT raise
            result = await _auto_refresh_stale_memory(state)

        assert result["refreshed"] is False
        assert "exception" in result["skipped_reason"]
