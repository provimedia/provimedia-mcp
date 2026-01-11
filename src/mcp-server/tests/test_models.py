"""
Tests for chainguard.models module.

Tests ScopeDefinition and ProjectState functionality.
"""

import json
import pytest
from chainguard.models import ScopeDefinition, ProjectState


class TestScopeDefinition:
    """Tests for ScopeDefinition dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        scope = ScopeDefinition()
        assert scope.description == ""
        assert scope.modules == []
        assert scope.acceptance_criteria == []
        assert scope.checklist == []
        assert scope.created_at == ""

    def test_with_values(self):
        """Test creating scope with values."""
        scope = ScopeDefinition(
            description="Test task",
            modules=["src/*.py"],
            acceptance_criteria=["Tests pass", "Docs updated"],
            created_at="2024-01-01T00:00:00"
        )
        assert scope.description == "Test task"
        assert len(scope.modules) == 1
        assert len(scope.acceptance_criteria) == 2


class TestProjectState:
    """Tests for ProjectState dataclass."""

    def test_default_values(self):
        """Test default values for required fields."""
        state = ProjectState(
            project_id="test123",
            project_name="TestProject",
            project_path="/tmp/test"
        )
        assert state.project_id == "test123"
        assert state.phase == "unknown"
        assert state.files_changed == 0
        assert state.scope is None
        assert state.test_config == {}
        assert state.test_results == {}

    def test_to_json(self):
        """Test JSON serialization."""
        state = ProjectState(
            project_id="test123",
            project_name="TestProject",
            project_path="/tmp/test"
        )
        json_str = state.to_json()
        data = json.loads(json_str)

        assert data["project_id"] == "test123"
        assert data["project_name"] == "TestProject"
        assert data["phase"] == "unknown"

    def test_from_dict_basic(self):
        """Test creating from dictionary."""
        data = {
            "project_id": "abc123",
            "project_name": "MyProject",
            "project_path": "/home/user/project",
            "phase": "implementation",
            "files_changed": 5
        }
        state = ProjectState.from_dict(data)

        assert state.project_id == "abc123"
        assert state.project_name == "MyProject"
        assert state.phase == "implementation"
        assert state.files_changed == 5

    def test_from_dict_with_scope(self):
        """Test from_dict with nested scope."""
        data = {
            "project_id": "abc123",
            "project_name": "MyProject",
            "project_path": "/tmp",
            "scope": {
                "description": "Test scope",
                "modules": ["*.py"],
                "acceptance_criteria": ["Done"],
                "checklist": [],
                "created_at": "2024-01-01"
            }
        }
        state = ProjectState.from_dict(data)

        assert state.scope is not None
        assert state.scope.description == "Test scope"
        assert state.scope.modules == ["*.py"]

    def test_from_dict_removes_deprecated(self):
        """Test that deprecated fields are removed."""
        data = {
            "project_id": "abc123",
            "project_name": "MyProject",
            "project_path": "/tmp",
            "progress_log": ["old", "data"],  # Deprecated
            "learnings": {"old": "stuff"},     # Deprecated
        }
        state = ProjectState.from_dict(data)

        # Should not raise and deprecated fields ignored
        assert state.project_id == "abc123"

    def test_from_dict_adds_defaults(self):
        """Test that missing fields get defaults."""
        data = {
            "project_id": "abc123",
            "project_name": "MyProject",
            "project_path": "/tmp"
        }
        state = ProjectState.from_dict(data)

        assert state.files_changed == 0
        assert state.test_config == {}
        assert state.criteria_status == {}

    def test_needs_validation(self):
        """Test needs_validation threshold check."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.files_since_validation = 5
        assert not state.needs_validation()  # Default threshold is 8

        state.files_since_validation = 10
        assert state.needs_validation()

    def test_check_file_in_scope_no_scope(self):
        """Test check_file_in_scope when no scope defined."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        # No scope means all files are in scope
        assert state.check_file_in_scope("any/file.py") is True

    def test_check_file_in_scope_with_patterns(self):
        """Test check_file_in_scope with module patterns."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(
            description="Test",
            modules=["src/*.py", "tests/"]
        )

        assert state.check_file_in_scope("src/main.py") is True
        assert state.check_file_in_scope("tests/test_main.py") is True
        assert state.check_file_in_scope("docs/readme.md") is False

    def test_add_action(self):
        """Test adding actions to recent_actions."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.add_action("EDIT: file.py")
        state.add_action("TEST: passed")

        assert len(state.recent_actions) == 2
        assert "EDIT: file.py" in state.recent_actions[0]
        assert "TEST: passed" in state.recent_actions[1]

    def test_add_action_limit(self):
        """Test that recent_actions is limited."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        # Add more than MAX_RECENT_ACTIONS (5)
        for i in range(10):
            state.add_action(f"action_{i}")

        assert len(state.recent_actions) <= 5

    def test_get_status_line(self):
        """Test status line generation."""
        state = ProjectState(
            project_id="test",
            project_name="TestProject",
            project_path="/tmp",
            phase="implementation",
            files_changed=3
        )
        state.scope = ScopeDefinition(description="Build feature X")

        status = state.get_status_line()

        assert "TestProject" in status
        assert "impl" in status
        assert "Build feature X" in status

    def test_get_completion_status_complete(self):
        """Test completion status when all criteria met."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(
            description="Test",
            acceptance_criteria=["Done"]
        )
        state.criteria_status = {"Done": True}

        status = state.get_completion_status()
        assert status["complete"] is True
        assert status["criteria_done"] == 1
        assert status["criteria_total"] == 1

    def test_get_completion_status_incomplete(self):
        """Test completion status with unfulfilled criteria."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(
            description="Test",
            acceptance_criteria=["Task 1", "Task 2"]
        )
        state.criteria_status = {"Task 1": True}

        status = state.get_completion_status()
        assert status["complete"] is False
        assert status["criteria_done"] == 1
        assert status["criteria_total"] == 2
        assert len(status["issues"]) > 0

    def test_get_completion_status_with_symbol_warnings(self):
        """Test completion status with symbol warnings (v6.4.5)."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(
            description="Test",
            acceptance_criteria=["Done"]
        )
        state.criteria_status = {"Done": True}
        state.symbol_warnings = ["unknownFunc() - Line 42", "fakeMethod() - Line 99"]

        status = state.get_completion_status()
        # Should be incomplete due to symbol warnings
        assert status["complete"] is False
        assert len(status["issues"]) == 1
        assert status["issues"][0]["type"] == "symbol_warnings"
        assert status["issues"][0]["blocking"] is False
        assert "2 potenzielle Halluzinationen" in status["issues"][0]["message"]

    def test_get_completion_status_no_symbol_warnings(self):
        """Test completion status without symbol warnings."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(
            description="Test",
            acceptance_criteria=["Done"]
        )
        state.criteria_status = {"Done": True}
        state.symbol_warnings = []  # No warnings

        status = state.get_completion_status()
        assert status["complete"] is True
        assert len(status["issues"]) == 0

    def test_add_changed_file(self):
        """Test tracking changed files."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.add_changed_file("file1.py")
        state.add_changed_file("file2.py")
        state.add_changed_file("file1.py")  # Duplicate

        assert len(state.changed_files) == 2

    def test_add_out_of_scope_file(self):
        """Test tracking out-of-scope files."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.add_out_of_scope_file("/other/file.py")

        assert len(state.out_of_scope_files) == 1
        assert "/other/file.py" in state.out_of_scope_files

    def test_roundtrip_serialization(self):
        """Test that state survives JSON roundtrip."""
        original = ProjectState(
            project_id="test123",
            project_name="TestProject",
            project_path="/tmp/test",
            phase="testing",
            files_changed=10,
            test_config={"command": "pytest"},
            tests_passed=5,
            tests_failed=1
        )
        original.scope = ScopeDefinition(
            description="Important task",
            modules=["src/"],
            acceptance_criteria=["Tests pass"]
        )

        # Serialize and deserialize
        json_str = original.to_json()
        data = json.loads(json_str)
        restored = ProjectState.from_dict(data)

        assert restored.project_id == original.project_id
        assert restored.phase == original.phase
        assert restored.files_changed == original.files_changed
        assert restored.test_config == original.test_config
        assert restored.tests_passed == original.tests_passed
        assert restored.scope.description == original.scope.description


