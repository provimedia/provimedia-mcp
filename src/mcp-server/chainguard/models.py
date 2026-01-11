"""
CHAINGUARD MCP Server - Models Module

Contains: ScopeDefinition, ProjectState

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.
"""

import json
import fnmatch
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

from .config import (
    CONFIG, MAX_RECENT_ACTIONS, MAX_OUT_OF_SCOPE_FILES,
    MAX_CHANGED_FILES, DB_SCHEMA_CHECK_TTL, DB_SCHEMA_PATTERNS,
    TaskMode, get_mode_features
)


@dataclass
class ScopeDefinition:
    """
    Defines the scope boundaries for a development task.
    """
    description: str = ""
    modules: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    checklist: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ProjectState:
    """
    Represents the complete state of a tracked project.
    """
    project_id: str
    project_name: str
    project_path: str
    phase: str = "unknown"
    current_task: str = ""

    # Counters
    files_changed: int = 0
    files_since_validation: int = 0
    validations_passed: int = 0
    validations_failed: int = 0

    # Timestamps
    last_validation: str = ""
    last_activity: str = ""
    session_start: str = ""

    # Core features
    scope: Optional[ScopeDefinition] = None
    criteria_status: Dict[str, bool] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    out_of_scope_files: List[str] = field(default_factory=list)
    checklist_results: Dict[str, bool] = field(default_factory=dict)

    # Compact log
    recent_actions: List[str] = field(default_factory=list)

    # HTTP Testing
    http_base_url: str = ""
    http_credentials: Dict[str, str] = field(default_factory=dict)
    http_tests_performed: int = 0  # v4.13: Track HTTP tests for finish warning

    # Impact-Check
    changed_files: List[str] = field(default_factory=list)
    impact_check_pending: bool = False

    # Test Runner (v4.10)
    test_config: Dict[str, Any] = field(default_factory=dict)   # {command, args, timeout}
    test_results: Dict[str, Any] = field(default_factory=dict)  # Letztes Ergebnis
    last_test_run: str = ""
    tests_passed: int = 0
    tests_failed: int = 0

    # Database Inspector (v4.12)
    db_config: Dict[str, Any] = field(default_factory=dict)  # {host, port, database, db_type, connected}
    # v4.18: Changed from bool to timestamp for TTL-based validation
    db_schema_checked_at: str = ""  # ISO timestamp when schema was last checked

    # Task Mode System (v5.0)
    task_mode: str = "programming"  # programming, content, devops, research, generic

    # Content Mode Data (v5.0)
    word_count_total: int = 0
    chapter_status: Dict[str, str] = field(default_factory=dict)  # {chapter: status}

    # DevOps Mode Data (v5.0)
    command_history: List[Dict[str, Any]] = field(default_factory=list)  # [{ts, cmd, result, output}]
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)  # [{name, ts, files}]

    # Research Mode Data (v5.0)
    sources: List[Dict[str, Any]] = field(default_factory=list)  # [{url, title, relevance}]
    facts: List[Dict[str, Any]] = field(default_factory=list)  # [{fact, source, confidence}]

    # Symbol Validation Warnings (v6.4.1) - collected during session, shown at finish
    symbol_warnings: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectState":
        if "scope" in data and data["scope"]:
            data["scope"] = ScopeDefinition(**data["scope"])

        # Migration from old format
        if "files_modified" in data and isinstance(data["files_modified"], list):
            data["files_changed"] = len(data["files_modified"])
            del data["files_modified"]

        # Remove deprecated fields
        deprecated = [
            "progress_log", "files_since_last_test", "validation_history",
            "todos_completed", "expected_state", "learnings",
            "file_dependencies", "_log_written_index"
        ]
        for key in deprecated:
            data.pop(key, None)

        # v4.18: Migrate db_schema_checked (bool) → db_schema_checked_at (timestamp)
        if "db_schema_checked" in data:
            old_value = data.pop("db_schema_checked")
            # If it was True, set a timestamp (though it's likely stale now)
            if old_value is True:
                data["db_schema_checked_at"] = datetime.now().isoformat()
            else:
                data["db_schema_checked_at"] = ""

        # Defaults for new fields
        defaults = {
            "files_changed": 0, "files_since_validation": 0,
            "validations_passed": 0, "validations_failed": 0,
            "recent_actions": [], "criteria_status": {},
            "out_of_scope_files": [], "checklist_results": {},
            "http_base_url": "", "http_credentials": {}, "http_tests_performed": 0,
            "changed_files": [], "impact_check_pending": False,
            # Test Runner (v4.10)
            "test_config": {}, "test_results": {},
            "last_test_run": "", "tests_passed": 0, "tests_failed": 0,
            # Database Inspector (v4.12, v4.18: timestamp statt bool)
            "db_config": {},
            "db_schema_checked_at": "",
            # Task Mode System (v5.0)
            "task_mode": "programming",
            "word_count_total": 0,
            "chapter_status": {},
            "command_history": [],
            "checkpoints": [],
            "sources": [],
            "facts": [],
            # Symbol Validation (v6.4.1)
            "symbol_warnings": []
        }
        for key, value in defaults.items():
            data.setdefault(key, value)

        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}

        return cls(**filtered_data)

    def needs_validation(self) -> bool:
        return self.files_since_validation >= CONFIG.validation_reminder_threshold

    def is_schema_checked(self) -> bool:
        """
        v4.18: Check if schema was checked and is still valid (within TTL).
        Returns True if schema was checked within DB_SCHEMA_CHECK_TTL seconds.
        """
        if not self.db_schema_checked_at:
            return False
        try:
            checked_at = datetime.fromisoformat(self.db_schema_checked_at)
            age_seconds = (datetime.now() - checked_at).total_seconds()
            return age_seconds < DB_SCHEMA_CHECK_TTL
        except (ValueError, TypeError):
            return False

    def get_schema_check_age(self) -> int:
        """Get age of schema check in seconds, or -1 if never checked."""
        if not self.db_schema_checked_at:
            return -1
        try:
            checked_at = datetime.fromisoformat(self.db_schema_checked_at)
            return int((datetime.now() - checked_at).total_seconds())
        except (ValueError, TypeError):
            return -1

    def invalidate_schema_check(self) -> bool:
        """
        v4.18: Invalidate schema check. Called when .sql files are modified.
        Returns True if schema was previously checked (and is now invalidated).
        """
        was_checked = bool(self.db_schema_checked_at)
        self.db_schema_checked_at = ""
        return was_checked

    def set_schema_checked(self):
        """v4.18: Mark schema as checked with current timestamp."""
        self.db_schema_checked_at = datetime.now().isoformat()

    @staticmethod
    def is_schema_file(file_path: str) -> bool:
        """v4.18: Check if a file is a schema-related file."""
        if not file_path:
            return False
        file_lower = file_path.lower()
        return any(pattern in file_lower for pattern in DB_SCHEMA_PATTERNS)

    def check_file_in_scope(self, file_path: str) -> bool:
        """Check if file matches scope patterns."""
        if not self.scope or not self.scope.modules:
            return True

        for pattern in self.scope.modules:
            if fnmatch.fnmatch(file_path, pattern):
                return True
            if file_path.endswith(pattern) or pattern in file_path:
                return True
        return False

    def add_action(self, action: str):
        """Add to recent actions - keeps only last MAX_RECENT_ACTIONS."""
        self.recent_actions.append(f"{datetime.now().strftime('%H:%M')} {action}")
        if len(self.recent_actions) > MAX_RECENT_ACTIONS:
            self.recent_actions = self.recent_actions[-MAX_RECENT_ACTIONS:]

    def get_status_line(self) -> str:
        """Ultra-compact one-line status."""
        flags = []
        if not self.scope:
            flags.append("!SCOPE")
        if self.needs_validation():
            flags.append(f"V!{self.files_since_validation}")
        if self.out_of_scope_files:
            flags.append(f"OOS:{len(self.out_of_scope_files)}")
        if any(not a.get("ack") for a in self.alerts):
            flags.append(f"A:{len([a for a in self.alerts if not a.get('ack')])}")

        flag_str = f" [{','.join(flags)}]" if flags else ""
        scope_preview = (
            self.scope.description[:35] + "..."
            if self.scope and len(self.scope.description) > 35
            else (self.scope.description if self.scope else "no scope")
        )

        return f"{self.project_name}|{self.phase[:4]}|F{self.files_changed}/V{self.files_since_validation}{flag_str} {scope_preview}"

    def get_completion_status(self) -> Dict[str, Any]:
        """Check if all requirements for task completion are fulfilled."""
        issues = []

        # 1. Check acceptance criteria
        if self.scope and self.scope.acceptance_criteria:
            unfulfilled = [c for c in self.scope.acceptance_criteria
                           if not self.criteria_status.get(c)]
            if unfulfilled:
                issues.append({
                    "type": "criteria",
                    "message": f"{len(unfulfilled)} Kriterien nicht erfüllt",
                    "details": unfulfilled[:3]
                })

        # 2. Check checklist
        if self.scope and self.scope.checklist:
            failed = [k for k, v in self.checklist_results.items() if v == "✗"]
            not_run = len(self.scope.checklist) - len(self.checklist_results)
            if failed:
                issues.append({
                    "type": "checklist",
                    "message": f"{len(failed)} Checks fehlgeschlagen",
                    "details": failed
                })
            if not_run > 0:
                issues.append({
                    "type": "checklist_pending",
                    "message": f"{not_run} Checks nicht ausgeführt"
                })

        # 3. Check open alerts
        open_alerts = [a for a in self.alerts if not a.get("ack")]
        if open_alerts:
            # v4.16: Check for blocking alerts (e.g. LOGIN_REQUIRED)
            blocking_alerts = [a for a in open_alerts if a.get("blocking")]
            if blocking_alerts:
                issues.append({
                    "type": "blocking_alert",
                    "message": f"{len(blocking_alerts)} blockierende Alerts",
                    "details": [a["msg"][:40] for a in blocking_alerts],
                    "blocking": True  # Cannot be bypassed with force=true!
                })
            else:
                issues.append({
                    "type": "alerts",
                    "message": f"{len(open_alerts)} offene Alerts",
                    "details": [a["msg"][:30] for a in open_alerts[:2]]
                })

        # 4. Check syntax errors in alerts
        syntax_alerts = [a for a in self.alerts if not a.get("ack") and "errors" in a]
        if syntax_alerts:
            issues.append({
                "type": "syntax",
                "message": "Syntax-Fehler nicht behoben"
            })

        # 5. v4.13: Check HTTP tests for web projects
        http_test_warning = self._check_http_test_needed()
        if http_test_warning:
            issues.append(http_test_warning)

        # 6. v6.4.5: Check symbol warnings (potential hallucinations)
        if self.symbol_warnings:
            issues.append({
                "type": "symbol_warnings",
                "message": f"{len(self.symbol_warnings)} potenzielle Halluzinationen",
                "details": self.symbol_warnings[:3],
                "blocking": False  # Can be bypassed with force=true
            })

        criteria_total = len(self.scope.acceptance_criteria) if self.scope and self.scope.acceptance_criteria else 0
        criteria_done = sum(
            1 for c in (self.scope.acceptance_criteria if self.scope and self.scope.acceptance_criteria else [])
            if self.criteria_status.get(c)
        )

        return {
            "complete": len(issues) == 0,
            "issues": issues,
            "criteria_done": criteria_done,
            "criteria_total": criteria_total
        }

    def add_changed_file(self, file_name: str):
        """Track a changed file for impact analysis."""
        if file_name not in self.changed_files:
            self.changed_files.append(file_name)
            if len(self.changed_files) > MAX_CHANGED_FILES:
                self.changed_files = self.changed_files[-MAX_CHANGED_FILES:]

    def add_out_of_scope_file(self, file_path: str):
        """Track an out-of-scope file."""
        if file_path not in self.out_of_scope_files:
            self.out_of_scope_files.append(file_path)
            if len(self.out_of_scope_files) > MAX_OUT_OF_SCOPE_FILES:
                self.out_of_scope_files = self.out_of_scope_files[-MAX_OUT_OF_SCOPE_FILES:]

    def _check_http_test_needed(self) -> Optional[Dict[str, Any]]:
        """
        v4.15.1: Check if HTTP tests should have been performed.

        BLOCKING (not just warning) if web files were changed without HTTP tests.

        Returns a blocking issue if:
        1. ANY PHP/JS/TS file was changed but no HTTP tests were performed
        2. Base-URL is set but no tests performed
        3. v4.15.1: Scope modules contain web file patterns

        Returns None if no issue (tests were done or no web files changed).
        """
        # Web file extensions that REQUIRE HTTP testing
        WEB_EXTENSIONS = {'.php', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.twig', '.blade.php'}

        # Skip if HTTP tests were already performed
        if self.http_tests_performed > 0:
            return None

        # Check 1: Base-URL set but no tests - BLOCKING
        if self.http_base_url:
            return {
                "type": "http_test",
                "blocking": True,
                "message": "HTTP-Tests PFLICHT: Base-URL gesetzt aber keine Endpoints getestet",
                "details": [f"Base-URL: {self.http_base_url[:40]}"]
            }

        # Check 2: ANY web file changed - BLOCKING
        web_files_changed = []
        for file_name in self.changed_files:
            file_lower = file_name.lower()
            for ext in WEB_EXTENSIONS:
                if file_lower.endswith(ext):
                    web_files_changed.append(file_name)
                    break

        if web_files_changed:  # v4.15: ANY web file triggers requirement
            return {
                "type": "http_test",
                "blocking": True,
                "message": f"HTTP-Tests PFLICHT: {len(web_files_changed)} Web-Datei(en) geändert",
                "details": web_files_changed[:5]
            }

        # v4.15.1: Check 3 - Fallback: Parse recent_actions for web files
        # This catches cases where changed_files list was not properly populated
        if self.files_changed > 0 and self.recent_actions:
            web_files_from_actions = []
            for action in self.recent_actions:
                # Actions look like: "14:30 edit: user-edit.php" or "14:30 BATCH(3): edit"
                action_lower = action.lower()
                for ext in WEB_EXTENSIONS:
                    if ext in action_lower:
                        # Extract filename from action
                        parts = action.split(': ')
                        if len(parts) >= 2:
                            filename = parts[-1].strip()
                            if filename not in web_files_from_actions:
                                web_files_from_actions.append(filename)
                        break
            if web_files_from_actions:
                return {
                    "type": "http_test",
                    "blocking": True,
                    "message": f"HTTP-Tests PFLICHT: Web-Dateien bearbeitet (aus Actions)",
                    "details": web_files_from_actions[:5]
                }

        # v4.15.1: Check 4 - Scope modules contain web patterns
        if self.scope and self.scope.modules:
            web_modules = []
            for module in self.scope.modules:
                module_lower = module.lower()
                for ext in WEB_EXTENSIONS:
                    if ext in module_lower or module_lower.endswith(ext.replace('.', '')):
                        web_modules.append(module)
                        break
            if web_modules and self.files_changed > 0:
                return {
                    "type": "http_test",
                    "blocking": False,  # Warning, not blocking (since we can't confirm files)
                    "message": f"HTTP-Tests empfohlen: Scope enthält Web-Module",
                    "details": web_modules[:3]
                }

        return None

    # =========================================================================
    # Task Mode System (v5.0)
    # =========================================================================

    def get_task_mode(self) -> TaskMode:
        """Get the current task mode as TaskMode enum."""
        return TaskMode.from_string(self.task_mode)

    def get_features(self):
        """Get ModeFeatures for the current task mode."""
        return get_mode_features(self.get_task_mode())

    def is_http_test_required(self) -> bool:
        """
        v5.0: Check if HTTP tests are required based on task mode.
        Only PROGRAMMING mode enforces HTTP tests for web files.
        """
        features = self.get_features()
        if not features.http_testing:
            return False  # HTTP testing not required for this mode

        # Only check web files in programming mode
        if self.task_mode != "programming":
            return False

        # Delegate to existing logic
        return self._check_http_test_needed() is not None

    def add_command(self, cmd: str, result: str = "success", output: str = ""):
        """
        v5.0: Log a command execution (DevOps mode).
        Keeps last 50 commands.
        """
        self.command_history.append({
            "ts": datetime.now().isoformat(),
            "cmd": cmd,
            "result": result,
            "output": output[:500] if output else ""
        })
        if len(self.command_history) > 50:
            self.command_history = self.command_history[-50:]

    def add_checkpoint(self, name: str, files: List[str] = None):
        """
        v5.0: Create a rollback checkpoint (DevOps mode).
        Keeps last 10 checkpoints.
        """
        self.checkpoints.append({
            "name": name,
            "ts": datetime.now().isoformat(),
            "files": files or []
        })
        if len(self.checkpoints) > 10:
            self.checkpoints = self.checkpoints[-10:]

    def add_source(self, url: str, title: str = "", relevance: str = "medium"):
        """
        v5.0: Track a research source (Research mode).
        Keeps last 100 sources.
        """
        self.sources.append({
            "url": url,
            "title": title,
            "relevance": relevance,  # high, medium, low
            "ts": datetime.now().isoformat()
        })
        if len(self.sources) > 100:
            self.sources = self.sources[-100:]

    def add_fact(self, fact: str, source: str = "", confidence: str = "likely"):
        """
        v5.0: Index a discovered fact (Research mode).
        Keeps last 200 facts.
        """
        self.facts.append({
            "fact": fact,
            "source": source,
            "confidence": confidence,  # verified, likely, uncertain
            "ts": datetime.now().isoformat()
        })
        if len(self.facts) > 200:
            self.facts = self.facts[-200:]

    def update_word_count(self, count: int):
        """v5.0: Update total word count (Content mode)."""
        self.word_count_total = count

    def set_chapter_status(self, chapter: str, status: str):
        """
        v5.0: Set chapter status (Content mode).
        status: draft, review, done
        """
        self.chapter_status[chapter] = status

    def get_mode_status_line(self) -> str:
        """
        v5.0: Get mode-specific status information.
        Returns additional info based on task mode.
        """
        mode = self.get_task_mode()

        if mode == TaskMode.CONTENT:
            chapters_done = sum(1 for s in self.chapter_status.values() if s == "done")
            chapters_total = len(self.chapter_status) or "?"
            return f"📝 {self.word_count_total} words | {chapters_done}/{chapters_total} chapters"

        elif mode == TaskMode.DEVOPS:
            cmds = len(self.command_history)
            checkpoints = len(self.checkpoints)
            return f"🖥️ {cmds} cmds | {checkpoints} checkpoints"

        elif mode == TaskMode.RESEARCH:
            return f"🔬 {len(self.sources)} sources | {len(self.facts)} facts"

        elif mode == TaskMode.GENERIC:
            return f"⚡ {self.files_changed} tracked"

        # PROGRAMMING mode - default
        return ""