class TestHTTPTestWarning:
    """Tests for v4.15 HTTP test BLOCKING in get_completion_status."""

    def test_no_warning_when_http_tests_performed(self):
        """No warning if HTTP tests were already performed."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(description="Test", acceptance_criteria=["Done"])
        state.criteria_status = {"Done": True}
        state.http_base_url = "http://localhost:8080"
        state.http_tests_performed = 3  # Tests were performed

        status = state.get_completion_status()
        http_issues = [i for i in status["issues"] if i.get("type") == "http_test"]
        assert len(http_issues) == 0

    def test_blocking_when_base_url_set_no_tests(self):
        """BLOCKING (not just warning) if Base-URL set but no HTTP tests."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(description="Test", acceptance_criteria=["Done"])
        state.criteria_status = {"Done": True}
        state.http_base_url = "http://localhost:8080"
        state.http_tests_performed = 0  # No tests

        status = state.get_completion_status()
        http_issues = [i for i in status["issues"] if i.get("type") == "http_test"]
        assert len(http_issues) == 1
        assert "PFLICHT" in http_issues[0]["message"]
        assert http_issues[0].get("blocking") is True  # v4.15: Must be blocking

    def test_blocking_when_web_files_changed_no_tests(self):
        """BLOCKING if web files changed but no HTTP tests."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(description="Test", acceptance_criteria=["Done"])
        state.criteria_status = {"Done": True}
        state.changed_files = ["UserController.php", "login.php", "app.js"]
        state.http_tests_performed = 0

        status = state.get_completion_status()
        http_issues = [i for i in status["issues"] if i.get("type") == "http_test"]
        assert len(http_issues) == 1
        assert "Web-Datei" in http_issues[0]["message"]
        assert http_issues[0].get("blocking") is True  # v4.15: Must be blocking

    def test_blocking_single_web_file(self):
        """v4.15: BLOCKING even for single web file change (no more threshold)."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(description="Test", acceptance_criteria=["Done"])
        state.criteria_status = {"Done": True}
        state.changed_files = ["single.php"]  # Only one file - still blocks!
        state.http_tests_performed = 0

        status = state.get_completion_status()
        http_issues = [i for i in status["issues"] if i.get("type") == "http_test"]
        assert len(http_issues) == 1  # v4.15: Now blocks even for 1 file
        assert http_issues[0].get("blocking") is True

    def test_no_warning_non_web_files(self):
        """No warning for non-web files (Python, config, etc.)."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.scope = ScopeDefinition(description="Test", acceptance_criteria=["Done"])
        state.criteria_status = {"Done": True}
        state.changed_files = ["script.py", "config.yaml", "README.md"]
        state.http_tests_performed = 0

        status = state.get_completion_status()
        http_issues = [i for i in status["issues"] if i.get("type") == "http_test"]
        assert len(http_issues) == 0

    def test_http_tests_performed_default(self):
        """Test that http_tests_performed defaults to 0."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        assert state.http_tests_performed == 0

    def test_http_tests_performed_from_dict(self):
        """Test that http_tests_performed is restored from dict."""
        data = {
            "project_id": "test",
            "project_name": "Test",
            "project_path": "/tmp",
            "http_tests_performed": 5
        }
        state = ProjectState.from_dict(data)
        assert state.http_tests_performed == 5

    def test_http_tests_performed_migration(self):
        """Test that old states without http_tests_performed get default."""
        data = {
            "project_id": "test",
            "project_name": "Test",
            "project_path": "/tmp"
            # No http_tests_performed field
        }
        state = ProjectState.from_dict(data)
        assert state.http_tests_performed == 0


class TestSchemaCheckInvalidation:
    """Tests for v4.18 Schema Check Invalidation with TTL."""

    def test_is_schema_checked_empty(self):
        """Test is_schema_checked returns False when never checked."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        assert state.is_schema_checked() is False
        assert state.get_schema_check_age() == -1

    def test_set_schema_checked(self):
        """Test set_schema_checked sets timestamp."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.set_schema_checked()

        assert state.db_schema_checked_at != ""
        assert state.is_schema_checked() is True
        assert state.get_schema_check_age() >= 0
        assert state.get_schema_check_age() < 5  # Should be very recent

    def test_invalidate_schema_check(self):
        """Test invalidate_schema_check clears timestamp."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.set_schema_checked()
        assert state.is_schema_checked() is True

        was_checked = state.invalidate_schema_check()
        assert was_checked is True
        assert state.is_schema_checked() is False
        assert state.db_schema_checked_at == ""

    def test_invalidate_schema_check_when_not_checked(self):
        """Test invalidate_schema_check returns False when not checked."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        was_checked = state.invalidate_schema_check()
        assert was_checked is False

    def test_is_schema_file_sql(self):
        """Test is_schema_file detects .sql files."""
        assert ProjectState.is_schema_file("migrations/001_create_users.sql") is True
        assert ProjectState.is_schema_file("schema.sql") is True
        assert ProjectState.is_schema_file("database/seeds/users.sql") is True

    def test_is_schema_file_migration(self):
        """Test is_schema_file detects migration files."""
        assert ProjectState.is_schema_file("migrations/2024_01_01_create_users.php") is True
        assert ProjectState.is_schema_file("database/migrations/create_table.php") is True
        assert ProjectState.is_schema_file("migrate.py") is True

    def test_is_schema_file_negative(self):
        """Test is_schema_file returns False for non-schema files."""
        assert ProjectState.is_schema_file("app/Controllers/UserController.php") is False
        assert ProjectState.is_schema_file("index.html") is False
        assert ProjectState.is_schema_file("main.py") is False
        assert ProjectState.is_schema_file("") is False

    def test_schema_check_ttl_expired(self):
        """Test is_schema_checked returns False for expired timestamp."""
        from datetime import datetime, timedelta

        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        # Set timestamp 15 minutes in the past (TTL is 10 min)
        old_time = datetime.now() - timedelta(minutes=15)
        state.db_schema_checked_at = old_time.isoformat()

        assert state.is_schema_checked() is False
        assert state.get_schema_check_age() > 600  # More than 10 min

    def test_schema_check_within_ttl(self):
        """Test is_schema_checked returns True within TTL."""
        from datetime import datetime, timedelta

        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        # Set timestamp 5 minutes in the past (TTL is 10 min)
        recent_time = datetime.now() - timedelta(minutes=5)
        state.db_schema_checked_at = recent_time.isoformat()

        assert state.is_schema_checked() is True
        assert 290 < state.get_schema_check_age() < 310  # Around 5 minutes

    def test_db_schema_checked_migration(self):
        """Test migration from old db_schema_checked (bool) to db_schema_checked_at (timestamp)."""
        # Old format with boolean True
        data = {
            "project_id": "test",
            "project_name": "Test",
            "project_path": "/tmp",
            "db_schema_checked": True
        }
        state = ProjectState.from_dict(data)
        assert state.db_schema_checked_at != ""
        assert state.is_schema_checked() is True

        # Old format with boolean False
        data2 = {
            "project_id": "test",
            "project_name": "Test",
            "project_path": "/tmp",
            "db_schema_checked": False
        }
        state2 = ProjectState.from_dict(data2)
        assert state2.db_schema_checked_at == ""
        assert state2.is_schema_checked() is False

    def test_db_schema_checked_at_default(self):
        """Test that new states default to empty db_schema_checked_at."""
        data = {
            "project_id": "test",
            "project_name": "Test",
            "project_path": "/tmp"
        }
        state = ProjectState.from_dict(data)
        assert state.db_schema_checked_at == ""
        assert state.is_schema_checked() is False

    def test_invalid_timestamp_handling(self):
        """Test handling of invalid timestamp values."""
        state = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        state.db_schema_checked_at = "invalid-timestamp"

        assert state.is_schema_checked() is False
        assert state.get_schema_check_age() == -1

    def test_roundtrip_with_schema_timestamp(self):
        """Test JSON roundtrip preserves db_schema_checked_at."""
        original = ProjectState(
            project_id="test",
            project_name="Test",
            project_path="/tmp"
        )
        original.set_schema_checked()
        original_ts = original.db_schema_checked_at

        # Roundtrip
        json_str = original.to_json()
        data = json.loads(json_str)
        restored = ProjectState.from_dict(data)

        assert restored.db_schema_checked_at == original_ts
        assert restored.is_schema_checked() is True
