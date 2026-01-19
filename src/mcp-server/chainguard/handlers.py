"""
CHAINGUARD MCP Server - Tool Handlers Module

Handler-Registry Pattern for testability and maintainability.
Each handler is a separate function decorated with @handler.register().

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.
"""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Callable, Awaitable, Set

try:
    from mcp.types import TextContent
except ImportError:
    TextContent = None

from .config import (
    CONFIG, CONTEXT_MARKER, CONTEXT_REFRESH_TEXT,
    MAX_DESCRIPTION_LENGTH, MAX_OUT_OF_SCOPE_FILES,
    MAX_CHANGED_FILES, MAX_BATCH_FILES, DESCRIPTION_PREVIEW_LENGTH,
    SCOPE_REQUIRED_TOOLS, SCOPE_BLOCKED_TEXT,
    TaskMode, detect_task_mode, get_mode_context, get_mode_features,
    get_mode_context_xml,
    should_validate_syntax,
    XML_RESPONSES_ENABLED,
    TOON_ENABLED,
    MEMORY_ENABLED,
    SYMBOL_VALIDATION_AUTO,
    KANBAN_ENABLED,
    logger
)

# TOON Encoder (v6.0) - Token-Oriented Object Notation
from .toon import (
    encode_toon, toon_array, toon_files, toon_tables,
    toon_history, toon_projects, toon_criteria, toon_alerts
)

# XML Response System (v6.0)
from .xml_response import (
    xml_success, xml_error, xml_warning, xml_info, xml_blocked,
    build_context, ResponseStatus
)
from .models import ScopeDefinition
from .project_manager import project_manager as pm
from .validators import SyntaxValidator
from .symbol_validator import SymbolValidator, SymbolExtractor, SymbolValidationMode
from .symbol_patterns import detect_language
from .package_validator import PackageValidator, format_package_report
from .utils import sanitize_path, is_path_safe
from .checklist import ChecklistRunner
from .analyzers import CodeAnalyzer, ImpactAnalyzer
from .http_session import http_session_manager
from .test_runner import TestRunner, TestConfig, TestResult
from .history import HistoryManager, format_auto_suggest
from .db_inspector import DBInspector, DBConfig, get_inspector, clear_inspector

# Kanban System (v6.5)
try:
    from .kanban import kanban_manager, KanbanCard
    KANBAN_AVAILABLE = KANBAN_ENABLED
except ImportError:
    kanban_manager = None
    KanbanCard = None
    KANBAN_AVAILABLE = False

# Memory imports (v5.1 - Long-Term Memory)
try:
    from .memory import (
        memory_manager, context_injector, get_project_id,
        RelevanceScorer, ContextFormatter, should_index_file
    )
    from .embeddings import KeywordExtractor, detect_task_type
    # v6.0: Memory can be disabled via config even if dependencies are available
    # This prevents high RAM usage and potential kernel panics on low-memory systems
    MEMORY_AVAILABLE = MEMORY_ENABLED
except ImportError:
    MEMORY_AVAILABLE = False

# Code Summarizer imports (v5.4 - Deep Logic Summaries)
try:
    from .code_summarizer import code_summarizer
    SUMMARIZER_AVAILABLE = True
except ImportError:
    code_summarizer = None
    SUMMARIZER_AVAILABLE = False


# =============================================================================
# Handler Registry
# =============================================================================
HandlerFunc = Callable[[Dict[str, Any]], Awaitable[List[TextContent]]]

# v6.3: Track per-project hints to avoid spam (shown once per session)
_phpstan_hint_shown: Set[str] = set()  # Set of project_ids where hint was shown


class HandlerRegistry:
    """
    Registry for tool handlers with decorator-based registration.

    Usage:
        @handler.register("tool_name")
        async def handle_tool(args: Dict[str, Any]) -> List[TextContent]:
            ...
    """
    _handlers: Dict[str, HandlerFunc] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a handler function."""
        def decorator(func: HandlerFunc) -> HandlerFunc:
            cls._handlers[name] = func
            return func
        return decorator

    @classmethod
    async def dispatch(cls, name: str, args: Dict[str, Any]) -> List[TextContent]:
        """Dispatch a tool call to its registered handler."""
        # v4.9: Scope-Blockade - Tools ohne Scope blockieren
        if name not in SCOPE_REQUIRED_TOOLS:
            working_dir = args.get("working_dir")
            state = await pm.get_async(working_dir)
            if not state.scope:
                logger.warning(f"BLOCKED: {name} called without scope")
                # v6.0: XML Blockade Response
                if XML_RESPONSES_ENABLED:
                    return [TextContent(type="text", text=xml_blocked(
                        tool=name,
                        message="Kein Scope gesetzt",
                        blocker_type="scope_required",
                        blocker_data={
                            "description": "Du MUSST zuerst chainguard_set_scope() aufrufen!",
                            "example": "chainguard_set_scope(description=\"...\", working_dir=\"...\")",
                            "next_action": "Scope setzen, dann andere Tools nutzen"
                        }
                    ))]
                return [TextContent(type="text", text=SCOPE_BLOCKED_TEXT)]

        handler = cls._handlers.get(name)
        if handler:
            try:
                return await handler(args)
            except Exception as e:
                logger.error(f"Error in {name}: {e}")
                # v6.0: XML Error Response
                if XML_RESPONSES_ENABLED:
                    return [TextContent(type="text", text=xml_error(
                        tool=name,
                        message=f"Error: {str(e)[:50]}"
                    ))]
                return [TextContent(type="text", text=f"Error: {str(e)[:50]}")]
        # v6.0: XML Unknown Response
        if XML_RESPONSES_ENABLED:
            return [TextContent(type="text", text=xml_error(
                tool=name,
                message=f"Unknown handler: {name}"
            ))]
        return [TextContent(type="text", text=f"Unknown: {name}")]

    @classmethod
    def list_handlers(cls) -> List[str]:
        """List all registered handler names."""
        return list(cls._handlers.keys())


# Shorthand for decorator
handler = HandlerRegistry


# =============================================================================
# Helper Functions
# =============================================================================
def _text(msg: str) -> List[TextContent]:
    """Create a single TextContent response."""
    return [TextContent(type="text", text=msg)]


def _check_context(args: Dict[str, Any]) -> str:
    """Check for context marker and return refresh text if missing."""
    ctx = args.get("ctx", "")
    return "" if ctx == CONTEXT_MARKER else CONTEXT_REFRESH_TEXT


# =============================================================================
# CORE HANDLERS
# =============================================================================

@handler.register("chainguard_set_scope")
async def handle_set_scope(args: Dict[str, Any]) -> List[TextContent]:
    """Define task scope at start with Task Mode support."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    description = args["description"]

    # v5.0: Task Mode - explicit or auto-detected
    explicit_mode = args.get("mode")
    if explicit_mode:
        task_mode = TaskMode.from_string(explicit_mode)
        mode_source = "explicit"
    else:
        task_mode = detect_task_mode(description, state.project_path)
        mode_source = "auto-detected"

    state.scope = ScopeDefinition(
        description=description,
        modules=args.get("modules", []),
        acceptance_criteria=args.get("acceptance_criteria", []),
        checklist=args.get("checklist", []),
        created_at=datetime.now().isoformat()
    )

    # v5.0: Set task mode
    state.task_mode = str(task_mode)

    # v4.16: FULL STATE RESET - alle scope-relevanten Felder zurücksetzen!
    state.phase = "planning"
    state.files_since_validation = 0
    state.files_changed = 0
    state.out_of_scope_files = []
    state.changed_files = []
    state.db_schema_checked_at = ""  # v4.18: Timestamp statt Boolean
    state.http_tests_performed = 0
    state.http_base_url = ""
    state.http_credentials = {}
    state.impact_check_pending = False
    state.criteria_status = {}
    state.checklist_results = {}
    state.alerts = []
    state.recent_actions = []

    # v5.0: Reset mode-specific fields
    state.word_count_total = 0
    state.chapter_status = {}
    state.command_history = []
    state.checkpoints = []
    state.sources = []
    state.facts = []

    state.add_action(f"SCOPE[{task_mode}]: {description[:25]}")
    await pm.save_async(state)

    # v4.19: Create .chainguard marker in project directory for Enforcer Hook
    marker_dir = Path(state.project_path) / ".chainguard"
    try:
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_file = marker_dir / "marker"
        if not marker_file.exists():
            marker_file.write_text(f"# Chainguard Project Marker\n# Created: {datetime.now().isoformat()}\n# Mode: {task_mode}\n")
    except (OSError, PermissionError):
        pass  # Silently ignore if we can't create the marker

    criteria_count = len(state.scope.acceptance_criteria)
    checklist_count = len(state.scope.checklist)
    modules_str = ", ".join(state.scope.modules[:3]) or "all"
    desc_preview = description[:50] + "..." if len(description) > 50 else description

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        # Build scope data
        data = {
            "scope": {
                "description": desc_preview,
                "mode": str(task_mode),
                "mode_source": mode_source,
                "modules": modules_str,
                "criteria_count": criteria_count,
                "checklist_count": checklist_count
            }
        }

        # Add warning if description too long
        if len(description) > MAX_DESCRIPTION_LENGTH:
            data["warning"] = {
                "type": "description_too_long",
                "length": len(description),
                "max": MAX_DESCRIPTION_LENGTH,
                "hint": "Kurze Description + Details als acceptance_criteria"
            }

        # Add auto-detect hint
        if mode_source == "auto-detected":
            data["hint"] = {
                "type": "mode_auto_detected",
                "message": "Modus wurde automatisch erkannt",
                "override": "chainguard_set_scope(mode=\"programming|content|devops|research\")"
            }

        # Get XML context template
        context = get_mode_context_xml(task_mode)

        # v5.1/v5.2: Smart Context Injection from Long-Term Memory
        if MEMORY_AVAILABLE:
            try:
                project_id = get_project_id(state.project_path)
                memory_context = await context_injector.get_context(
                    project_id=project_id,
                    description=description,
                    max_results=8
                )
                if memory_context:
                    data["memory_context"] = memory_context

                # Add proactive hints from learnings
                if await memory_manager.memory_exists(project_id):
                    memory = await memory_manager.get_memory(project_id)
                    keywords = KeywordExtractor.extract(description)
                    if keywords:
                        learning_results = await memory.query(
                            query_text=" ".join(keywords),
                            collection="learnings",
                            n_results=2
                        )
                        if learning_results:
                            similar_tasks = []
                            for doc, distance in learning_results:
                                if distance < 0.8:
                                    scope = doc.metadata.get("scope", "")
                                    if scope and scope != description:
                                        similar_tasks.append(scope[:50])
                            if similar_tasks:
                                data["similar_tasks"] = similar_tasks

            except Exception as e:
                logger.warning(f"Smart Context Injection failed: {e}")

        # v6.5: Smart Kanban Suggestion for complex projects (XML)
        complexity_keywords = ["mehrtägig", "komplex", "pipeline", "phasen", "multi-day", "mehrere schritte", "multi-step"]
        is_complex = criteria_count >= 5 or any(kw in description.lower() for kw in complexity_keywords)

        if is_complex and KANBAN_AVAILABLE:
            preset_map = {
                TaskMode.PROGRAMMING: "programming",
                TaskMode.CONTENT: "content",
                TaskMode.DEVOPS: "devops",
                TaskMode.RESEARCH: "research",
            }
            suggested_preset = preset_map.get(task_mode, "programming")
            data["kanban_suggestion"] = {
                "reason": f"complex_project_{criteria_count}_criteria",
                "preset": suggested_preset,
                "command": f'chainguard_kanban_init(preset="{suggested_preset}")'
            }

        return _text(xml_success(
            tool="set_scope",
            message="Scope definiert",
            data=data,
            context=context
        ))

    # Legacy plain text response
    mode_emoji = {
        TaskMode.PROGRAMMING: "💻",
        TaskMode.CONTENT: "📝",
        TaskMode.DEVOPS: "🖥️",
        TaskMode.RESEARCH: "🔬",
        TaskMode.GENERIC: "⚡"
    }.get(task_mode, "📋")

    lines = [f"✓ Scope: {desc_preview}"]
    lines.append(f"{mode_emoji} **Mode: {task_mode}** ({mode_source})")
    lines.append(f"Modules: {modules_str} | Criteria: {criteria_count} | Checks: {checklist_count}")

    if len(description) > MAX_DESCRIPTION_LENGTH:
        lines.append("")
        lines.append(f"⚠ Description lang ({len(description)} > {MAX_DESCRIPTION_LENGTH})")
        lines.append("→ Tipp: Kurze Description + Details als acceptance_criteria")

    context_text = get_mode_context(task_mode)
    lines.append(context_text)

    if mode_source == "auto-detected":
        lines.append("")
        lines.append(f"💡 Modus wurde automatisch erkannt. Falls falsch:")
        lines.append(f'   `chainguard_set_scope(description="...", mode="programming|content|devops|research")`')

    if MEMORY_AVAILABLE:
        try:
            project_id = get_project_id(state.project_path)
            context_text = await context_injector.get_context(
                project_id=project_id,
                description=description,
                max_results=8
            )
            if context_text:
                lines.append(context_text)

            if await memory_manager.memory_exists(project_id):
                memory = await memory_manager.get_memory(project_id)
                keywords = KeywordExtractor.extract(description)
                if keywords:
                    learning_results = await memory.query(
                        query_text=" ".join(keywords),
                        collection="learnings",
                        n_results=2
                    )
                    if learning_results:
                        hint_lines = []
                        for doc, distance in learning_results:
                            if distance < 0.8:
                                scope = doc.metadata.get("scope", "")
                                if scope and scope != description:
                                    hint_lines.append(f"• {scope[:50]}")
                        if hint_lines:
                            lines.append("")
                            lines.append("💡 **Ähnliche frühere Tasks:**")
                            for hint in hint_lines[:2]:
                                lines.append(hint)

        except Exception as e:
            logger.warning(f"Smart Context Injection failed: {e}")

    # v6.5: Smart Kanban Suggestion for complex projects
    complexity_keywords = ["mehrtägig", "komplex", "pipeline", "phasen", "multi-day", "mehrere schritte", "multi-step"]
    is_complex = criteria_count >= 5 or any(kw in description.lower() for kw in complexity_keywords)

    if is_complex and KANBAN_AVAILABLE:
        # Suggest preset based on task mode
        preset_map = {
            TaskMode.PROGRAMMING: "programming",
            TaskMode.CONTENT: "content",
            TaskMode.DEVOPS: "devops",
            TaskMode.RESEARCH: "research",
        }
        suggested_preset = preset_map.get(task_mode, "programming")
        lines.append("")
        lines.append(f"💡 **Komplexes Projekt erkannt** ({criteria_count} Kriterien)")
        lines.append(f'   Empfehlung: `chainguard_kanban_init(preset="{suggested_preset}")`')
        lines.append("   → Persistiert Tasks über Sessions, trackt Dependencies")

    return _text("\n".join(lines))


@handler.register("chainguard_track")
async def handle_track(args: Dict[str, Any]) -> List[TextContent]:
    """Track file change with mode-aware auto-validation and Error Memory."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    file = args.get("file", "")
    action = args.get("action", "edit")
    skip_validation = args.get("skip_validation", False)

    if file and not is_path_safe(file, state.project_path):
        return _text("⚠ Invalid path")

    # v5.0: Get task mode and features
    task_mode = state.get_task_mode()
    features = state.get_features()

    state.files_changed += 1
    state.files_since_validation += 1
    state.last_activity = datetime.now().isoformat()

    if file:
        state.add_changed_file(Path(file).name)

    messages = []

    # v5.0: Only check schema files in programming mode
    is_schema_file = state.is_schema_file(file) if file else False

    if features.db_inspection and is_schema_file:
        # v4.18: Invalidate schema check when .sql files are modified
        if state.db_schema_checked_at:
            was_invalidated = state.invalidate_schema_check()
            if was_invalidated:
                messages.append("🔄 **SCHEMA INVALIDIERT**")
                messages.append("   Schema-Datei geändert → DB-Schema muss neu geprüft werden.")
                messages.append("   → Nutze: chainguard_db_schema(refresh=True) vor weiteren Änderungen")
                messages.append("")

        # v4.14/v4.18: Warn if editing schema/migration files without valid schema check
        if not state.is_schema_checked():
            schema_age = state.get_schema_check_age()
            if schema_age == -1:
                messages.append("⚠️ **DB-SCHEMA NICHT GEPRÜFT!**")
                messages.append("   Du bearbeitest Schema-Dateien ohne vorherige DB-Inspektion.")
            else:
                messages.append(f"⚠️ **DB-SCHEMA VERALTET!** (Check vor {schema_age}s, TTL: 600s)")
                messages.append("   Schema-Check ist abgelaufen.")
            messages.append("   → Nutze: chainguard_db_connect() + chainguard_db_schema()")
            messages.append("   → Verhindert Spalten-Fehler wie 'Unknown column'")
            messages.append("")

    validation_result = "PASS"
    error_type = ""
    error_msg = ""

    # v5.0: Syntax Validation - only if mode enables it for this file type
    run_validation = (
        file and
        not skip_validation and
        action != "delete" and
        should_validate_syntax(task_mode, file)
    )

    if run_validation:
        validation = await SyntaxValidator.validate_file(file, state.project_path)
        if not validation["valid"]:
            for err in validation["errors"]:
                messages.append(f"✗ {err['type']}: {err['message']}")
                error_type = err['type']
                error_msg = err['message']
                validation_result = f"FAIL:{err['type']}:{err['message'][:50]}"

            state.alerts.append({
                "msg": f"Syntax error in {Path(file).name}",
                "errors": validation["errors"],
                "ack": False,
                "ts": datetime.now().isoformat()
            })

            # v4.11: Index error for future recall
            scope_desc = state.scope.description if state.scope else ""
            await HistoryManager.index_error(
                project_id=state.project_id,
                file=file,
                error_type=error_type,
                error_msg=error_msg,
                scope_desc=scope_desc
            )

            # v4.11: Auto-Suggest - find similar errors with known fixes
            similar = await HistoryManager.find_similar_errors(
                project_id=state.project_id,
                file=file,
                error_type=error_type,
                error_msg=error_msg
            )
            if similar:
                messages.append(format_auto_suggest(similar))

        # v6.3: Show one-time hint if PHPStan not available for PHP files
        if validation.get("phpstan_available") is False:
            if state.project_id not in _phpstan_hint_shown:
                _phpstan_hint_shown.add(state.project_id)
                messages.append("")
                messages.append("💡 **PHPStan nicht installiert** - Erweiterte PHP-Analyse deaktiviert")
                messages.append("   PHPStan erkennt Null-Zugriffe und Typ-Fehler VOR der Ausführung.")
                messages.append("   Install: `composer global require phpstan/phpstan`")

    # v6.2: Symbol Validation - check for hallucinated function calls
    run_symbol_validation = (
        SYMBOL_VALIDATION_AUTO and
        file and
        action != "delete" and
        task_mode == TaskMode.PROGRAMMING and
        SymbolValidator.get_mode() != SymbolValidationMode.OFF
    )

    if run_symbol_validation:
        try:
            # Read file content
            full_path = Path(state.project_path) / file
            if full_path.exists():
                file_content = full_path.read_text(encoding='utf-8', errors='replace')

                # Collect known symbols from project (cached per language)
                lang = detect_language(str(full_path))
                if lang:
                    known_symbols = await _get_project_symbols(state.project_path, lang)

                    # Validate
                    symbol_result = SymbolValidator.validate(file_content, file, known_symbols)

                    # Report issues (WARN mode = inform only, never block)
                    if symbol_result.issues:
                        high_conf = [i for i in symbol_result.issues if i.confidence > 0.7]
                        if high_conf:
                            messages.append("")
                            messages.append(f"⚠️ Symbol-Check: {len(high_conf)} potenzielle Halluzinationen")
                            for issue in high_conf[:3]:  # Max 3 shown
                                messages.append(f"   [{issue.confidence:.0%}] {issue.name}() - Line {issue.line}")
                            if len(high_conf) > 3:
                                messages.append(f"   ... und {len(high_conf) - 3} weitere")
                            messages.append("   → Prüfe ob diese Funktionen existieren")

                            # v6.4.1: Collect warnings for finish summary
                            for issue in high_conf:
                                warning = f"{Path(file).name}:{issue.line} → {issue.name}() [{issue.confidence:.0%}]"
                                if warning not in state.symbol_warnings:
                                    state.symbol_warnings.append(warning)
        except Exception as e:
            logger.debug(f"Symbol validation skipped: {e}")

    # Check scope
    sanitized = sanitize_path(file, state.project_path) if file else ""
    if sanitized and not state.check_file_in_scope(sanitized):
        state.add_out_of_scope_file(sanitized)
        messages.append(f"⚠ OOS: {Path(sanitized).name}")

    state.add_action(f"{action}: {Path(file).name if file else '?'}")
    await pm.save_async(state)

    # v4.11: Log change to history
    if file:
        scope_id = state.scope.created_at if state.scope else ""
        scope_desc = state.scope.description if state.scope else ""
        await HistoryManager.log_change(
            project_id=state.project_id,
            file=sanitized or file,
            action=action,
            validation_result=validation_result,
            scope_id=scope_id,
            scope_desc=scope_desc
        )

    # v5.2: Auto-update memory when file is tracked (non-blocking)
    if MEMORY_AVAILABLE and file:
        try:
            project_id = get_project_id(state.project_path)
            if await memory_manager.memory_exists(project_id):
                if action == "delete":
                    # v5.3: Remove deleted files from memory
                    asyncio.create_task(_delete_from_memory(
                        project_id=project_id,
                        file_path=file,
                        project_path=state.project_path
                    ))
                else:
                    # Fire-and-forget: update memory in background
                    asyncio.create_task(_update_memory_for_file(
                        project_id=project_id,
                        file_path=file,
                        project_path=state.project_path
                    ))
        except Exception as e:
            logger.debug(f"Memory auto-update skipped: {e}")

    context_refresh = _check_context(args)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        file_name = Path(file).name if file else ""

        # Build response data
        data = {
            "file": file_name,
            "action": action,
            "files_changed": state.files_changed,
            "files_since_validation": state.files_since_validation
        }

        # Check for errors
        if error_type and error_msg:
            data["validation"] = {
                "status": "fail",
                "error": {
                    "type": error_type,
                    "message": error_msg[:100]
                }
            }
            # Add auto-suggest if available
            if messages:
                for msg in messages:
                    if "Similar error" in msg or "💡" in msg:
                        data["validation"]["suggestion"] = msg

            return _text(xml_error(
                tool="track",
                message=f"Syntax error in {file_name}",
                data=data
            ))

        # Check for warnings (schema, OOS)
        warnings = [m for m in messages if "⚠" in m or "🔄" in m]
        if warnings:
            data["warnings"] = warnings[:3]
            return _text(xml_warning(
                tool="track",
                message="File tracked with warnings",
                data=data
            ))

        # Add validation hint if needed
        if state.needs_validation():
            data["hint"] = f"{state.files_since_validation} changes, validate soon"

        return _text(xml_success(
            tool="track",
            message="File tracked" if file else "Tracked",
            data=data
        ))

    # Legacy response
    if messages:
        return _text("\n".join(messages) + context_refresh)

    if state.needs_validation():
        return _text(f"→ {state.files_since_validation} changes, validate soon{context_refresh}")

    return _text(context_refresh.strip())


@handler.register("chainguard_track_batch")
async def handle_track_batch(args: Dict[str, Any]) -> List[TextContent]:
    """Track multiple files at once."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    files = args.get("files", [])
    action = args.get("action", "edit")
    skip_validation = args.get("skip_validation", False)

    if not files:
        return _text("⚠ No files provided")

    files = files[:MAX_BATCH_FILES]
    errors = []
    tracked = 0
    oos_count = 0

    # v4.18: Check for schema files in batch and handle invalidation
    schema_files_in_batch = [f for f in files if f and state.is_schema_file(f)]

    if schema_files_in_batch:
        # Invalidate schema check if any schema file is in batch
        if state.db_schema_checked_at:
            state.invalidate_schema_check()
            errors.append("🔄 **SCHEMA INVALIDIERT**")
            errors.append(f"   {len(schema_files_in_batch)} Schema-Datei(en) geändert")
            errors.append("   → Nutze: chainguard_db_schema(refresh=True)")
            errors.append("")

        # Warn if schema not checked
        if not state.is_schema_checked():
            schema_age = state.get_schema_check_age()
            if schema_age == -1:
                errors.append("⚠️ **DB-SCHEMA NICHT GEPRÜFT!**")
            else:
                errors.append(f"⚠️ **DB-SCHEMA VERALTET!** (Check vor {schema_age}s)")
            errors.append("   Du bearbeitest Schema-Dateien ohne gültige DB-Inspektion.")
            errors.append("   → Nutze: chainguard_db_connect() + chainguard_db_schema()")
            errors.append("")

    for file in files:
        if file and not is_path_safe(file, state.project_path):
            errors.append(f"⚠ Invalid path: {Path(file).name}")
            continue

        state.files_changed += 1
        state.files_since_validation += 1

        if file:
            state.add_changed_file(Path(file).name)

        if file and not skip_validation and action != "delete":
            validation = await SyntaxValidator.validate_file(file, state.project_path)
            if not validation["valid"]:
                for err in validation["errors"]:
                    errors.append(f"✗ {Path(file).name}: {err['type']} - {err['message'][:40]}")
                state.alerts.append({
                    "msg": f"Syntax error in {Path(file).name}",
                    "errors": validation["errors"],
                    "ack": False,
                    "ts": datetime.now().isoformat()
                })
            else:
                tracked += 1

        sanitized = sanitize_path(file, state.project_path) if file else ""
        if sanitized and not state.check_file_in_scope(sanitized):
            state.add_out_of_scope_file(sanitized)
            oos_count += 1

    state.last_activity = datetime.now().isoformat()
    # v4.16: Dateinamen in Action speichern für HTTP-Test Fallback
    file_names = [Path(f).name for f in files if f][:3]
    file_names_str = ", ".join(file_names)
    if len(files) > 3:
        file_names_str += f" +{len(files)-3}"
    state.add_action(f"BATCH: {action} [{file_names_str}]")
    await pm.save_async(state, immediate=True)  # v4.16: immediate für Konsistenz

    actual_tracked = len(files) if skip_validation else tracked

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "tracked": actual_tracked,
            "total": len(files),
            "action": action,
            "files_changed": state.files_changed,
            "files_since_validation": state.files_since_validation
        }

        if errors:
            data["errors"] = errors[:5]
        if oos_count > 0:
            data["out_of_scope"] = oos_count

        if errors:
            return _text(xml_warning(
                tool="track_batch",
                message=f"{actual_tracked}/{len(files)} tracked, {len(errors)} Fehler",
                data=data
            ))

        return _text(xml_success(
            tool="track_batch",
            message=f"{actual_tracked}/{len(files)} files tracked",
            data=data
        ))

    # Legacy plain text response
    parts = []
    if tracked > 0 or (skip_validation and len(files) > 0):
        parts.append(f"✓ {actual_tracked}/{len(files)} files tracked")

    if errors:
        parts.append("\n".join(errors[:5]))
        if len(errors) > 5:
            parts.append(f"... +{len(errors) - 5} more errors")

    if oos_count > 0:
        parts.append(f"⚠ {oos_count} files out of scope")

    if state.needs_validation():
        parts.append(f"→ {state.files_since_validation} changes, validate soon")

    return _text("\n".join(parts) if parts else "")


@handler.register("chainguard_status")
async def handle_status(args: Dict[str, Any]) -> List[TextContent]:
    """Ultra-compact one-line status."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        task_mode = state.get_task_mode()
        open_alerts = [a for a in state.alerts if not a.get("ack")]

        data = {
            "project": state.project_name,
            "phase": state.phase,
            "mode": str(task_mode),
            "files_changed": state.files_changed,
            "files_since_validation": state.files_since_validation,
            "validations": {
                "passed": state.validations_passed,
                "failed": state.validations_failed
            },
            "alerts_count": len(open_alerts)
        }

        # Add scope info if exists
        if state.scope:
            done = sum(1 for c in state.scope.acceptance_criteria if state.criteria_status.get(c))
            total = len(state.scope.acceptance_criteria)
            data["criteria"] = {"done": done, "total": total}
            data["scope_preview"] = state.scope.description[:30]

        return _text(xml_info(
            tool="status",
            data=data
        ))

    # Legacy response
    status_line = state.get_status_line()
    context_refresh = _check_context(args)
    if context_refresh:
        return _text(f"{status_line}{context_refresh}")
    return _text(status_line)


@handler.register("chainguard_context")
async def handle_context(args: Dict[str, Any]) -> List[TextContent]:
    """Full context - use sparingly."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        task_mode = state.get_task_mode()
        open_alerts = [a for a in state.alerts if not a.get("ack")]

        data = {
            "project": {
                "name": state.project_name,
                "path": state.project_path,
                "phase": state.phase,
                "mode": str(task_mode)
            },
            "stats": {
                "files_changed": state.files_changed,
                "files_since_validation": state.files_since_validation,
                "validations_passed": state.validations_passed,
                "validations_failed": state.validations_failed
            }
        }

        # Warnings
        warnings = []
        if not state.scope:
            warnings.append("NO SCOPE DEFINED")
        if state.needs_validation():
            warnings.append(f"{state.files_since_validation} changes need validation")
        if state.out_of_scope_files:
            warnings.append(f"OOS files: {len(state.out_of_scope_files)}")
        if open_alerts:
            warnings.append(f"{len(open_alerts)} open alerts")
        if warnings:
            data["warnings"] = warnings

        # Scope info
        if state.scope:
            desc = state.scope.description
            if len(desc) > DESCRIPTION_PREVIEW_LENGTH:
                desc_preview = desc[:DESCRIPTION_PREVIEW_LENGTH] + "..."
            else:
                desc_preview = desc

            done = sum(1 for c in state.scope.acceptance_criteria if state.criteria_status.get(c))
            total = len(state.scope.acceptance_criteria)

            data["scope"] = {
                "description": desc_preview,
                "modules": state.scope.modules[:5] if state.scope.modules else [],
                "criteria": {"done": done, "total": total}
            }

        # Recent actions
        if state.recent_actions:
            data["recent_actions"] = state.recent_actions[-5:]

        # Alerts detail
        if open_alerts:
            data["alerts"] = [{"message": a["msg"][:50], "ts": a.get("ts", "")} for a in open_alerts[-3:]]

        return _text(xml_info(
            tool="context",
            message="Full project context",
            data=data
        ))

    # Legacy response
    lines = [f"## {state.project_name} [{state.phase}]"]

    warnings = []
    if not state.scope:
        warnings.append("NO SCOPE DEFINED")
    if state.needs_validation():
        warnings.append(f"{state.files_since_validation} changes need validation")
    if state.out_of_scope_files:
        warnings.append(f"OOS files: {', '.join(Path(f).name for f in state.out_of_scope_files[-3:])}")

    open_alerts = [a for a in state.alerts if not a.get("ack")]
    if open_alerts:
        warnings.append(f"Alerts: {', '.join(a['msg'][:20] for a in open_alerts[-2:])}")

    if warnings:
        lines.append(f"**⚠ {' | '.join(warnings)}**")

    if state.scope:
        desc = state.scope.description
        if len(desc) > DESCRIPTION_PREVIEW_LENGTH:
            desc_preview = desc[:DESCRIPTION_PREVIEW_LENGTH] + f"... ({len(desc)} chars)"
        else:
            desc_preview = desc
        lines.append(f"\n**Scope:** {desc_preview}")
        if state.scope.modules:
            lines.append(f"Modules: {', '.join(state.scope.modules[:5])}")

    lines.append(f"\n**Stats:** {state.files_changed} files | {state.files_since_validation} since val | V:{state.validations_passed}✓/{state.validations_failed}✗")

    if state.scope and state.scope.acceptance_criteria:
        done = sum(1 for c in state.scope.acceptance_criteria if state.criteria_status.get(c))
        total = len(state.scope.acceptance_criteria)
        lines.append(f"**Criteria:** {done}/{total}")

    if state.recent_actions:
        lines.append(f"\n**Recent:** {' → '.join(state.recent_actions[-3:])}")

    return _text("\n".join(lines))


@handler.register("chainguard_set_phase")
async def handle_set_phase(args: Dict[str, Any]) -> List[TextContent]:
    """Set project phase."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    new_phase = args["phase"]
    state.current_task = args.get("task", "")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        if new_phase == "done":
            completion = state.get_completion_status()
            if not completion["complete"]:
                state.phase = new_phase
                state.add_action("PHASE: done (warnings)")
                await pm.save_async(state)

                return _text(xml_warning(
                    tool="set_phase",
                    message="Phase auf 'done' gesetzt mit Warnungen",
                    data={
                        "phase": new_phase,
                        "issues": [i["message"] for i in completion["issues"]],
                        "hint": "Nutze chainguard_finish() für sauberen Abschluss"
                    }
                ))

        state.phase = new_phase
        state.add_action(f"PHASE: {state.phase}")
        await pm.save_async(state)

        data = {"phase": new_phase}
        if state.current_task:
            data["task"] = state.current_task

        return _text(xml_success(
            tool="set_phase",
            message=f"Phase: {new_phase}",
            data=data
        ))

    # Legacy response
    if new_phase == "done":
        completion = state.get_completion_status()
        if not completion["complete"]:
            warnings = [f"⚠ {i['message']}" for i in completion["issues"]]
            state.phase = new_phase
            state.add_action("PHASE: done (warnings)")
            await pm.save_async(state)
            return _text(f"→ done (mit Warnungen)\n" + "\n".join(warnings) +
                        "\n\n→ Nutze `chainguard_finish` für sauberen Abschluss")

    state.phase = new_phase
    state.add_action(f"PHASE: {state.phase}")
    await pm.save_async(state)

    task_str = f": {state.current_task}" if state.current_task else ""
    return _text(f"→ {state.phase}{task_str}")


# =============================================================================
# VALIDATION HANDLERS
# =============================================================================

@handler.register("chainguard_run_checklist")
async def handle_run_checklist(args: Dict[str, Any]) -> List[TextContent]:
    """Execute all checklist checks."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    if not state.scope or not state.scope.checklist:
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(tool="run_checklist", message="No checklist defined"))
        return _text("No checklist defined")

    # Use async version for better performance
    results = await ChecklistRunner.run_all_async(state.scope.checklist, state.project_path)
    state.checklist_results = results["results"]
    state.add_action(f"CHECK: {results['passed']}/{results['total']}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        all_passed = results['passed'] == results['total']
        return _text(xml_success(
            tool="run_checklist",
            message=f"Checklist {results['passed']}/{results['total']}",
            data={
                "passed": results['passed'],
                "total": results['total'],
                "all_passed": all_passed,
                "results": results["results"]
            }
        ) if all_passed else xml_warning(
            tool="run_checklist",
            message=f"Checklist {results['passed']}/{results['total']} - nicht alle bestanden",
            data={
                "passed": results['passed'],
                "total": results['total'],
                "results": results["results"]
            }
        ))

    # Legacy response
    result_str = " ".join(f"{k}:{v}" for k, v in results["results"].items())
    return _text(f"Checklist {results['passed']}/{results['total']}: {result_str}")


@handler.register("chainguard_check_criteria")
async def handle_check_criteria(args: Dict[str, Any]) -> List[TextContent]:
    """Mark or view acceptance criteria."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    # Setting a criterion
    if args.get("criterion") is not None and args.get("fulfilled") is not None:
        state.criteria_status[args["criterion"]] = args["fulfilled"]
        await pm.save_async(state)

        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="check_criteria",
                message=f"Kriterium {'erfüllt' if args['fulfilled'] else 'nicht erfüllt'}",
                data={
                    "criterion": args["criterion"][:50],
                    "fulfilled": args["fulfilled"]
                }
            ))

        icon = '✓' if args['fulfilled'] else '✗'
        return _text(f"{icon} {args['criterion'][:40]}")

    # Listing criteria
    if not state.scope or not state.scope.acceptance_criteria:
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(tool="check_criteria", message="No criteria defined"))
        return _text("No criteria defined")

    done = sum(1 for c in state.scope.acceptance_criteria if state.criteria_status.get(c))
    total = len(state.scope.acceptance_criteria)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        criteria_list = []
        for c in state.scope.acceptance_criteria:
            status = state.criteria_status.get(c)
            criteria_list.append({
                "name": c,
                "status": "done" if status is True else "failed" if status is False else "pending"
            })

        return _text(xml_info(
            tool="check_criteria",
            message=f"Criteria {done}/{total}",
            data={
                "done": done,
                "total": total,
                "criteria": criteria_list
            }
        ))

    # Legacy response
    lines = []
    for c in state.scope.acceptance_criteria:
        status = state.criteria_status.get(c)
        icon = "✓" if status is True else "✗" if status is False else "?"
        lines.append(f"{icon} {c}")

    return _text(f"Criteria {done}/{total}:\n" + "\n".join(lines))


@handler.register("chainguard_validate")
async def handle_validate(args: Dict[str, Any]) -> List[TextContent]:
    """Record validation result."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    status = args["status"]
    note = args.get("note", "")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        if status == "PASS":
            state.validations_passed += 1
            completion = state.get_completion_status()

            state.files_since_validation = 0
            state.last_validation = datetime.now().isoformat()

            if not completion["complete"]:
                state.add_action("VAL: PASS (warnings)")
                await pm.save_async(state, immediate=True)

                return _text(xml_warning(
                    tool="validate",
                    message="Validation PASS mit offenen Punkten",
                    data={
                        "status": "PASS",
                        "note": note if note else None,
                        "issues": [i["message"] for i in completion["issues"]],
                        "hint": "Nutze chainguard_finish() für vollständigen Abschluss"
                    }
                ))

            state.add_action("VAL: PASS")
            await pm.save_async(state, immediate=True)
            return _text(xml_success(
                tool="validate",
                message="Validation PASS",
                data={"status": "PASS", "note": note if note else None}
            ))
        else:
            state.validations_failed += 1
            state.alerts.append({
                "msg": note or "Validation failed",
                "ack": False,
                "ts": datetime.now().isoformat()
            })
            state.files_since_validation = 0
            state.last_validation = datetime.now().isoformat()
            state.add_action("VAL: FAIL")
            await pm.save_async(state, immediate=True)

            return _text(xml_error(
                tool="validate",
                message="Validation FAIL",
                data={"status": "FAIL", "note": note if note else None}
            ))

    # Legacy response
    if status == "PASS":
        state.validations_passed += 1
        completion = state.get_completion_status()
        if not completion["complete"]:
            warnings = [f"⚠ {i['message']}" for i in completion["issues"]]
            state.files_since_validation = 0
            state.last_validation = datetime.now().isoformat()
            state.add_action("VAL: PASS (warnings)")
            await pm.save_async(state, immediate=True)
            return _text(f"Validation: PASS" + (f" - {note}" if note else "") +
                        f"\n\n⚠ Offene Punkte:\n" + "\n".join(warnings) +
                        "\n\n→ Nutze `chainguard_finish` für vollständigen Abschluss")
    else:
        state.validations_failed += 1
        state.alerts.append({
            "msg": note or "Validation failed",
            "ack": False,
            "ts": datetime.now().isoformat()
        })

    state.files_since_validation = 0
    state.last_validation = datetime.now().isoformat()
    state.add_action(f"VAL: {status}")
    await pm.save_async(state, immediate=True)

    return _text(f"Validation: {status}" + (f" - {note}" if note else ""))


# =============================================================================
# ALERT HANDLERS
# =============================================================================

@handler.register("chainguard_alert")
async def handle_alert(args: Dict[str, Any]) -> List[TextContent]:
    """Add an alert."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    message = args["message"]
    state.alerts.append({
        "msg": message,
        "ack": False,
        "ts": datetime.now().isoformat()
    })
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_warning(
            tool="alert",
            message="Alert hinzugefügt",
            data={
                "alert": message[:100],
                "total_alerts": len([a for a in state.alerts if not a.get("ack")])
            }
        ))

    return _text(f"⚠ {message[:50]}")


@handler.register("chainguard_clear_alerts")
async def handle_clear_alerts(args: Dict[str, Any]) -> List[TextContent]:
    """Acknowledge all alerts."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    count = sum(1 for a in state.alerts if not a.get("ack"))
    for a in state.alerts:
        a["ack"] = True
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="clear_alerts",
            message=f"{count} Alerts bestätigt",
            data={"cleared_count": count}
        ))

    return _text(f"✓ {count} alerts cleared")


# =============================================================================
# ADMIN HANDLERS
# =============================================================================

@handler.register("chainguard_projects")
async def handle_projects(args: Dict[str, Any]) -> List[TextContent]:
    """List all tracked projects."""
    projects = await pm.list_all_projects_async()

    if not projects:
        return _text("No projects")

    # Build projects data for any format
    projects_data = [
        {"id": p["name"][:8], "path": p["name"], "phase": p["phase"], "files": p.get("files", 0)}
        for p in projects[:10]
    ]

    # v6.0: TOON Response (30-60% token savings on arrays)
    if TOON_ENABLED:
        return _text(toon_projects(projects_data))

    # v6.0: XML Response (disabled by default)
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="projects",
            message=f"{len(projects)} Projekte",
            data={"count": len(projects), "projects": projects_data}
        ))

    # Legacy
    lines = [f"{p['name']}|{p['phase']}|{p['last']}" for p in projects[:10]]
    return _text("\n".join(lines))


@handler.register("chainguard_config")
async def handle_config(args: Dict[str, Any]) -> List[TextContent]:
    """View or set config."""
    updated = False
    if args.get("validation_threshold"):
        CONFIG.validation_reminder_threshold = args["validation_threshold"]
        CONFIG.save()
        updated = True

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "validation_threshold": CONFIG.validation_reminder_threshold
        }
        if updated:
            return _text(xml_success(
                tool="config",
                message="Config aktualisiert",
                data=data
            ))
        return _text(xml_info(
            tool="config",
            message="Aktuelle Config",
            data=data
        ))

    return _text(f"Config: val_threshold={CONFIG.validation_reminder_threshold}")


# =============================================================================
# HTTP TESTING HANDLERS
# =============================================================================

@handler.register("chainguard_test_endpoint")
async def handle_test_endpoint(args: Dict[str, Any]) -> List[TextContent]:
    """Test HTTP endpoint with session support and auto-re-login."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    url = args["url"]
    method = args.get("method", "GET")
    data = args.get("data")
    headers = args.get("headers")

    if not url.startswith("http"):
        if state.http_base_url:
            url = state.http_base_url.rstrip("/") + "/" + url.lstrip("/")
        else:
            if XML_RESPONSES_ENABLED:
                return _text(xml_blocked(
                    tool="test_endpoint",
                    message="Keine Base-URL gesetzt",
                    blocker_type="base_url_required",
                    blocker_data={"action": "chainguard_set_base_url(base_url=\"...\")"}
                ))
            return _text("⚠ Set base_url first: chainguard_set_base_url")

    # v4.15: Auto-re-login if session was lost but credentials are stored
    auto_relogin = False
    session_check = await http_session_manager.ensure_session(
        project_id=state.project_id,
        base_url=state.http_base_url
    )
    if session_check.get("auto_relogin"):
        auto_relogin = True

    result = await http_session_manager.test_endpoint(
        url=url, method=method, project_id=state.project_id,
        data=data, headers=headers
    )

    # v4.13: Track HTTP tests for finish warning
    state.http_tests_performed += 1
    state.add_action(f"HTTP {method}: {result['status_code']}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        response_data = {
            "method": method,
            "url": url[:80],
            "status_code": result["status_code"],
            "auto_relogin": auto_relogin
        }

        if result["needs_auth"]:
            return _text(xml_blocked(
                tool="test_endpoint",
                message=f"Auth required ({result['status_code']})",
                blocker_type="auth_required",
                blocker_data={
                    "status_code": result["status_code"],
                    "error": result.get("error", ""),
                    "action": "chainguard_login(...)"
                }
            ))

        if result["success"]:
            if result["body_preview"]:
                response_data["body_preview"] = result["body_preview"][:200]
            return _text(xml_success(
                tool="test_endpoint",
                message=f"{method} {result['status_code']}",
                data=response_data
            ))

        response_data["error"] = result.get("error", "Failed")
        if result["body_preview"]:
            response_data["body_preview"] = result["body_preview"][:200]
        return _text(xml_error(
            tool="test_endpoint",
            message=f"{method} {result['status_code']} fehlgeschlagen",
            data=response_data
        ))

    # Legacy response
    relogin_msg = "🔄 Auto-Re-Login erfolgreich\n" if auto_relogin else ""

    if result["needs_auth"]:
        return _text(f"🔐 Auth required ({result['status_code']}): {result['error']}\n→ Use chainguard_login to authenticate")

    if result["success"]:
        preview = result["body_preview"][:200] if result["body_preview"] else ""
        return _text(f"{relogin_msg}✓ {method} {result['status_code']}\n{preview}")

    return _text(f"{relogin_msg}✗ {method} {result['status_code']}: {result.get('error', 'Failed')}\n{result['body_preview'][:200]}")


@handler.register("chainguard_login")
async def handle_login(args: Dict[str, Any]) -> List[TextContent]:
    """Login to application and store session."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    login_url = args["login_url"]
    username = args["username"]
    password = args["password"]
    username_field = args.get("username_field", "email")
    password_field = args.get("password_field", "password")

    if not login_url.startswith("http") and state.http_base_url:
        login_url = state.http_base_url.rstrip("/") + "/" + login_url.lstrip("/")

    result = await http_session_manager.login(
        login_url=login_url, username=username, password=password,
        project_id=state.project_id, username_field=username_field,
        password_field=password_field
    )

    if result["success"]:
        state.http_credentials = {"username": username, "login_url": login_url}
        state.add_action("LOGIN: success")
        await pm.save_async(state)

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="login",
                message=f"Eingeloggt als {username}",
                data={"username": username, "session_stored": True}
            ))
        return _text(f"✓ Logged in as {username}\nSession stored for future requests")

    state.add_action("LOGIN: failed")

    # v4.16: BLOCKING Alert - finish() kann nicht umgangen werden bis Credentials geklärt
    state.alerts.append({
        "msg": "⛔ LOGIN_REQUIRED: Credentials via AskUserQuestion klären",
        "type": "login_required",
        "blocking": True,  # Kann nicht mit force=true umgangen werden!
        "ack": False,
        "ts": datetime.now().isoformat()
    })

    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_blocked(
            tool="login",
            message=f"Login fehlgeschlagen: {result.get('error', 'Unknown error')}",
            blocker_type="login_failed",
            blocker_data={
                "error": result.get("error", "Unknown error"),
                "required_fields": ["login_url", "username", "password"],
                "optional_fields": ["username_field", "password_field"],
                "action": "AskUserQuestion für korrekte Credentials nutzen",
                "finish_blocked": True
            }
        ))

    return _text(
        f"✗ Login failed: {result.get('error', 'Unknown error')}\n\n"
        "⛔ BLOCKIERT: Nutze AskUserQuestion für korrekte Credentials:\n"
        "   - Login URL (if different)\n"
        "   - Username/Email\n"
        "   - Password\n"
        "   - Username field name (default: 'email')\n"
        "   - Password field name (default: 'password')\n"
        "Dann chainguard_login() erneut aufrufen.\n\n"
        "⚠️ finish() ist blockiert bis Login erfolgreich oder Alert cleared!"
    )


@handler.register("chainguard_set_base_url")
async def handle_set_base_url(args: Dict[str, Any]) -> List[TextContent]:
    """Set base URL for HTTP tests."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    base_url = args["base_url"].rstrip("/")
    state.http_base_url = base_url
    state.add_action(f"BASE_URL: {base_url[:30]}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="set_base_url",
            message="Base URL gesetzt",
            data={"base_url": base_url}
        ))

    return _text(f"✓ Base URL: {base_url}")


@handler.register("chainguard_clear_session")
async def handle_clear_session(args: Dict[str, Any]) -> List[TextContent]:
    """Clear stored session/cookies and base URL."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    http_session_manager.clear_session(state.project_id)
    state.http_credentials = {}
    state.http_base_url = ""  # v4.15.1: Also clear base URL
    state.add_action("SESSION: cleared")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="clear_session",
            message="Session und Base-URL gelöscht",
            data={"session_cleared": True, "base_url_cleared": True}
        ))

    return _text("✓ Session + Base-URL cleared")


# =============================================================================
# ANALYSIS HANDLERS
# =============================================================================

@handler.register("chainguard_analyze")
async def handle_analyze(args: Dict[str, Any]) -> List[TextContent]:
    """Pre-flight code analysis."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    target = args.get("target", "")

    if not target:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="analyze",
                message="target parameter required"
            ))
        return _text("❌ target parameter required")

    result = await CodeAnalyzer.analyze_file(target, state.project_path)
    state.add_action(f"ANALYZE: {Path(target).name}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        if result.get("error"):
            return _text(xml_error(
                tool="analyze",
                message=result["error"]
            ))

        data = {
            "file": Path(target).name,
            "metrics": {
                "loc": result.get("loc", 0),
                "code_lines": result.get("code_lines", 0),
                "functions": result.get("functions", 0),
                "classes": result.get("classes", 0),
                "complexity": result.get("complexity", 0)
            },
            "patterns": result.get("patterns", []),
            "hotspots": result.get("hotspots", [])[:3],
            "todos": result.get("todos", [])[:3]
        }
        if result.get("checklist"):
            data["checklist"] = result["checklist"]

        return _text(xml_success(
            tool="analyze",
            message=f"Analyse: {Path(target).name}",
            data=data
        ))

    output = CodeAnalyzer.format_output(result)
    return _text(output)


@handler.register("chainguard_finish")
async def handle_finish(args: Dict[str, Any]) -> List[TextContent]:
    """Complete task with full validation."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    force = args.get("force", False)
    confirmed = args.get("confirmed", False)

    # Run checklist if not done yet
    if state.scope and state.scope.checklist and not state.checklist_results:
        results = await ChecklistRunner.run_all_async(state.scope.checklist, state.project_path)
        state.checklist_results = results["results"]

    completion = state.get_completion_status()
    scope_desc = state.scope.description if state.scope else "Kein Scope definiert"

    # Calculate checklist stats
    checklist_passed = 0
    checklist_total = 0
    if state.checklist_results:
        checklist_passed = sum(1 for v in state.checklist_results.values() if v == "✓")
        checklist_total = len(state.checklist_results)

    blocking_issues = [i for i in completion["issues"] if i.get("blocking")]

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "task": scope_desc[:50],
            "criteria": {
                "done": completion['criteria_done'],
                "total": completion['criteria_total']
            }
        }

        if checklist_total > 0:
            data["checklist"] = {"passed": checklist_passed, "total": checklist_total}

        # Handle blocking issues
        if blocking_issues:
            data["blockers"] = [
                {"type": i.get("type", "unknown"), "message": i["message"]}
                for i in blocking_issues
            ]
            return _text(xml_blocked(
                tool="finish",
                message="HTTP-Tests sind Pflicht für Web-Dateien",
                blocker_type="http_test_required",
                blocker_data={"action": "chainguard_test_endpoint() ausführen"}
            ))

        # Handle non-complete without force
        if not completion["complete"] and not force:
            data["issues"] = [
                {"type": i.get("type", "unknown"), "message": i["message"]}
                for i in completion["issues"]
            ]
            data["hint"] = "force=true um trotzdem abzuschließen"
            return _text(xml_warning(
                tool="finish",
                message="Kann nicht abschließen - offene Punkte",
                data=data
            ))

        # Show impact check
        if not confirmed and not state.impact_check_pending:
            state.impact_check_pending = True
            state.add_action("FINISH: Impact-Check")
            await pm.save_async(state)

            data["impact_check"] = {
                "files_changed": state.changed_files[:10],
                "action_required": "chainguard_finish(confirmed=true)"
            }
            return _text(xml_info(
                tool="finish",
                message="Impact-Check - Bitte bestätigen",
                data=data
            ))

        # Complete
        if confirmed or force:
            state.impact_check_pending = False
            state.validations_passed += 1
            state.files_since_validation = 0
            state.phase = "done"
            state.last_validation = datetime.now().isoformat()

            if MEMORY_AVAILABLE:
                await _consolidate_session_learnings(state, scope_desc)

            # v6.4.1: Include symbol warnings in response with action-required
            if state.symbol_warnings:
                data["symbol_warnings"] = state.symbol_warnings[:10]  # Max 10
                data["symbol_warnings_count"] = len(state.symbol_warnings)
                data["action_required"] = {
                    "type": "symbol-check",
                    "message": "Potenzielle Halluzinationen gefunden - MÜSSEN geprüft werden!",
                    "instructions": [
                        "1. Existiert die Funktion? → Falls nein: Code korrigieren!",
                        "2. Ist es eine externe Library? → Falls ja: Import prüfen",
                        "3. False Positive? → Ignorieren und weitermachen"
                    ]
                }

            state.changed_files = []
            symbol_warnings_copy = state.symbol_warnings.copy()  # Keep for message
            state.symbol_warnings = []  # Clear after finish

            if force and not completion["complete"]:
                state.add_action("FINISH: FORCED")
                await pm.save_async(state, immediate=True)
                data["forced"] = True
                msg = "Task abgeschlossen (erzwungen)"
                if symbol_warnings_copy:
                    msg += f" - 🔴 AKTION ERFORDERLICH: {len(symbol_warnings_copy)} Halluzinationen prüfen!"
                return _text(xml_warning(
                    tool="finish",
                    message=msg,
                    data=data
                ))
            else:
                state.add_action("FINISH: CONFIRMED")
                await pm.save_async(state, immediate=True)
                msg = "Task erfolgreich abgeschlossen"
                if symbol_warnings_copy:
                    msg += f" - 🔴 AKTION ERFORDERLICH: {len(symbol_warnings_copy)} Halluzinationen prüfen!"
                return _text(xml_success(
                    tool="finish",
                    message=msg,
                    data=data
                ))

        # Waiting for confirmation
        data["waiting_for"] = "confirmed=true"
        return _text(xml_info(
            tool="finish",
            message="Impact-Check wurde angezeigt - bitte bestätigen",
            data=data
        ))

    # Legacy plain text response
    lines = []
    lines.append(f"## Task-Abschluss: {scope_desc}")
    lines.append("")
    lines.append(f"**Kriterien:** {completion['criteria_done']}/{completion['criteria_total']}")

    if checklist_total > 0:
        lines.append(f"**Checklist:** {checklist_passed}/{checklist_total}")

    if completion["issues"]:
        lines.append("")
        lines.append("**Offene Punkte:**")
        for issue in completion["issues"]:
            details = ""
            if "details" in issue and issue["details"]:
                details = f" ({', '.join(str(d)[:20] for d in issue['details'][:2])})"
            prefix = "🚫" if issue.get("blocking") else "-"
            lines.append(f"{prefix} {issue['message']}{details}")

            if issue.get("type") == "http_test":
                lines.append("  → Nutze: chainguard_set_base_url + chainguard_test_endpoint")
                lines.append("  → Dann: chainguard_login falls Auth nötig")
                if not issue.get("blocking"):
                    lines.append("  → Oder: chainguard_finish(force=true) um zu überspringen")

    if blocking_issues:
        lines.append("")
        lines.append("🚫 **BLOCKIERT** - HTTP-Tests sind Pflicht für Web-Dateien!")
        lines.append("   Führe mindestens einen chainguard_test_endpoint() aus.")
        return _text("\n".join(lines))

    if not completion["complete"] and not force:
        lines.append("")
        lines.append("✗ **Kann nicht abschließen** - offene Punkte beheben oder `force=true`")
        return _text("\n".join(lines))

    if not confirmed and not state.impact_check_pending:
        state.impact_check_pending = True
        state.add_action("FINISH: Impact-Check")
        await pm.save_async(state)

        lines.append("")
        lines.append("---")
        lines.append("")
        impact_msg = ImpactAnalyzer.format_impact_check(state.changed_files, scope_desc)
        lines.append(impact_msg)

        return _text("\n".join(lines))

    if confirmed or force:
        state.impact_check_pending = False
        state.validations_passed += 1
        state.files_since_validation = 0
        state.phase = "done"
        state.last_validation = datetime.now().isoformat()

        if MEMORY_AVAILABLE:
            await _consolidate_session_learnings(state, scope_desc)

        state.changed_files = []

        # v6.4.1: Show symbol warnings before completing
        symbol_warnings_copy = state.symbol_warnings.copy()
        state.symbol_warnings = []  # Clear after finish

        if symbol_warnings_copy:
            lines.append("")
            lines.append("<action-required type=\"symbol-check\">")
            lines.append(f"🔴 **AKTION ERFORDERLICH: {len(symbol_warnings_copy)} potenzielle Halluzinationen!**")
            lines.append("")
            lines.append("Diese Funktionen wurden NICHT im Projekt gefunden:")
            for warning in symbol_warnings_copy[:10]:  # Max 10
                lines.append(f"   • {warning}")
            if len(symbol_warnings_copy) > 10:
                lines.append(f"   ... und {len(symbol_warnings_copy) - 10} weitere")
            lines.append("")
            lines.append("**Du MUSST jetzt prüfen:**")
            lines.append("1. Existiert die Funktion? → Falls nein: Code korrigieren!")
            lines.append("2. Ist es eine externe Library? → Falls ja: Import prüfen")
            lines.append("3. False Positive? → Ignorieren und weitermachen")
            lines.append("")
            lines.append("⚠️ NICHT IGNORIEREN - Halluzinierte Funktionen führen zu Runtime-Fehlern!")
            lines.append("</action-required>")

        if force and not completion["complete"]:
            state.add_action("FINISH: FORCED")
            await pm.save_async(state, immediate=True)
            lines.append("")
            lines.append("⚠ **Task abgeschlossen (erzwungen)**")
        else:
            state.add_action("FINISH: CONFIRMED")
            await pm.save_async(state, immediate=True)
            lines.append("")
            lines.append("✓ **Task erfolgreich abgeschlossen!**")

        return _text("\n".join(lines))

    lines.append("")
    lines.append("⏳ **Impact-Check wurde angezeigt**")
    lines.append("→ Bitte mit `chainguard_finish(confirmed=true)` bestätigen")
    return _text("\n".join(lines))


# =============================================================================
# TEST RUNNER HANDLERS (v4.10)
# =============================================================================

@handler.register("chainguard_test_config")
async def handle_test_config(args: Dict[str, Any]) -> List[TextContent]:
    """Configure test command for project."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    command = args.get("command", "")
    test_args = args.get("args", "")
    timeout = args.get("timeout", 300)

    if not command:
        # Show current config
        if state.test_config:
            cfg = state.test_config

            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_info(
                    tool="test_config",
                    message="Aktuelle Test-Konfiguration",
                    data={
                        "command": cfg.get("command", "-"),
                        "args": cfg.get("args", "-"),
                        "timeout": cfg.get("timeout", 300)
                    }
                ))

            return _text(f"Test Config:\n  Command: {cfg.get('command', '-')}\n  Args: {cfg.get('args', '-')}\n  Timeout: {cfg.get('timeout', 300)}s")

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="test_config",
                message="Kein Test-Command konfiguriert",
                data={
                    "example": "chainguard_test_config(command=\"./vendor/bin/phpunit\", args=\"tests/\")"
                }
            ))

        return _text("Kein Test-Command konfiguriert.\n\nBeispiel:\nchainguard_test_config(\n  command=\"./vendor/bin/phpunit\",\n  args=\"tests/\"\n)")

    # Save config
    state.test_config = {
        "command": command,
        "args": test_args,
        "timeout": timeout
    }
    state.add_action(f"TEST_CFG: {command[:20]}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="test_config",
            message="Test-Config gespeichert",
            data={
                "command": command,
                "args": test_args,
                "timeout": timeout
            }
        ))

    return _text(f"✓ Test-Config gespeichert:\n  {command} {test_args}")


@handler.register("chainguard_run_tests")
async def handle_run_tests(args: Dict[str, Any]) -> List[TextContent]:
    """Run tests using configured command."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    # Check for config
    if not state.test_config or not state.test_config.get("command"):
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="run_tests",
                message="Kein Test-Command konfiguriert",
                blocker_type="test_config_required",
                blocker_data={"action": "chainguard_test_config(command=\"...\")"}
            ))
        return _text("✗ Kein Test-Command konfiguriert.\n\nZuerst: chainguard_test_config(command=\"...\")")

    # Build config
    config = TestConfig.from_dict(state.test_config)

    # Run tests
    result = await TestRunner.run_async(config, state.project_path)

    # Update state
    state.test_results = result.to_dict()
    state.last_test_run = datetime.now().isoformat()
    state.tests_passed = result.passed
    state.tests_failed = result.failed

    # Add action
    status = "PASS" if result.success else "FAIL"
    state.add_action(f"TEST: {status} {result.passed}/{result.total}")

    # Create alert on failure
    if not result.success and result.failed > 0:
        state.alerts.append({
            "msg": f"Tests fehlgeschlagen: {result.failed}/{result.total}",
            "ack": False,
            "ts": datetime.now().isoformat()
        })

    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "success": result.success,
            "passed": result.passed,
            "failed": result.failed,
            "total": result.total,
            "framework": result.framework or "unknown",
            "duration": result.duration
        }

        if result.error_lines:
            data["errors"] = result.error_lines[:5]

        if result.success:
            return _text(xml_success(
                tool="run_tests",
                message=f"Tests bestanden: {result.passed}/{result.total}",
                data=data
            ))
        else:
            return _text(xml_error(
                tool="run_tests",
                message=f"Tests fehlgeschlagen: {result.failed}/{result.total}",
                data=data
            ))

    # Legacy response
    return _text(TestRunner.format_result(result))


@handler.register("chainguard_test_status")
async def handle_test_status(args: Dict[str, Any]) -> List[TextContent]:
    """Show last test run status."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    if not state.test_results:
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="test_status",
                message="Keine Tests ausgeführt",
                data={"hint": "chainguard_run_tests()"}
            ))
        return _text("Keine Tests ausgeführt.\n\nNutze: chainguard_run_tests()")

    result = TestResult.from_dict(state.test_results)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "success": result.success,
            "passed": result.passed,
            "failed": result.failed,
            "total": result.total,
            "framework": result.framework or "unknown",
            "last_run": state.last_test_run
        }

        if result.error_lines:
            data["errors"] = result.error_lines[:3]

        if state.test_config:
            data["command"] = state.test_config.get("command", "-")

        return _text(xml_info(
            tool="test_status",
            message=f"Test Status: {'PASS' if result.success else 'FAIL'} {result.passed}/{result.total}",
            data=data
        ))

    # Legacy response
    status = TestRunner.format_status(result, state.last_test_run)

    lines = [f"Test Status: {status}"]

    if result.error_lines:
        lines.append("\nFehler:")
        for err in result.error_lines[:3]:
            lines.append(f"  • {err}")

    if state.test_config:
        lines.append(f"\nCommand: {state.test_config.get('command', '-')}")

    return _text("\n".join(lines))


# =============================================================================
# HISTORY / ERROR MEMORY HANDLERS (v4.11)
# =============================================================================

@handler.register("chainguard_recall")
async def handle_recall(args: Dict[str, Any]) -> List[TextContent]:
    """Search error history for similar issues and their resolutions."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    query = args.get("query", "")
    limit = args.get("limit", 5)

    if not query:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="recall",
                message="Query required",
                data={"example": 'chainguard_recall(query="php syntax Controller")'}
            ))
        return _text("⚠ Query required. Example: chainguard_recall(query=\"php syntax Controller\")")

    # Search error index
    results = await HistoryManager.recall(
        project_id=state.project_id,
        query=query,
        limit=limit
    )

    if not results:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="recall",
                message=f"Keine Eintraege fuer '{query}' gefunden",
                data={"query": query, "results": []}
            ))
        return _text(f"Keine Einträge für '{query}' gefunden.")

    # Build results list
    results_data = []
    lines = [f"🔍 {len(results)} Ergebnis(se) für '{query}':", ""]

    for i, entry in enumerate(results, 1):
        # Time ago
        try:
            ts = datetime.fromisoformat(entry.ts)
            days_ago = (datetime.now() - ts).days
            if days_ago == 0:
                time_str = "heute"
            elif days_ago == 1:
                time_str = "gestern"
            else:
                time_str = f"vor {days_ago}d"
        except ValueError:
            time_str = entry.ts[:10]

        # For XML
        results_data.append({
            "file_pattern": entry.file_pattern,
            "error_type": entry.error_type,
            "error_msg": entry.error_msg[:80],
            "resolution": entry.resolution or None,
            "time_ago": time_str,
            "scope": entry.scope_desc[:40] if entry.scope_desc else None
        })

        # For legacy
        lines.append(f"{i}. **{entry.file_pattern}** ({time_str})")
        lines.append(f"   Type: {entry.error_type}")
        lines.append(f"   Error: {entry.error_msg[:60]}...")

        if entry.resolution:
            lines.append(f"   ✓ Fix: {entry.resolution}")
        else:
            lines.append(f"   ? Kein Fix dokumentiert")

        if entry.scope_desc:
            lines.append(f"   Scope: {entry.scope_desc[:40]}")
        lines.append("")

    state.add_action(f"RECALL: {query[:20]}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="recall",
            message=f"{len(results)} Ergebnis(se) fuer '{query}'",
            data={"query": query, "count": len(results), "results": results_data}
        ))

    return _text("\n".join(lines))


@handler.register("chainguard_history")
async def handle_history(args: Dict[str, Any]) -> List[TextContent]:
    """View recent change history for the current project."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    limit = args.get("limit", 20)
    scope_only = args.get("scope_only", False)

    scope_id = None
    if scope_only and state.scope:
        scope_id = state.scope.created_at

    entries = await HistoryManager.get_history(
        project_id=state.project_id,
        limit=limit,
        scope_id=scope_id
    )

    if not entries:
        return _text("Keine History-Einträge vorhanden.")

    # Build entries data for any format
    entries_data = []
    for entry in entries[:limit]:
        ts_short = entry.ts[11:16] if len(entry.ts) > 16 else entry.ts[:5]
        file_short = Path(entry.file).name if entry.file else "?"
        status = "ok" if entry.validation == "PASS" else "err"
        entries_data.append({
            "time": ts_short,
            "file": file_short,
            "action": entry.action,
            "status": status
        })

    # v6.0: TOON Response (30-60% token savings on arrays)
    if TOON_ENABLED:
        return _text(toon_history(entries_data))

    # v6.0: XML Response (disabled by default)
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="history",
            message=f"{len(entries)} Eintraege" + (" (aktueller Scope)" if scope_only else ""),
            data={
                "count": len(entries),
                "scope_only": scope_only,
                "entries": entries_data
            }
        ))

    # Legacy
    lines = [f"📜 {len(entries)} Einträge" + (" (aktueller Scope)" if scope_only else ""), ""]
    for e in entries_data:
        lines.append(f"{e['time']} {e['action']:6} {e['file']:20} {'✓' if e['status'] == 'ok' else '✗'}")
    return _text("\n".join(lines))


@handler.register("chainguard_learn")
async def handle_learn(args: Dict[str, Any]) -> List[TextContent]:
    """Document a fix/resolution for the most recent error."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    resolution = args.get("resolution", "")
    file_pattern = args.get("file_pattern", "")
    error_type = args.get("error_type", "")

    if not resolution:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="learn",
                message="resolution required",
                data={"example": 'chainguard_learn(resolution="Missing semicolon before }")'}
            ))
        return _text("⚠ resolution required. Example: chainguard_learn(resolution=\"Missing semicolon before }\")")

    # If no specific pattern given, try to find the most recent error
    if not file_pattern or not error_type:
        # Look for recent syntax errors in alerts
        recent_errors = [a for a in state.alerts if "errors" in a and not a.get("ack")]
        if recent_errors:
            last_error = recent_errors[-1]
            if "errors" in last_error and last_error["errors"]:
                err = last_error["errors"][0]
                error_type = error_type or err.get("type", "")
                file = err.get("file", "")
                if file:
                    # HistoryManager is already imported at module level
                    file_pattern = file_pattern or HistoryManager._extract_pattern(Path(file).name)

    if not file_pattern or not error_type:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="learn",
                message="Kein kuerzlicher Fehler gefunden",
                data={
                    "hint": "Bitte file_pattern und error_type angeben",
                    "required_params": ["file_pattern", "error_type"]
                }
            ))
        return _text("⚠ Kein kürzlicher Fehler gefunden. Bitte file_pattern und error_type angeben.")

    # Update the error index with the resolution
    success = await HistoryManager.update_resolution(
        project_id=state.project_id,
        file_pattern=file_pattern,
        error_type=error_type,
        resolution=resolution
    )

    if success:
        state.add_action(f"LEARN: {resolution[:20]}")
        await pm.save_async(state)

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="learn",
                message="Resolution dokumentiert",
                data={
                    "file_pattern": file_pattern,
                    "error_type": error_type,
                    "resolution": resolution
                }
            ))
        return _text(f"✓ Resolution dokumentiert:\n   {file_pattern} ({error_type})\n   → {resolution}")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_warning(
            tool="learn",
            message=f"Kein passender Fehler gefunden fuer {file_pattern} / {error_type}",
            data={"file_pattern": file_pattern, "error_type": error_type}
        ))
    return _text(f"⚠ Kein passender Fehler gefunden für {file_pattern} / {error_type}")


# =============================================================================
# DATABASE INSPECTOR HANDLERS (v4.12)
# =============================================================================

@handler.register("chainguard_db_connect")
async def handle_db_connect(args: Dict[str, Any]) -> List[TextContent]:
    """Connect to database for schema inspection.

    v6.4: Supports persistent credentials per project.
    - If no credentials given, tries to load saved credentials
    - On success, saves credentials for next session
    - On failure with saved credentials, deletes them (may be outdated)
    """
    from .db_credentials import get_credential_store

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    remember = args.get("remember", True)  # Default: save credentials

    # Check if new credentials provided
    user = args.get("user", "")
    password = args.get("password", "")
    database = args.get("database", "")

    used_saved = False
    config = None

    if not user and not database:
        # Try to load saved credentials
        store = get_credential_store()
        saved = store.load(working_dir)

        if saved:
            config = saved
            used_saved = True
        else:
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="db_connect",
                    message="Keine Credentials. user + database angeben.",
                    data={"hint": "Gib user, password, database an. Nach Erfolg werden sie gespeichert."}
                ))
            return _text("⚠ Keine Credentials. user + database angeben.")
    else:
        # Use provided credentials
        config = DBConfig(
            host=args.get("host", "localhost"),
            port=args.get("port", 3306),
            user=user,
            password=password,
            database=database,
            db_type=args.get("db_type", "mysql")
        )

        if not config.user or not config.database:
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="db_connect",
                    message="user und database sind erforderlich",
                    data={"required_params": ["user", "database"]}
                ))
            return _text("⚠ user und database sind erforderlich")

    inspector = get_inspector(state.project_id)
    result = await inspector.connect(config)

    if result["success"]:
        # Store config reference in state (not credentials!)
        state.db_config = {
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "db_type": config.db_type,
            "connected": True
        }
        state.add_action(f"DB: {config.database}")
        await pm.save_async(state)

        # Save credentials after successful connection (if new credentials provided)
        saved_msg = ""
        if remember and not used_saved:
            store = get_credential_store()
            if store.save(working_dir, config):
                saved_msg = " (Credentials gespeichert)"

        version = result.get("version", "")

        # Build response message
        if used_saved:
            base_msg = f"Verbunden mit gespeicherten Credentials ({config.database})"
        else:
            base_msg = f"Verbunden mit {config.database}"

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="db_connect",
                message=base_msg + saved_msg,
                data={
                    "database": config.database,
                    "db_type": config.db_type,
                    "version": version,
                    "host": config.host,
                    "used_saved_credentials": used_saved,
                    "credentials_saved": bool(saved_msg)
                }
            ))

        return _text(f"✓ {base_msg} ({config.db_type} {version}){saved_msg}")

    # Connection failed
    # If we used saved credentials, they might be outdated - delete them
    if used_saved:
        store = get_credential_store()
        store.delete(working_dir)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_error(
            tool="db_connect",
            message="Verbindung fehlgeschlagen",
            data={
                "error": result.get("message", "Unknown error"),
                "used_saved_credentials": used_saved,
                "saved_credentials_deleted": used_saved
            }
        ))

    error_msg = f"✗ Connection failed: {result.get('message', 'Unknown error')}"
    if used_saved:
        error_msg += " (gespeicherte Credentials gelöscht)"
    return _text(error_msg)


@handler.register("chainguard_db_schema")
async def handle_db_schema(args: Dict[str, Any]) -> List[TextContent]:
    """Get database schema with caching."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    refresh = args.get("refresh", False)

    inspector = get_inspector(state.project_id)

    if not inspector.is_connected():
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="db_schema",
                message="Keine DB verbunden",
                blocker_type="db_not_connected",
                blocker_data={"action": "chainguard_db_connect(...)"}
            ))
        return _text("✗ Keine DB verbunden. Zuerst: chainguard_db_connect(...)")

    schema = await inspector.get_schema(force_refresh=refresh)

    if not schema:
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="db_schema",
                message="Schema konnte nicht geladen werden"
            ))
        return _text("✗ Schema konnte nicht geladen werden")

    # v4.18: Mark schema as checked with timestamp (enables TTL-based validation)
    state.set_schema_checked()
    state.add_action(f"SCHEMA: {len(schema.tables)} tables")
    # v4.19: immediate=True for enforcement-state sync (critical for PreToolUse hook)
    await pm.save_async(state, immediate=True)

    # v6.0: XML Response - schema is already formatted text, include as-is
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="db_schema",
            message=f"Schema mit {len(schema.tables)} Tabellen",
            data={
                "table_count": len(schema.tables),
                "refreshed": refresh,
                "schema_text": inspector.format_schema(schema)
            }
        ))

    return _text(inspector.format_schema(schema))


@handler.register("chainguard_db_table")
async def handle_db_table(args: Dict[str, Any]) -> List[TextContent]:
    """Get detailed info for a single table."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    table = args.get("table", "")
    sample = args.get("sample", False)

    if not table:
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="db_table",
                message="table parameter erforderlich"
            ))
        return _text("⚠ table parameter erforderlich")

    inspector = get_inspector(state.project_id)

    if not inspector.is_connected():
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="db_table",
                message="Keine DB verbunden",
                blocker_type="db_not_connected",
                blocker_data={"action": "chainguard_db_connect(...)"}
            ))
        return _text("✗ Keine DB verbunden. Zuerst: chainguard_db_connect(...)")

    details = await inspector.get_table_details(table, show_sample=sample)

    if not details:
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="db_table",
                message=f"Tabelle '{table}' nicht gefunden",
                data={"table": table}
            ))
        return _text(f"✗ Tabelle '{table}' nicht gefunden")

    state.add_action(f"TABLE: {table}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="db_table",
            message=f"Tabellendetails für {table}",
            data={
                "table": table,
                "include_sample": sample,
                "details_text": details
            }
        ))

    return _text(details)


@handler.register("chainguard_db_disconnect")
async def handle_db_disconnect(args: Dict[str, Any]) -> List[TextContent]:
    """Disconnect from database and clear cache."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    clear_inspector(state.project_id)
    state.db_config = {}
    state.add_action("DB: disconnected")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="db_disconnect",
            message="Datenbankverbindung getrennt",
            data={"disconnected": True, "cache_cleared": True}
        ))

    return _text("✓ Datenbankverbindung getrennt, Cache gelöscht")


@handler.register("chainguard_db_forget")
async def handle_db_forget(args: Dict[str, Any]) -> List[TextContent]:
    """Delete saved DB credentials for this project (v6.4)."""
    from .db_credentials import get_credential_store

    working_dir = args.get("working_dir")

    store = get_credential_store()
    info = store.get_info(working_dir)

    if store.delete(working_dir):
        db_name = info.get('database', 'unknown') if info else 'unknown'

        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="db_forget",
                message=f"Credentials für {db_name} gelöscht",
                data={"deleted": True, "database": db_name}
            ))

        return _text(f"✓ DB-Credentials gelöscht ({db_name})")
    else:
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="db_forget",
                message="Keine gespeicherten Credentials gefunden",
                data={"deleted": False}
            ))

        return _text("ℹ Keine gespeicherten Credentials für dieses Projekt")


# =============================================================================
# MODE-SPECIFIC HANDLERS (v5.0)
# =============================================================================

# -----------------------------------------------------------------------------
# CONTENT MODE HANDLERS
# -----------------------------------------------------------------------------

@handler.register("chainguard_word_count")
async def handle_word_count(args: Dict[str, Any]) -> List[TextContent]:
    """Get word count statistics (CONTENT mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    file = args.get("file")

    if file:
        # Count words in specific file
        try:
            file_path = Path(state.project_path) / file if not Path(file).is_absolute() else Path(file)
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                word_count = len(content.split())
                # v6.0: XML Response
                if XML_RESPONSES_ENABLED:
                    return _text(xml_info(
                        tool="word_count",
                        message=f"{file}: {word_count} words",
                        data={"file": file, "words": word_count}
                    ))
                return _text(f"📝 {file}: {word_count} words")
            else:
                # v6.0: XML Response
                if XML_RESPONSES_ENABLED:
                    return _text(xml_warning(
                        tool="word_count",
                        message=f"File not found: {file}"
                    ))
                return _text(f"⚠ File not found: {file}")
        except Exception as e:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="word_count",
                    message=f"Error reading file: {str(e)[:50]}"
                ))
            return _text(f"⚠ Error reading file: {str(e)[:50]}")

    # Show overall statistics
    chapters_done = sum(1 for s in state.chapter_status.values() if s == "done")
    chapters_draft = sum(1 for s in state.chapter_status.values() if s == "draft")
    chapters_review = sum(1 for s in state.chapter_status.values() if s == "review")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="word_count",
            message="Word Count Statistics",
            data={
                "total_words": state.word_count_total,
                "chapters": state.chapter_status,
                "progress": {
                    "done": chapters_done,
                    "review": chapters_review,
                    "draft": chapters_draft
                }
            }
        ))

    lines = ["📊 **Word Count Statistics**", ""]
    lines.append(f"Total: **{state.word_count_total}** words")
    lines.append("")

    if state.chapter_status:
        lines.append("**Chapters:**")
        for chapter, status in state.chapter_status.items():
            icon = {"done": "✓", "review": "👁", "draft": "✏"}.get(status, "?")
            lines.append(f"  {icon} {chapter}: {status}")
        lines.append("")
        lines.append(f"Progress: {chapters_done} done, {chapters_review} review, {chapters_draft} draft")

    return _text("\n".join(lines))


@handler.register("chainguard_track_chapter")
async def handle_track_chapter(args: Dict[str, Any]) -> List[TextContent]:
    """Track chapter progress (CONTENT mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    chapter = args["chapter"]
    status = args["status"]
    word_count = args.get("word_count")

    state.set_chapter_status(chapter, status)

    if word_count:
        # Update total word count (simplistic - add if new, assume same if updating)
        state.word_count_total += word_count

    state.add_action(f"CHAPTER: {chapter}={status}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="track_chapter",
            message=f"Chapter '{chapter}': {status}",
            data={
                "chapter": chapter,
                "status": status,
                "words": word_count
            }
        ))

    icon = {"done": "✓", "review": "👁", "draft": "✏"}.get(status, "?")
    result = f"{icon} Chapter '{chapter}': {status}"
    if word_count:
        result += f" ({word_count} words)"

    return _text(result)


# -----------------------------------------------------------------------------
# DEVOPS MODE HANDLERS
# -----------------------------------------------------------------------------

@handler.register("chainguard_log_command")
async def handle_log_command(args: Dict[str, Any]) -> List[TextContent]:
    """Log executed command (DEVOPS mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    command = args["command"]
    result = args.get("result", "success")
    output = args.get("output", "")

    state.add_command(command, result, output)
    state.add_action(f"CMD: {command[:20]}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="log_command",
            message=f"Logged: {command[:50]}",
            data={"command": command[:100], "result": result}
        ))

    icon = "✓" if result == "success" else "✗"
    return _text(f"{icon} Logged: {command[:50]}")


@handler.register("chainguard_checkpoint")
async def handle_checkpoint(args: Dict[str, Any]) -> List[TextContent]:
    """Create rollback checkpoint (DEVOPS mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    name = args["name"]
    files = args.get("files", [])

    state.add_checkpoint(name, files)
    state.add_action(f"CHECKPOINT: {name}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="checkpoint",
            message=f"Checkpoint created: {name}",
            data={
                "name": name,
                "files": files[:10],
                "total_checkpoints": len(state.checkpoints)
            }
        ))

    lines = [f"💾 Checkpoint created: **{name}**"]
    if files:
        lines.append(f"   Files: {', '.join(files[:5])}")
        if len(files) > 5:
            lines.append(f"   +{len(files) - 5} more")
    lines.append(f"   Total checkpoints: {len(state.checkpoints)}")

    return _text("\n".join(lines))


@handler.register("chainguard_health_check")
async def handle_health_check(args: Dict[str, Any]) -> List[TextContent]:
    """Run health checks (DEVOPS mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    endpoints = args.get("endpoints", [])
    services = args.get("services", [])

    results = []
    results_data = []

    # Check endpoints
    if endpoints:
        for url in endpoints[:10]:  # Limit to 10
            try:
                # Use http_session_manager for endpoint checks
                result = await http_session_manager.test_endpoint(
                    url=url, method="GET", project_id=state.project_id
                )
                status = "✓" if result["success"] else "✗"
                code = result.get("status_code", "?")
                results.append(f"{status} {url}: {code}")
                results_data.append({"type": "endpoint", "target": url, "status": code, "ok": result["success"]})
            except Exception as e:
                results.append(f"✗ {url}: {str(e)[:30]}")
                results_data.append({"type": "endpoint", "target": url, "status": "error", "ok": False})

    # Check services (Linux systemd)
    if services:
        import asyncio
        for service in services[:10]:  # Limit to 10
            try:
                proc = await asyncio.create_subprocess_exec(
                    "systemctl", "is-active", service,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                status_str = stdout.decode().strip()
                icon = "✓" if status_str == "active" else "✗"
                results.append(f"{icon} {service}: {status_str}")
                results_data.append({"type": "service", "target": service, "status": status_str, "ok": status_str == "active"})
            except Exception:
                results.append(f"? {service}: unknown")
                results_data.append({"type": "service", "target": service, "status": "unknown", "ok": False})

    state.add_action(f"HEALTH: {len(endpoints)}e/{len(services)}s")
    await pm.save_async(state)

    if not results:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="health_check",
                message="No endpoints or services specified"
            ))
        return _text("⚠ No endpoints or services specified")

    # Summary
    ok_count = sum(1 for r in results if r.startswith("✓"))
    total = len(results)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="health_check",
            message=f"Health Check: {ok_count}/{total} OK",
            data={
                "ok_count": ok_count,
                "total": total,
                "results": results_data
            }
        ))

    lines = [f"🏥 **Health Check: {ok_count}/{total} OK**", ""]
    lines.extend(results)

    return _text("\n".join(lines))


# -----------------------------------------------------------------------------
# RESEARCH MODE HANDLERS
# -----------------------------------------------------------------------------

@handler.register("chainguard_add_source")
async def handle_add_source(args: Dict[str, Any]) -> List[TextContent]:
    """Track research source (RESEARCH mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    url = args["url"]
    title = args.get("title", "")
    relevance = args.get("relevance", "medium")

    state.add_source(url, title, relevance)
    state.add_action(f"SOURCE: {title[:20] or url[:20]}")
    await pm.save_async(state)

    icon = {"high": "⭐", "medium": "📄", "low": "📎"}.get(relevance, "📄")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="add_source",
            message=f"Source added ({relevance})",
            data={
                "url": url,
                "title": title or url[:40],
                "relevance": relevance,
                "total_sources": len(state.sources)
            }
        ))

    return _text(f"{icon} Source added: {title or url[:40]} ({relevance})")


@handler.register("chainguard_index_fact")
async def handle_index_fact(args: Dict[str, Any]) -> List[TextContent]:
    """Index discovered fact (RESEARCH mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    fact = args["fact"]
    source = args.get("source", "")
    confidence = args.get("confidence", "likely")

    state.add_fact(fact, source, confidence)
    state.add_action(f"FACT: {fact[:20]}")
    await pm.save_async(state)

    icon = {"verified": "✓", "likely": "○", "uncertain": "?"}.get(confidence, "○")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="index_fact",
            message=f"Fact indexed ({confidence})",
            data={
                "fact": fact,
                "source": source or None,
                "confidence": confidence,
                "total_facts": len(state.facts)
            }
        ))

    result = f"{icon} Fact indexed ({confidence}): {fact[:60]}"
    if source:
        result += f"\n   Source: {source[:40]}"

    return _text(result)


@handler.register("chainguard_sources")
async def handle_sources(args: Dict[str, Any]) -> List[TextContent]:
    """List all tracked sources (RESEARCH mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    if not state.sources:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="sources",
                message="No sources tracked yet",
                data={"hint": "chainguard_add_source(url=\"...\")"}
            ))
        return _text("📚 No sources tracked yet.\n\nUse: chainguard_add_source(url=\"...\")")

    # Group by relevance
    high = [s for s in state.sources if s.get("relevance") == "high"]
    medium = [s for s in state.sources if s.get("relevance") == "medium"]
    low = [s for s in state.sources if s.get("relevance") == "low"]

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        sources_data = {
            "total": len(state.sources),
            "by_relevance": {
                "high": [{"url": s.get("url"), "title": s.get("title")} for s in high],
                "medium": [{"url": s.get("url"), "title": s.get("title")} for s in medium],
                "low": [{"url": s.get("url"), "title": s.get("title")} for s in low]
            }
        }
        return _text(xml_info(
            tool="sources",
            message=f"{len(state.sources)} Sources",
            data=sources_data
        ))

    lines = [f"📚 **{len(state.sources)} Sources**", ""]

    if high:
        lines.append("⭐ **High Relevance:**")
        for s in high[:5]:
            title = s.get("title") or s.get("url", "")[:40]
            lines.append(f"   • {title}")
        lines.append("")

    if medium:
        lines.append("📄 **Medium Relevance:**")
        for s in medium[:5]:
            title = s.get("title") or s.get("url", "")[:40]
            lines.append(f"   • {title}")
        lines.append("")

    if low:
        lines.append(f"📎 Low Relevance: {len(low)} sources")

    return _text("\n".join(lines))


@handler.register("chainguard_facts")
async def handle_facts(args: Dict[str, Any]) -> List[TextContent]:
    """List all indexed facts (RESEARCH mode)."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    if not state.facts:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="facts",
                message="No facts indexed yet",
                data={"hint": "chainguard_index_fact(fact=\"...\")"}
            ))
        return _text("🔬 No facts indexed yet.\n\nUse: chainguard_index_fact(fact=\"...\")")

    # Group by confidence
    verified = [f for f in state.facts if f.get("confidence") == "verified"]
    likely = [f for f in state.facts if f.get("confidence") == "likely"]
    uncertain = [f for f in state.facts if f.get("confidence") == "uncertain"]

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        facts_data = {
            "total": len(state.facts),
            "by_confidence": {
                "verified": [{"fact": f.get("fact"), "source": f.get("source")} for f in verified],
                "likely": [{"fact": f.get("fact"), "source": f.get("source")} for f in likely],
                "uncertain": [{"fact": f.get("fact"), "source": f.get("source")} for f in uncertain]
            }
        }
        return _text(xml_info(
            tool="facts",
            message=f"{len(state.facts)} Facts",
            data=facts_data
        ))

    lines = [f"🔬 **{len(state.facts)} Facts**", ""]

    if verified:
        lines.append("✓ **Verified:**")
        for f in verified[:5]:
            lines.append(f"   • {f.get('fact', '')[:60]}")
        lines.append("")

    if likely:
        lines.append("○ **Likely:**")
        for f in likely[:5]:
            lines.append(f"   • {f.get('fact', '')[:60]}")
        lines.append("")

    if uncertain:
        lines.append(f"? Uncertain: {len(uncertain)} facts")

    return _text("\n".join(lines))


# =============================================================================
# MEMORY HANDLERS (v5.1 - Long-Term Memory)
# =============================================================================

@handler.register("chainguard_memory_init")
async def handle_memory_init(args: Dict[str, Any]) -> List[TextContent]:
    """Initialize project memory with full code indexing."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_init",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    include_patterns = args.get("include_patterns", ["**/*.py", "**/*.php", "**/*.js", "**/*.ts", "**/*.tsx"])
    exclude_patterns = args.get("exclude_patterns", ["node_modules", "vendor", ".git", "__pycache__", "*.min.js"])
    force = args.get("force", False)

    project_id = get_project_id(state.project_path)

    # Check if memory already exists
    if await memory_manager.memory_exists(project_id) and not force:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="memory_init",
                message=f"Memory bereits initialisiert fuer {state.project_name}",
                data={
                    "project": state.project_name,
                    "hint": "force=true zum Neuinitialisieren oder memory_query() zum Suchen"
                }
            ))
        return _text(
            f"✓ Memory bereits initialisiert für {state.project_name}\n"
            "→ Nutze force=true zum Neuinitialisieren\n"
            "→ Oder chainguard_memory_query() zum Suchen"
        )

    memory = await memory_manager.get_memory(project_id, state.project_path)

    # Index project files
    indexed_files = 0
    indexed_functions = 0
    errors = []

    project_path = Path(state.project_path)

    for pattern in include_patterns:
        try:
            for file_path in project_path.glob(pattern):
                # Skip excluded patterns
                path_str = str(file_path)
                if any(excl in path_str for excl in exclude_patterns):
                    continue

                # Skip sensitive files
                if not should_index_file(path_str):
                    continue

                # Skip if not a file
                if not file_path.is_file():
                    continue

                try:
                    # Read file content
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if not content.strip():
                        continue

                    # Create document for file
                    relative_path = str(file_path.relative_to(project_path))
                    file_summary = _create_file_summary(file_path, content)

                    await memory.add(
                        content=file_summary,
                        collection="code_structure",
                        metadata={
                            "type": "file",
                            "path": relative_path,
                            "language": file_path.suffix.lstrip('.'),
                            "lines": len(content.splitlines()),
                        },
                        doc_id=f"file:{relative_path}"
                    )
                    indexed_files += 1

                    # Extract functions/classes using AST-Analyzer
                    functions = _extract_functions(content, file_path.suffix, str(file_path))
                    for func in functions:
                        # ChromaDB doesn't accept None values in metadata
                        await memory.add(
                            content=func["description"],
                            collection="functions",
                            metadata={
                                "type": func["type"],
                                "name": func["name"],
                                "path": relative_path,
                                "params": ",".join(func.get("params", [])),  # Join list to string
                                "signature": func.get("signature") or "",
                                "parent": func.get("parent") or "",
                                "return_type": func.get("return_type") or "",
                                "line_start": func.get("line_start", 0),
                            },
                            doc_id=f"func:{relative_path}:{func['name']}"
                        )
                        indexed_functions += 1

                    # v5.4: Create deep logic summary using CodeSummarizer
                    if SUMMARIZER_AVAILABLE and code_summarizer:
                        try:
                            summary = code_summarizer.summarize_file(file_path, content)
                            summary_text = summary.to_text(max_length=2000)

                            if summary_text.strip():
                                await memory.add(
                                    content=summary_text,
                                    collection="code_summaries",
                                    metadata={
                                        "type": "logic_summary",
                                        "path": relative_path,
                                        "language": summary.language,
                                        "purpose": summary.purpose[:200] if summary.purpose else "",
                                        "class_count": len(summary.classes),
                                        "function_count": len(summary.functions),
                                    },
                                    doc_id=f"summary:{relative_path}"
                                )
                        except Exception as sum_err:
                            logger.debug(f"Summary error for {relative_path}: {sum_err}")

                except Exception as e:
                    errors.append(f"{file_path.name}: {str(e)[:30]}")

        except Exception as e:
            errors.append(f"Pattern {pattern}: {str(e)[:30]}")

    # Save metadata
    await memory.save_metadata(
        initialized_at=datetime.now().isoformat(),
        indexed_files=indexed_files,
        indexed_functions=indexed_functions,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns
    )

    # v5.4: Auto-detect and store architecture
    architecture_indexed = False
    try:
        from .architecture import architecture_detector
        analysis = architecture_detector.analyze(state.project_path)

        # Always store main architecture info (even with low confidence)
        arch_content = (
            f"Project architecture: {analysis.pattern.value}. "
            f"Framework: {analysis.framework.value if analysis.framework else 'unknown'}. "
            f"Detected layers: {', '.join(analysis.detected_layers[:5]) if analysis.detected_layers else 'none'}. "
            f"Design patterns: {', '.join(analysis.detected_patterns[:5]) if analysis.detected_patterns else 'none'}."
        )
        await memory.upsert(
            content=arch_content,
            collection="architecture",
            metadata={
                "type": "architecture",
                "name": "project_architecture",
                "pattern": analysis.pattern.value,
                "framework": analysis.framework.value if analysis.framework else "",
                "confidence": analysis.confidence,
                "layers": ",".join(analysis.detected_layers[:10]) if analysis.detected_layers else "",
                "design_patterns": ",".join(analysis.detected_patterns[:10]) if analysis.detected_patterns else "",
            },
            doc_id="arch:main"
        )
        architecture_indexed = True

        # Store each detected layer as separate document for better search
        for layer in analysis.detected_layers[:10]:
            layer_content = f"Architecture layer: {layer} in {analysis.pattern.value} pattern."
            await memory.upsert(
                content=layer_content,
                collection="architecture",
                metadata={
                    "type": "layer",
                    "name": layer,
                    "pattern": analysis.pattern.value,
                },
                doc_id=f"arch:layer:{layer.lower()}"
            )

        # Store design patterns (always, even with low architecture confidence)
        for pattern in analysis.detected_patterns[:10]:
            pattern_content = f"Design pattern: {pattern} detected in codebase."
            await memory.upsert(
                content=pattern_content,
                collection="architecture",
                metadata={
                    "type": "design_pattern",
                    "name": pattern,
                },
                doc_id=f"arch:pattern:{pattern.lower()}"
            )
    except Exception as e:
        errors.append(f"Architecture detection: {str(e)[:30]}")

    state.add_action(f"MEMORY_INIT: {indexed_files}f/{indexed_functions}fn")
    await pm.save_async(state)

    # Get stats
    stats = await memory.get_stats()

    # Count summaries
    summaries_count = stats.collections.get("code_summaries", 0)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        data = {
            "project": state.project_name,
            "indexed": {
                "files": indexed_files,
                "functions": indexed_functions,
                "summaries": summaries_count,
                "total_documents": stats.total_documents
            },
            "storage_mb": round(stats.storage_size_mb, 1)
        }
        if architecture_indexed:
            data["architecture"] = {
                "pattern": analysis.pattern.value,
                "confidence": round(analysis.confidence, 2)
            }
        if errors:
            data["errors"] = errors[:3]

        return _text(xml_success(
            tool="memory_init",
            message=f"Memory initialisiert fuer {state.project_name}",
            data=data
        ))

    lines = [f"✓ Memory initialisiert für: {state.project_name}", ""]
    lines.append("📊 **Indexiert:**")
    lines.append(f"   - {indexed_files} Dateien")
    lines.append(f"   - {indexed_functions} Funktionen/Methoden")
    if summaries_count > 0:
        lines.append(f"   - {summaries_count} Code-Logik-Summaries")
    if architecture_indexed:
        lines.append(f"   - Architecture: {analysis.pattern.value} ({analysis.confidence:.0%})")
    lines.append(f"   - {stats.total_documents} Dokumente total")
    lines.append("")
    lines.append(f"💾 Speicher: {stats.storage_size_mb:.1f} MB")

    if errors:
        lines.append("")
        lines.append(f"⚠ {len(errors)} Fehler beim Indexieren")
        for err in errors[:3]:
            lines.append(f"   - {err}")

    lines.append("")
    lines.append("→ Nutze chainguard_memory_query() für semantische Suchen")

    return _text("\n".join(lines))


@handler.register("chainguard_memory_query")
async def handle_memory_query(args: Dict[str, Any]) -> List[TextContent]:
    """Semantic search in project memory."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_query",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    query = args.get("query", "")
    limit = args.get("limit", 5)
    filter_type = args.get("filter_type", "all")

    if not query:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="memory_query",
                message="query required",
                data={"example": 'chainguard_memory_query(query="Where is authentication handled?")'}
            ))
        return _text("⚠ query required. Example: chainguard_memory_query(query=\"Where is authentication handled?\")")

    project_id = get_project_id(state.project_path)

    if not await memory_manager.memory_exists(project_id):
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="memory_query",
                message="Memory nicht initialisiert",
                blocker_type="memory_not_initialized",
                blocker_data={"action": "chainguard_memory_init()"}
            ))
        return _text(
            "✗ Memory nicht initialisiert.\n"
            "→ Zuerst: chainguard_memory_init()"
        )

    memory = await memory_manager.get_memory(project_id, state.project_path)

    # Map filter_type to collection
    collection = "all"
    if filter_type == "code":
        collection = "code_structure"
    elif filter_type == "functions":
        collection = "functions"
    elif filter_type == "database":
        collection = "database_schema"
    elif filter_type == "architecture":
        collection = "architecture"

    # Query memory
    results = await memory.query(
        query_text=query,
        collection=collection,
        n_results=limit * 2  # Get more, then filter by score
    )

    if not results:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="memory_query",
                message=f"Keine Ergebnisse fuer: {query}",
                data={"query": query, "results": []}
            ))
        return _text(f"🔍 Keine Ergebnisse für: \"{query}\"")

    # Extract keywords for scoring
    keywords = KeywordExtractor.extract(query)
    task_type = detect_task_type(query)

    # Score and sort results
    scored_results = []
    for doc, distance in results:
        scored = RelevanceScorer.score(
            document=doc,
            semantic_distance=distance,
            keywords=keywords,
            task_type=task_type,
            collection=doc.metadata.get("_collection", "unknown")
        )
        scored_results.append(scored)

    scored_results.sort(key=lambda x: x.final_score, reverse=True)

    # Build results data for XML
    results_data = []
    lines = [f"🔍 Query: \"{query}\"", ""]
    lines.append(f"📍 **Relevante Stellen (Top {min(limit, len(scored_results))}):**")
    lines.append("")

    for i, result in enumerate(scored_results[:limit], 1):
        doc = result.document
        score = result.final_score
        path = doc.metadata.get("path", doc.metadata.get("name", "unknown"))
        summary = ContextFormatter._get_summary(doc)

        # For XML
        results_data.append({
            "path": path,
            "score": round(score, 2),
            "summary": summary[:100] if summary else None
        })

        # For legacy
        lines.append(f"{i}. [{score:.2f}] **{path}**")
        if summary:
            lines.append(f"   └─ {summary}")
        lines.append("")

    state.add_action(f"QUERY: {query[:20]}")
    await pm.save_async(state)

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="memory_query",
            message=f"{len(results_data)} Ergebnis(se) fuer: {query}",
            data={"query": query, "count": len(results_data), "results": results_data}
        ))

    return _text("\n".join(lines))


@handler.register("chainguard_memory_update")
async def handle_memory_update(args: Dict[str, Any]) -> List[TextContent]:
    """Manual memory update for specific files or learnings."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_update",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    action = args.get("action", "reindex_file")
    file_path = args.get("file_path", "")
    learning = args.get("learning", "")

    project_id = get_project_id(state.project_path)

    if not await memory_manager.memory_exists(project_id):
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="memory_update",
                message="Memory nicht initialisiert",
                blocker_type="memory_not_initialized",
                blocker_data={"action": "chainguard_memory_init()"}
            ))
        return _text("✗ Memory nicht initialisiert. Zuerst: chainguard_memory_init()")

    memory = await memory_manager.get_memory(project_id, state.project_path)

    if action == "reindex_file":
        if not file_path:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_warning(
                    tool="memory_update",
                    message="file_path required for reindex_file action"
                ))
            return _text("⚠ file_path required for reindex_file action")

        full_path = Path(state.project_path) / file_path if not Path(file_path).is_absolute() else Path(file_path)

        if not full_path.exists():
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="memory_update",
                    message=f"File not found: {file_path}",
                    data={"file": file_path}
                ))
            return _text(f"✗ File not found: {file_path}")

        try:
            content = full_path.read_text(encoding='utf-8', errors='ignore')
            relative_path = str(full_path.relative_to(state.project_path))
            file_summary = _create_file_summary(full_path, content)

            await memory.upsert(
                content=file_summary,
                collection="code_structure",
                metadata={
                    "type": "file",
                    "path": relative_path,
                    "language": full_path.suffix.lstrip('.'),
                    "lines": len(content.splitlines()),
                },
                doc_id=f"file:{relative_path}"
            )

            # Invalidate context cache
            context_injector.invalidate_cache(project_id)

            state.add_action(f"MEM_UPDATE: {full_path.name}")
            await pm.save_async(state)

            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_success(
                    tool="memory_update",
                    message=f"Re-indexed: {relative_path}",
                    data={"file": relative_path, "action": "reindex_file"}
                ))
            return _text(f"✓ Re-indexed: {relative_path}")

        except Exception as e:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="memory_update",
                    message=f"Error reindexing: {str(e)[:50]}",
                    data={"file": file_path}
                ))
            return _text(f"✗ Error reindexing: {str(e)[:50]}")

    elif action == "add_learning":
        if not learning:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_warning(
                    tool="memory_update",
                    message="learning required for add_learning action"
                ))
            return _text("⚠ learning required for add_learning action")

        await memory.add(
            content=learning,
            collection="learnings",
            metadata={
                "type": "learning",
                "scope": state.scope.description if state.scope else "",
                "added_by": "manual",
            }
        )

        state.add_action(f"LEARNING: {learning[:20]}")
        await pm.save_async(state)

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="memory_update",
                message=f"Learning added: {learning[:60]}",
                data={"learning": learning[:100], "action": "add_learning"}
            ))
        return _text(f"✓ Learning added: {learning[:60]}")

    elif action == "cleanup":
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="memory_update",
                message="Cleanup completed",
                data={"action": "cleanup"}
            ))
        # Remove old entries (placeholder for future implementation)
        return _text("✓ Cleanup completed (no action needed)")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_warning(
            tool="memory_update",
            message=f"Unknown action: {action}",
            data={"valid_actions": ["reindex_file", "add_learning", "cleanup"]}
        ))
    return _text(f"⚠ Unknown action: {action}")


@handler.register("chainguard_memory_status")
async def handle_memory_status(args: Dict[str, Any]) -> List[TextContent]:
    """Show memory status and statistics."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_status",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    project_id = get_project_id(state.project_path)

    if not await memory_manager.memory_exists(project_id):
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="memory_status",
                message=f"Memory Status: {state.project_name}",
                data={
                    "project": state.project_name,
                    "initialized": False,
                    "hint": "chainguard_memory_init()"
                }
            ))
        return _text(
            f"📊 Memory Status: {state.project_name}\n\n"
            "❌ Nicht initialisiert\n"
            "→ Nutze: chainguard_memory_init()"
        )

    memory = await memory_manager.get_memory(project_id, state.project_path)
    stats = await memory.get_stats()

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="memory_status",
            message=f"Memory Status: {state.project_name}",
            data={
                "project": state.project_name,
                "initialized": True,
                "initialized_at": stats.initialized_at[:16] if stats.initialized_at else None,
                "last_update": stats.last_update[:16] if stats.last_update else None,
                "collections": stats.collections,
                "total_documents": stats.total_documents,
                "storage_mb": round(stats.storage_size_mb, 2),
                "embedding_model": "all-MiniLM-L6-v2"
            }
        ))

    lines = [f"📊 **Memory Status: {state.project_name}**", ""]

    if stats.initialized_at:
        lines.append(f"Initialisiert: {stats.initialized_at[:16]}")
    if stats.last_update:
        lines.append(f"Letztes Update: {stats.last_update[:16]}")

    lines.append("")
    lines.append("**Collections:**")
    for name, count in stats.collections.items():
        lines.append(f"├─ {name}: {count} Dokumente")

    lines.append("")
    lines.append(f"**Total:** {stats.total_documents} Dokumente")
    lines.append(f"**Speicher:** {stats.storage_size_mb:.2f} MB")
    lines.append(f"**Embedding-Model:** all-MiniLM-L6-v2")

    return _text("\n".join(lines))


@handler.register("chainguard_memory_summarize")
async def handle_memory_summarize(args: Dict[str, Any]) -> List[TextContent]:
    """
    Generate deep logic summaries for a specific file or the entire project.

    This tool extracts and stores detailed descriptions of code logic,
    not just structure. It analyzes docstrings, comments, and code patterns
    to create human-readable summaries of what each file/function does.

    Args:
        file: Optional specific file to summarize (relative or absolute path)
        force: If true, re-summarize even if summary exists

    Returns:
        Summary of the file(s) processed
    """
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_summarize",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    if not SUMMARIZER_AVAILABLE or not code_summarizer:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_summarize",
                message="Code Summarizer not available"
            ))
        return _text("✗ Code Summarizer not available. Check installation.")

    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    file_path = args.get("file", "")
    force = args.get("force", False)

    project_id = get_project_id(state.project_path)

    if not await memory_manager.memory_exists(project_id):
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="memory_summarize",
                message="Memory nicht initialisiert",
                blocker_type="memory_not_initialized",
                blocker_data={"action": "chainguard_memory_init()"}
            ))
        return _text(
            "✗ Memory nicht initialisiert.\n"
            "→ Zuerst: chainguard_memory_init()"
        )

    memory = await memory_manager.get_memory(project_id, state.project_path)
    project_path = Path(state.project_path)

    if file_path:
        # Summarize single file
        full_path = project_path / file_path if not Path(file_path).is_absolute() else Path(file_path)

        if not full_path.exists():
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="memory_summarize",
                    message=f"File not found: {file_path}",
                    data={"file": file_path}
                ))
            return _text(f"✗ File not found: {file_path}")

        if not full_path.is_file():
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="memory_summarize",
                    message=f"Not a file: {file_path}",
                    data={"file": file_path}
                ))
            return _text(f"✗ Not a file: {file_path}")

        try:
            content = full_path.read_text(encoding='utf-8', errors='ignore')
            relative_path = str(full_path.relative_to(project_path))

            summary = code_summarizer.summarize_file(full_path, content)
            summary_text = summary.to_text(max_length=2000)

            if not summary_text.strip():
                # v6.0: XML Response
                if XML_RESPONSES_ENABLED:
                    return _text(xml_warning(
                        tool="memory_summarize",
                        message=f"No meaningful content to summarize in: {relative_path}",
                        data={"file": relative_path}
                    ))
                return _text(f"⚠ No meaningful content to summarize in: {relative_path}")

            await memory.upsert(
                content=summary_text,
                collection="code_summaries",
                metadata={
                    "type": "logic_summary",
                    "path": relative_path,
                    "language": summary.language,
                    "purpose": summary.purpose[:200] if summary.purpose else "",
                    "class_count": len(summary.classes),
                    "function_count": len(summary.functions),
                },
                doc_id=f"summary:{relative_path}"
            )

            # Invalidate context cache
            context_injector.invalidate_cache(project_id)

            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_success(
                    tool="memory_summarize",
                    message=f"Summary erstellt fuer: {relative_path}",
                    data={
                        "file": relative_path,
                        "purpose": summary.purpose[:200] if summary.purpose else "",
                        "class_count": len(summary.classes),
                        "function_count": len(summary.functions),
                        "classes": [{"name": c.name, "purpose": c.get_purpose()[:80]} for c in summary.classes[:5]],
                        "functions": [{"name": f.name, "purpose": f.get_purpose()[:80]} for f in summary.functions[:8]]
                    }
                ))

            lines = [f"✓ Summary erstellt für: {relative_path}", ""]
            lines.append(f"**Zweck:** {summary.purpose}")
            lines.append("")

            if summary.classes:
                lines.append("**Klassen:**")
                for cls in summary.classes[:5]:
                    lines.append(f"  • {cls.name}: {cls.get_purpose()}")

            if summary.functions:
                lines.append("**Funktionen:**")
                for func in summary.functions[:8]:
                    lines.append(f"  • {func.name}: {func.get_purpose()}")

            if summary.important_comments:
                lines.append("")
                lines.append("**Wichtige Notizen:**")
                for comment in summary.important_comments[:3]:
                    lines.append(f"  • {comment[:80]}")

            return _text("\n".join(lines))

        except Exception as e:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="memory_summarize",
                    message=f"Error summarizing file: {str(e)[:100]}",
                    data={"file": file_path}
                ))
            return _text(f"✗ Error summarizing file: {str(e)[:100]}")

    else:
        # Summarize all files (re-run for entire project)
        include_patterns = ["**/*.py", "**/*.php", "**/*.js", "**/*.ts", "**/*.tsx"]
        exclude_patterns = ["node_modules", "vendor", ".git", "__pycache__", "*.min.js"]

        summarized = 0
        errors = []

        for pattern in include_patterns:
            try:
                for fp in project_path.glob(pattern):
                    path_str = str(fp)
                    if any(excl in path_str for excl in exclude_patterns):
                        continue
                    if not should_index_file(path_str):
                        continue
                    if not fp.is_file():
                        continue

                    try:
                        content = fp.read_text(encoding='utf-8', errors='ignore')
                        if not content.strip():
                            continue

                        relative_path = str(fp.relative_to(project_path))

                        # Check if summary exists and skip if not forcing
                        if not force:
                            existing = await memory.get(f"summary:{relative_path}", "code_summaries")
                            if existing:
                                continue

                        summary = code_summarizer.summarize_file(fp, content)
                        summary_text = summary.to_text(max_length=2000)

                        if summary_text.strip():
                            await memory.upsert(
                                content=summary_text,
                                collection="code_summaries",
                                metadata={
                                    "type": "logic_summary",
                                    "path": relative_path,
                                    "language": summary.language,
                                    "purpose": summary.purpose[:200] if summary.purpose else "",
                                    "class_count": len(summary.classes),
                                    "function_count": len(summary.functions),
                                },
                                doc_id=f"summary:{relative_path}"
                            )
                            summarized += 1

                    except Exception as e:
                        errors.append(f"{fp.name}: {str(e)[:30]}")

            except Exception as e:
                errors.append(f"Pattern {pattern}: {str(e)[:30]}")

        # Invalidate context cache
        context_injector.invalidate_cache(project_id)

        state.add_action(f"SUMMARIZE: {summarized} files")
        await pm.save_async(state)

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            data = {
                "summarized": summarized,
                "force": force
            }
            if errors:
                data["errors"] = errors[:5]
            return _text(xml_success(
                tool="memory_summarize",
                message=f"{summarized} Dateien summarisiert",
                data=data
            ))

        lines = [f"✓ {summarized} Dateien summarisiert", ""]

        if errors:
            lines.append(f"⚠ {len(errors)} Fehler:")
            for err in errors[:5]:
                lines.append(f"   - {err}")

        lines.append("")
        lines.append("→ Nutze chainguard_memory_query() für semantische Suchen")
        lines.append("→ Filter mit filter_type='code' für Logik-Summaries")

        return _text("\n".join(lines))


# Helper functions for memory indexing
def _create_file_summary(file_path: Path, content: str) -> str:
    """Create a summary description for a file."""
    name = file_path.name
    lines = len(content.splitlines())
    ext = file_path.suffix.lower()

    # Detect common patterns
    patterns = []
    content_lower = content.lower()

    if "class " in content or "interface " in content:
        patterns.append("defines classes")
    if "def " in content or "function " in content or "async function" in content:
        patterns.append("contains functions")
    if "import " in content or "require(" in content or "use " in content:
        patterns.append("has imports")
    if "@route" in content_lower or "router." in content_lower or "app.get(" in content_lower:
        patterns.append("defines routes")
    if "test" in name.lower() or "spec" in name.lower():
        patterns.append("test file")
    if "model" in name.lower():
        patterns.append("model definition")
    if "controller" in name.lower():
        patterns.append("controller")
    if "config" in name.lower() or "settings" in name.lower():
        patterns.append("configuration")

    pattern_str = ", ".join(patterns) if patterns else "general code"

    # First comment/docstring as description
    first_comment = ""
    if ext == ".py":
        # Python docstring
        import re
        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if match:
            first_comment = match.group(1).strip()[:100]
    elif ext in [".php", ".js", ".ts"]:
        # PHPDoc/JSDoc style
        import re
        match = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
        if match:
            first_comment = match.group(1).strip()[:100]
            first_comment = re.sub(r'[\s*]+', ' ', first_comment)

    summary = f"{name}: {pattern_str}. {lines} lines."
    if first_comment:
        summary += f" {first_comment}"

    return summary[:500]  # Limit length


def _extract_functions(content: str, suffix: str, file_path: str = "") -> list:
    """Extract functions/methods from code using AST-Analyzer.

    Uses the ast_analyzer module for precise extraction with tree-sitter
    or regex fallback. Returns richer metadata including signatures,
    parent classes, and return types.
    """
    from .ast_analyzer import ast_analyzer, LANGUAGE_EXTENSIONS

    # Get language from suffix
    language = LANGUAGE_EXTENSIONS.get(suffix.lower())
    if not language:
        return []

    # Use AST analyzer for extraction
    analysis = ast_analyzer.analyze_file(file_path, content) if file_path else None

    if analysis is None:
        # Fallback: use RegexAnalyzer directly
        from .ast_analyzer import RegexAnalyzer
        analysis = RegexAnalyzer.analyze(content, language, file_path or "unknown")

    functions = []
    seen_keys = set()  # Deduplicate by (name, line_start, parent)

    for symbol in analysis.symbols:
        # Skip non-function symbols for this collection
        if symbol.type.value not in ["function", "method", "class"]:
            continue

        # Deduplicate: same name + line + parent = same symbol
        dedup_key = (symbol.name, symbol.line_start, symbol.parent or "")
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        func_data = {
            "type": symbol.type.value,
            "name": symbol.name,
            "params": symbol.parameters[:5],
            "description": symbol.to_memory_content(),
            "signature": symbol.signature[:100] if symbol.signature else "",
            "parent": symbol.parent,
            "return_type": symbol.return_type,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
        }
        functions.append(func_data)

    return functions[:100]  # Limit to prevent too many entries


# =============================================================================
# SYMBOL VALIDATION HELPERS (v6.2)
# =============================================================================

# Cache for project symbols (per project_path + language)
_symbol_cache: Dict[str, Set[str]] = {}
_symbol_cache_time: Dict[str, float] = {}
SYMBOL_CACHE_TTL = 300  # 5 minutes

async def _get_project_symbols(project_path: str, lang) -> Set[str]:
    """
    Get all symbol definitions from the project for a given language.
    Results are cached for 5 minutes to avoid repeated scans.
    """
    import time
    from .symbol_patterns import EXTENSION_MAP

    cache_key = f"{project_path}:{lang.value if hasattr(lang, 'value') else lang}"
    now = time.time()

    # Check cache
    if cache_key in _symbol_cache:
        if now - _symbol_cache_time.get(cache_key, 0) < SYMBOL_CACHE_TTL:
            return _symbol_cache[cache_key]

    # Collect symbols
    symbols = set()
    extractor = SymbolExtractor()
    project = Path(project_path)

    # Get extensions for this language
    extensions = [ext for ext, l in EXTENSION_MAP.items() if l == lang]

    # Scan project files
    for ext in extensions:
        for src_file in project.glob(f"**/*{ext}"):
            # Skip common directories
            if any(skip in str(src_file) for skip in ['node_modules', 'vendor', '.git', '__pycache__', 'dist', 'build']):
                continue

            try:
                content = src_file.read_text(encoding='utf-8', errors='replace')
                defs = extractor.extract_definitions(content, lang)
                symbols.update(defs)
            except Exception:
                pass

    # Cache result
    _symbol_cache[cache_key] = symbols
    _symbol_cache_time[cache_key] = now

    return symbols


# =============================================================================
# MEMORY AUTO-UPDATE HELPERS (v5.2)
# =============================================================================

async def _update_memory_for_file(project_id: str, file_path: str, project_path: str):
    """
    Update memory for a single file (runs in background).

    Called automatically when a file is tracked.
    Non-blocking - errors are logged but don't affect the main flow.
    """
    if not MEMORY_AVAILABLE:
        return

    try:
        # Check if file should be indexed
        if not should_index_file(file_path):
            return

        # Get full path
        full_path = Path(project_path) / file_path if not Path(file_path).is_absolute() else Path(file_path)

        if not full_path.exists():
            return

        # Read file content
        try:
            content = full_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return

        if not content.strip():
            return

        # Get memory instance
        memory = await memory_manager.get_memory(project_id)

        # Create relative path
        try:
            relative_path = str(full_path.relative_to(project_path))
        except ValueError:
            relative_path = file_path

        # Update file summary
        file_summary = _create_file_summary(full_path, content)
        await memory.upsert(
            content=file_summary,
            collection="code_structure",
            metadata={
                "type": "file",
                "path": relative_path,
                "language": full_path.suffix.lstrip('.'),
                "lines": len(content.splitlines()),
            },
            doc_id=f"file:{relative_path}"
        )

        # Update functions (re-extract)
        functions = _extract_functions(content, full_path.suffix)
        for func in functions[:20]:  # Limit per file
            await memory.upsert(
                content=func["description"],
                collection="functions",
                metadata={
                    "type": func["type"],
                    "name": func["name"],
                    "path": relative_path,
                    "params": func.get("params", []),
                },
                doc_id=f"func:{relative_path}:{func['name']}"
            )

        # Invalidate context cache for this project
        context_injector.invalidate_cache(project_id)

        logger.debug(f"Memory auto-updated: {relative_path}")

    except Exception as e:
        logger.debug(f"Memory auto-update failed for {file_path}: {e}")


async def _delete_from_memory(project_id: str, file_path: str, project_path: str):
    """
    Remove a deleted file from memory (v5.3).

    Called automatically when a file is tracked with action="delete".
    Removes both the file entry and all associated function entries.
    """
    if not MEMORY_AVAILABLE:
        return

    try:
        memory = await memory_manager.get_memory(project_id)

        # Create relative path for matching
        full_path = Path(project_path) / file_path if not Path(file_path).is_absolute() else Path(file_path)
        try:
            relative_path = str(full_path.relative_to(project_path))
        except ValueError:
            relative_path = file_path

        # Delete file entry from code_structure
        file_doc_id = f"file:{relative_path}"
        await memory.delete(
            collection="code_structure",
            doc_ids=[file_doc_id]
        )

        # Delete all functions from this file
        # We need to find and delete by path metadata
        await memory.delete(
            collection="functions",
            where={"path": relative_path}
        )

        # Invalidate context cache
        context_injector.invalidate_cache(project_id)

        logger.debug(f"Memory cleanup: removed {relative_path}")

    except Exception as e:
        logger.debug(f"Memory delete failed for {file_path}: {e}")


async def _consolidate_session_learnings(state, scope_desc: str):
    """
    Consolidate learnings from the current session into memory.

    Called at finish() to persist insights from the work session.
    """
    if not MEMORY_AVAILABLE:
        return

    try:
        project_id = get_project_id(state.project_path)

        if not await memory_manager.memory_exists(project_id):
            return

        memory = await memory_manager.get_memory(project_id)

        # Create session summary
        changed_files = list(state.changed_files)[:10]
        phase = state.phase
        criteria_status = []

        if state.scope and state.scope.acceptance_criteria:
            for crit in state.scope.acceptance_criteria:
                status = "done" if crit.get("fulfilled") else "open"
                criteria_status.append(f"{crit.get('criterion', '?')}: {status}")

        # Build learning content
        learning_parts = [
            f"Session: {scope_desc}",
            f"Phase: {phase}",
            f"Files changed: {', '.join(changed_files)}" if changed_files else "",
        ]

        if criteria_status:
            learning_parts.append(f"Criteria: {'; '.join(criteria_status[:5])}")

        learning_content = ". ".join([p for p in learning_parts if p])

        if learning_content:
            await memory.add(
                content=learning_content,
                collection="learnings",
                metadata={
                    "type": "session",
                    "scope": scope_desc,
                    "phase": phase,
                    "files_count": len(changed_files),
                }
            )
            logger.debug(f"Session learning consolidated: {scope_desc[:30]}")

    except Exception as e:
        logger.debug(f"Session consolidation failed: {e}")


# =============================================================================
# PHASE 3 HANDLERS (v5.3): AST Analysis, Architecture, Export/Import
# =============================================================================

@handler.register("chainguard_analyze_code")
async def handle_analyze_code(args: Dict[str, Any]) -> List[TextContent]:
    """Analyze code structure using AST parsing."""
    working_dir = args.get("working_dir")
    file_path = args.get("file", "")
    state = await pm.get_async(working_dir)

    try:
        from .ast_analyzer import ast_analyzer, LANGUAGE_EXTENSIONS
    except ImportError as e:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="analyze_code",
                message=f"AST Analyzer not available: {e}"
            ))
        return _text(f"✗ AST Analyzer not available: {e}")

    if not file_path:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="analyze_code",
                message="Missing required parameter: file"
            ))
        return _text("✗ Missing required parameter: file")

    # Build full path
    full_path = Path(state.project_path) / file_path if not Path(file_path).is_absolute() else Path(file_path)

    if full_path.is_dir():
        # Directory analysis
        analyses = ast_analyzer.analyze_directory(str(full_path))

        if not analyses:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_info(
                    tool="analyze_code",
                    message=f"No analyzable files found in: {file_path}",
                    data={"path": file_path, "files": []}
                ))
            return _text(f"No analyzable files found in: {file_path}")

        # Build data for XML
        files_data = []
        total_symbols = 0

        lines = [f"📊 **Code Analysis: {file_path}**", ""]
        lines.append(f"Analyzed {len(analyses)} files")
        lines.append("")

        for path, analysis in list(analyses.items())[:10]:  # Limit output
            rel_path = str(Path(path).relative_to(full_path)) if full_path in Path(path).parents else path
            symbols_summary = []
            for s in analysis.symbols:
                if s.type.value not in [t.value for t in symbols_summary]:
                    symbols_summary.append(s.type)

            types_str = ", ".join(s.value for s in symbols_summary[:3])
            files_data.append({
                "path": rel_path,
                "symbols": len(analysis.symbols),
                "types": [s.value for s in symbols_summary[:3]]
            })
            lines.append(f"├─ {rel_path}: {len(analysis.symbols)} symbols ({types_str})")
            total_symbols += len(analysis.symbols)

        if len(analyses) > 10:
            lines.append(f"└─ ... and {len(analyses) - 10} more files")

        lines.append("")
        lines.append(f"**Total Symbols:** {total_symbols}")

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="analyze_code",
                message=f"Analyzed {len(analyses)} files",
                data={
                    "path": file_path,
                    "file_count": len(analyses),
                    "total_symbols": total_symbols,
                    "files": files_data
                }
            ))

        return _text("\n".join(lines))

    else:
        # Single file analysis
        if not full_path.exists():
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="analyze_code",
                    message=f"File not found: {file_path}",
                    data={"file": file_path}
                ))
            return _text(f"✗ File not found: {file_path}")

        ext = full_path.suffix.lower()
        if ext not in LANGUAGE_EXTENSIONS:
            # v6.0: XML Response
            if XML_RESPONSES_ENABLED:
                return _text(xml_error(
                    tool="analyze_code",
                    message=f"Unsupported file type: {ext}",
                    data={"file": file_path, "extension": ext}
                ))
            return _text(f"✗ Unsupported file type: {ext}")

        analysis = ast_analyzer.analyze_file(str(full_path))

        # Build symbols data for XML
        symbols_data = []
        lines = [f"📊 **Code Analysis: {full_path.name}**", ""]
        lines.append(f"Language: {analysis.language}")
        lines.append("")

        if analysis.symbols:
            lines.append(f"**Symbols ({len(analysis.symbols)}):**")
            for symbol in analysis.symbols[:15]:
                parent = f" (in {symbol.parent})" if symbol.parent else ""
                symbols_data.append({
                    "type": symbol.type.value,
                    "name": symbol.name,
                    "parent": symbol.parent,
                    "line": symbol.line_start
                })
                lines.append(f"├─ {symbol.type.value}: {symbol.name}{parent} [L{symbol.line_start}]")
            if len(analysis.symbols) > 15:
                lines.append(f"└─ ... and {len(analysis.symbols) - 15} more")
            lines.append("")

        if analysis.imports:
            lines.append(f"**Imports ({len(analysis.imports)}):**")
            for imp in analysis.imports[:5]:
                lines.append(f"├─ {imp[:60]}")
            if len(analysis.imports) > 5:
                lines.append(f"└─ ... and {len(analysis.imports) - 5} more")
            lines.append("")

        if analysis.relations:
            lines.append(f"**Relations ({len(analysis.relations)}):**")
            for rel in analysis.relations[:5]:
                lines.append(f"├─ {rel.relation_type.value}: {', '.join(rel.symbols[:3])}")

        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="analyze_code",
                message=f"Code Analysis: {full_path.name}",
                data={
                    "file": file_path,
                    "language": analysis.language,
                    "symbol_count": len(analysis.symbols),
                    "import_count": len(analysis.imports),
                    "relation_count": len(analysis.relations),
                    "symbols": symbols_data[:15],
                    "imports": analysis.imports[:5]
                }
            ))

        return _text("\n".join(lines))


@handler.register("chainguard_detect_architecture")
async def handle_detect_architecture(args: Dict[str, Any]) -> List[TextContent]:
    """Detect architectural patterns in the codebase."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    try:
        from .architecture import architecture_detector
    except ImportError as e:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="detect_architecture",
                message=f"Architecture Detector not available: {e}"
            ))
        return _text(f"✗ Architecture Detector not available: {e}")

    analysis = architecture_detector.analyze(state.project_path)

    # v5.4: Store in Memory if available (always, even with low confidence)
    memory_updated = False
    if MEMORY_AVAILABLE:
        try:
            project_id = get_project_id(state.project_path)
            if await memory_manager.memory_exists(project_id):
                memory = await memory_manager.get_memory(project_id, state.project_path)

                # Always store main architecture pattern
                arch_content = (
                    f"Project architecture: {analysis.pattern.value}. "
                    f"Framework: {analysis.framework.value if analysis.framework else 'unknown'}. "
                    f"Detected layers: {', '.join(analysis.detected_layers[:5]) if analysis.detected_layers else 'none'}. "
                    f"Design patterns: {', '.join(analysis.detected_patterns[:5]) if analysis.detected_patterns else 'none'}."
                )
                await memory.upsert(
                    content=arch_content,
                    collection="architecture",
                    metadata={
                        "type": "architecture",
                        "name": "project_architecture",
                        "pattern": analysis.pattern.value,
                        "framework": analysis.framework.value if analysis.framework else "",
                        "confidence": analysis.confidence,
                        "layers": ",".join(analysis.detected_layers[:10]) if analysis.detected_layers else "",
                        "design_patterns": ",".join(analysis.detected_patterns[:10]) if analysis.detected_patterns else "",
                    },
                    doc_id="arch:main"
                )
                memory_updated = True

                # Store each detected layer
                for layer in analysis.detected_layers[:10]:
                    layer_content = f"Architecture layer: {layer} in {analysis.pattern.value} pattern."
                    await memory.upsert(
                        content=layer_content,
                        collection="architecture",
                        metadata={
                            "type": "layer",
                            "name": layer,
                            "pattern": analysis.pattern.value,
                        },
                        doc_id=f"arch:layer:{layer.lower()}"
                    )

                # Store design patterns
                for pattern in analysis.detected_patterns[:10]:
                    pattern_content = f"Design pattern: {pattern} detected in codebase."
                    await memory.upsert(
                        content=pattern_content,
                        collection="architecture",
                        metadata={
                            "type": "design_pattern",
                            "name": pattern,
                        },
                        doc_id=f"arch:pattern:{pattern.lower()}"
                    )
        except Exception:
            pass  # Silent fail - architecture detection still works without memory

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_success(
            tool="detect_architecture",
            message=f"Architecture Analysis: {state.project_name}",
            data={
                "project": state.project_name,
                "pattern": analysis.pattern.value,
                "confidence": round(analysis.confidence, 2),
                "framework": analysis.framework.value if analysis.framework else None,
                "layers": analysis.detected_layers[:8],
                "design_patterns": analysis.detected_patterns[:6],
                "suggestions": analysis.suggestions[:3],
                "memory_updated": memory_updated
            }
        ))

    lines = [f"🏛️ **Architecture Analysis: {state.project_name}**", ""]

    # Main pattern
    lines.append(f"**Pattern:** {analysis.pattern.value}")
    lines.append(f"**Confidence:** {analysis.confidence:.0%}")

    if analysis.framework:
        lines.append(f"**Framework:** {analysis.framework.value}")

    lines.append("")

    if analysis.detected_layers:
        lines.append("**Detected Layers:**")
        for layer in analysis.detected_layers[:8]:
            lines.append(f"├─ {layer}")
        lines.append("")

    if analysis.detected_patterns:
        lines.append("**Design Patterns:**")
        for pattern in analysis.detected_patterns[:6]:
            lines.append(f"├─ {pattern}")
        lines.append("")

    if analysis.suggestions:
        lines.append("**Suggestions:**")
        for suggestion in analysis.suggestions[:3]:
            lines.append(f"• {suggestion}")

    if memory_updated:
        lines.append("")
        lines.append("✓ Architecture stored in Memory")

    return _text("\n".join(lines))


@handler.register("chainguard_memory_export")
async def handle_memory_export(args: Dict[str, Any]) -> List[TextContent]:
    """Export project memory to a portable file."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_export",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    export_format = args.get("format", "json")
    collections = args.get("collections")
    include_embeddings = args.get("include_embeddings", False)
    compress = args.get("compress", False)

    state = await pm.get_async(working_dir)
    project_id = get_project_id(state.project_path)

    if not await memory_manager.memory_exists(project_id):
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_blocked(
                tool="memory_export",
                message="No memory initialized for this project",
                blocker_type="memory_not_initialized",
                blocker_data={"action": "chainguard_memory_init()"}
            ))
        return _text("✗ No memory initialized for this project. Run chainguard_memory_init() first.")

    try:
        from .memory_export import memory_exporter
    except ImportError as e:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_export",
                message=f"Memory Export not available: {e}"
            ))
        return _text(f"✗ Memory Export not available: {e}")

    memory = await memory_manager.get_memory(project_id, state.project_path)

    if export_format == "jsonl":
        result = await memory_exporter.export_jsonl(
            memory,
            collections=collections,
            include_embeddings=include_embeddings,
            compress=compress,
        )
    else:
        result = await memory_exporter.export_json(
            memory,
            collections=collections,
            include_embeddings=include_embeddings,
            compress=compress,
        )

    if result.success:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="memory_export",
                message="Memory exported successfully",
                data={
                    "file": result.file_path,
                    "documents": result.documents_exported,
                    "collections": result.collections_exported
                }
            ))
        lines = ["✓ Memory exported successfully!", ""]
        lines.append(f"**File:** {result.file_path}")
        lines.append(f"**Documents:** {result.documents_exported}")
        lines.append(f"**Collections:** {', '.join(result.collections_exported)}")
        return _text("\n".join(lines))
    else:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_export",
                message=f"Export failed: {result.error}"
            ))
        return _text(f"✗ Export failed: {result.error}")


@handler.register("chainguard_memory_import")
async def handle_memory_import(args: Dict[str, Any]) -> List[TextContent]:
    """Import project memory from an exported file."""
    if not MEMORY_AVAILABLE:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_import",
                message="Memory not available",
                data={"install": "pip install chromadb sentence-transformers"}
            ))
        return _text("✗ Memory not available. Install: pip install chromadb sentence-transformers")

    working_dir = args.get("working_dir")
    file_path = args.get("file", "")
    merge = args.get("merge", True)
    skip_existing = args.get("skip_existing", True)

    if not file_path:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_warning(
                tool="memory_import",
                message="Missing required parameter: file"
            ))
        return _text("✗ Missing required parameter: file")

    state = await pm.get_async(working_dir)
    project_id = get_project_id(state.project_path)

    try:
        from .memory_export import memory_importer
    except ImportError as e:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_import",
                message=f"Memory Import not available: {e}"
            ))
        return _text(f"✗ Memory Import not available: {e}")

    # Ensure memory exists
    if not await memory_manager.memory_exists(project_id):
        # Initialize first
        memory = await memory_manager.get_memory(project_id, state.project_path)
    else:
        memory = await memory_manager.get_memory(project_id, state.project_path)

    # Determine format from extension
    path = Path(file_path)
    is_jsonl = ".jsonl" in path.name

    if is_jsonl:
        result = await memory_importer.import_jsonl(
            memory,
            file_path,
            merge=merge,
            skip_existing=skip_existing,
        )
    else:
        result = await memory_importer.import_json(
            memory,
            file_path,
            merge=merge,
            skip_existing=skip_existing,
        )

    if result.success:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_success(
                tool="memory_import",
                message="Memory imported successfully",
                data={
                    "imported": result.documents_imported,
                    "skipped": result.documents_skipped,
                    "collections": result.collections_imported
                }
            ))
        lines = ["✓ Memory imported successfully!", ""]
        lines.append(f"**Imported:** {result.documents_imported} documents")
        lines.append(f"**Skipped:** {result.documents_skipped}")
        lines.append(f"**Collections:** {', '.join(result.collections_imported)}")
        return _text("\n".join(lines))
    else:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="memory_import",
                message=f"Import failed: {result.error}"
            ))
        return _text(f"✗ Import failed: {result.error}")


@handler.register("chainguard_list_exports")
async def handle_list_exports(args: Dict[str, Any]) -> List[TextContent]:
    """List available memory export files."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)

    try:
        from .memory_export import list_exports
    except ImportError as e:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_error(
                tool="list_exports",
                message=f"Memory Export not available: {e}"
            ))
        return _text(f"✗ Memory Export not available: {e}")

    project_id = get_project_id(state.project_path) if MEMORY_AVAILABLE else None
    exports = list_exports(project_id[:8] if project_id else None)

    if not exports:
        # v6.0: XML Response
        if XML_RESPONSES_ENABLED:
            return _text(xml_info(
                tool="list_exports",
                message="No export files found",
                data={"exports": []}
            ))
        return _text("No export files found.")

    # Build exports data for XML
    exports_data = []
    lines = ["📁 **Available Exports:**", ""]

    for exp in exports[:10]:
        size_kb = exp["size_bytes"] / 1024
        exports_data.append({
            "filename": exp["filename"],
            "size_kb": round(size_kb, 1),
            "modified": exp["modified"][:16]
        })
        lines.append(f"├─ {exp['filename']}")
        lines.append(f"│  Size: {size_kb:.1f} KB | Modified: {exp['modified'][:16]}")

    if len(exports) > 10:
        lines.append(f"└─ ... and {len(exports) - 10} more files")

    # v6.0: XML Response
    if XML_RESPONSES_ENABLED:
        return _text(xml_info(
            tool="list_exports",
            message=f"{len(exports)} export files found",
            data={"count": len(exports), "exports": exports_data}
        ))

    return _text("\n".join(lines))


# =============================================================================
# SYMBOL VALIDATION TOOLS (v6.2 - Hallucination Prevention)
# =============================================================================

@handler.register("chainguard_symbol_mode")
async def handle_symbol_mode(args: Dict[str, Any]) -> List[TextContent]:
    """Set or view symbol validation mode."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    mode = args.get("mode")

    if mode:
        # Set new mode (case-insensitive - accepts both "STRICT" and "strict")
        try:
            new_mode = SymbolValidationMode(mode.lower())
            SymbolValidator.set_mode(new_mode)

            mode_descriptions = {
                SymbolValidationMode.OFF: "Symbol validation disabled",
                SymbolValidationMode.WARN: "Warnings only (no blocking)",
                SymbolValidationMode.STRICT: "Block on high-confidence issues",
                SymbolValidationMode.ADAPTIVE: "Auto-adjust based on false positive rate"
            }

            return _text(f"✓ Symbol validation mode: {new_mode.value}\n  {mode_descriptions[new_mode]}")

        except ValueError:
            valid_modes = ", ".join([m.value for m in SymbolValidationMode])
            return _text(f"✗ Invalid mode '{mode}'. Valid modes: {valid_modes}")

    # Show current mode
    current_mode = SymbolValidator.get_mode()

    mode_info = {
        SymbolValidationMode.OFF: ("⬚", "Disabled"),
        SymbolValidationMode.WARN: ("⚠", "Warnings only (default)"),
        SymbolValidationMode.STRICT: ("🛡", "Strict (blocking)"),
        SymbolValidationMode.ADAPTIVE: ("🔄", "Adaptive")
    }

    icon, desc = mode_info.get(current_mode, ("?", "Unknown"))

    lines = [
        f"Symbol Validation: {icon} {current_mode.value}",
        f"  {desc}",
        "",
        "Available modes:",
        "  OFF     - Disabled",
        "  WARN    - Warnings only (default, never blocks)",
        "  STRICT  - Block on high-confidence issues",
        "  ADAPTIVE - Auto-adjust"
    ]
    return _text("\n".join(lines))


@handler.register("chainguard_validate_symbols")
async def handle_validate_symbols(args: Dict[str, Any]) -> List[TextContent]:
    """Validate symbols in a file against the codebase."""
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    file_path = args.get("file")
    code = args.get("code")

    if not file_path and not code:
        return _text("✗ Either 'file' or 'code' parameter required")

    # Get code content
    if file_path:
        full_path = Path(state.project_path) / file_path
        if not full_path.exists():
            return _text(f"✗ File not found: {file_path}")

        try:
            code = full_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return _text(f"✗ Cannot read file: {e}")

    # Get known symbols from codebase
    lang = detect_language(file_path or "code.py")
    if not lang:
        return _text("✗ Could not detect language")

    known_symbols = await _get_project_symbols(state.project_path, lang)

    # Validate the target code
    result = SymbolValidator.validate(code, file_path or "inline.txt", known_symbols)

    if not result.issues:
        return _text(f"✓ No symbol issues detected in {file_path or 'code'}")

    # Format issues
    lines = [f"Symbol Validation: {len(result.issues)} potential issues", ""]

    for issue in result.issues[:10]:  # Limit to 10
        conf_bar = "█" * int(issue.confidence * 5) + "░" * (5 - int(issue.confidence * 5))
        lines.append(f"  [{conf_bar}] {issue.name}")
        lines.append(f"      Line {issue.line}: {issue.reason}")

    if len(result.issues) > 10:
        lines.append(f"  ... and {len(result.issues) - 10} more")

    lines.append("")
    lines.append(f"Overall confidence: {result.confidence:.0%}")
    lines.append(f"Should block: {'Yes' if result.should_block else 'No'}")

    return _text("\n".join(lines))


@handler.register("chainguard_validate_packages")
async def handle_validate_packages(args: Dict[str, Any]) -> List[TextContent]:
    """Validate package imports against project dependencies.

    Detects hallucinated/slopsquatting packages that don't exist in:
    - composer.json (PHP)
    - package.json (JS/TS)
    - requirements.txt (Python)

    Args:
        file: File path to validate (optional if code is provided)
        code: Source code to validate (optional if file is provided)
        working_dir: Project root directory
    """
    working_dir = args.get("working_dir")
    state = await pm.get_async(working_dir)
    file_path = args.get("file")
    code = args.get("code")

    if not file_path and not code:
        return _text("✗ Either 'file' or 'code' parameter required")

    validator = PackageValidator(state.project_path)

    if file_path:
        full_path = Path(state.project_path) / file_path
        result = validator.validate_file(str(full_path))
    else:
        # Detect language from file extension or default to JS
        lang = detect_language(file_path or "code.js")
        if not lang:
            return _text("✗ Could not detect language. Provide a file path.")
        result = validator.validate_content(code, file_path or "inline.txt", lang)

    return _text(format_package_report(result))


# =============================================================================
# KANBAN SYSTEM (v6.5)
# =============================================================================

@handler.register("chainguard_kanban_init")
async def handle_kanban_init(args: Dict[str, Any]) -> List[TextContent]:
    """Initialize Kanban board with custom columns."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled (KANBAN_ENABLED=False or PyYAML not installed)")

    working_dir = args.get("working_dir")
    # Use resolved working_dir directly, NOT state.project_path
    # This fixes persistence in subdirectories of git repos
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    columns = args.get("columns")
    preset = args.get("preset")

    # Show available presets if nothing specified
    if not columns and not preset:
        presets = kanban_manager.get_available_presets()
        lines = [
            "📋 **Kanban Board Initialization**",
            "",
            "Bitte wähle Spalten für dein Board:",
            "",
            "**Option 1 - Preset verwenden:**",
        ]
        for name, cols in presets.items():
            lines.append(f"  `preset=\"{name}\"` → {' → '.join(cols)}")

        lines.extend([
            "",
            "**Option 2 - Custom Spalten:**",
            "  `columns=[\"phase1\", \"phase2\", \"phase3\", \"done\"]`",
            "",
            "**Tipp:** Analysiere die Aufgabe und wähle passende Phasen!"
        ])
        return _text("\n".join(lines))

    # Initialize board
    existed = kanban_manager.board_exists(kanban_path)
    board = kanban_manager.init_board(
        working_dir=kanban_path,
        columns=columns,
        preset=preset
    )

    # Format response
    col_flow = " → ".join(board.columns)
    if existed:
        return _text(f"✓ Board aktualisiert\n  Spalten: {col_flow}\n  Cards: {len(board.cards)} (migriert)")
    else:
        return _text(f"✓ Board initialisiert\n  Spalten: {col_flow}\n\n  Nutze `chainguard_kanban_add(title=\"...\")` um Cards zu erstellen.")


@handler.register("chainguard_kanban")
async def handle_kanban(args: Dict[str, Any]) -> List[TextContent]:
    """View Kanban board."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled (KANBAN_ENABLED=False or PyYAML not installed)")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    compact = args.get("compact", True)

    # Check if board exists, suggest init if not
    if not kanban_manager.board_exists(kanban_path):
        return _text("📋 Kein Board vorhanden.\n\n💡 Nutze `chainguard_kanban_init(preset=\"...\")` oder `chainguard_kanban_init(columns=[...])` um ein Board zu erstellen.")

    board_view = kanban_manager.get_board_view(kanban_path, compact=compact)

    # Show blocked cards hint
    blocked = kanban_manager.get_blocked_cards(kanban_path)
    if blocked:
        board_view += f"\n\n⚠️ {len(blocked)} blocked cards (dependencies not met)"

    return _text(board_view)


@handler.register("chainguard_kanban_add")
async def handle_kanban_add(args: Dict[str, Any]) -> List[TextContent]:
    """Add a new card to the Kanban board."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    title = args.get("title")

    if not title:
        return _text("✗ 'title' parameter required")

    card = kanban_manager.add_card(
        working_dir=kanban_path,
        title=title,
        column=args.get("column", "backlog"),
        priority=args.get("priority", "medium"),
        depends_on=args.get("depends_on"),
        tags=args.get("tags"),
        detail_content=args.get("detail")
    )

    detail_info = " 📎" if card.detail_file else ""
    return _text(f"✓ Card `{card.id}` added to {card.column}{detail_info}\n  {card.title}")


@handler.register("chainguard_kanban_move")
async def handle_kanban_move(args: Dict[str, Any]) -> List[TextContent]:
    """Move a card to a different column."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    card_id = args.get("card_id")
    to_column = args.get("to_column")

    if not card_id or not to_column:
        return _text("✗ 'card_id' and 'to_column' parameters required")

    card = kanban_manager.move_card(kanban_path, card_id, to_column)

    if not card:
        return _text(f"✗ Card `{card_id}` not found or invalid column")

    return _text(f"✓ `{card_id}` → {to_column}\n  {card.title}")


@handler.register("chainguard_kanban_detail")
async def handle_kanban_detail(args: Dict[str, Any]) -> List[TextContent]:
    """Get detailed information for a card."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    card_id = args.get("card_id")

    if not card_id:
        return _text("✗ 'card_id' parameter required")

    board = kanban_manager.load_board(kanban_path)
    card = board.get_card(card_id)

    if not card:
        return _text(f"✗ Card `{card_id}` not found")

    # Format card details
    lines = [
        f"📌 **Card: {card.id}**",
        f"Title: {card.title}",
        f"Column: {card.column}",
        f"Priority: {card.priority}",
        f"Created: {card.created_at[:10]}",
        f"Updated: {card.updated_at[:10]}"
    ]

    if card.tags:
        lines.append(f"Tags: {', '.join(card.tags)}")

    if card.depends_on:
        lines.append(f"Depends on: {', '.join(card.depends_on)}")

    # Get detail content if exists
    detail = kanban_manager.get_card_detail(kanban_path, card_id)
    if detail:
        lines.append("")
        lines.append("---")
        lines.append(detail)

    return _text("\n".join(lines))


@handler.register("chainguard_kanban_update")
async def handle_kanban_update(args: Dict[str, Any]) -> List[TextContent]:
    """Update card properties."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    card_id = args.get("card_id")

    if not card_id:
        return _text("✗ 'card_id' parameter required")

    # Update detail content if provided
    if args.get("detail"):
        kanban_manager.set_card_detail(kanban_path, card_id, args["detail"])

    card = kanban_manager.update_card(
        working_dir=kanban_path,
        card_id=card_id,
        title=args.get("title"),
        priority=args.get("priority"),
        tags=args.get("tags"),
        depends_on=args.get("depends_on")
    )

    if not card:
        return _text(f"✗ Card `{card_id}` not found")

    return _text(f"✓ Card `{card_id}` updated\n  {card.title}")


@handler.register("chainguard_kanban_delete")
async def handle_kanban_delete(args: Dict[str, Any]) -> List[TextContent]:
    """Delete a card permanently."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    card_id = args.get("card_id")

    if not card_id:
        return _text("✗ 'card_id' parameter required")

    success = kanban_manager.delete_card(kanban_path, card_id)

    if not success:
        return _text(f"✗ Card `{card_id}` not found")

    return _text(f"✓ Card `{card_id}` deleted")


@handler.register("chainguard_kanban_archive")
async def handle_kanban_archive(args: Dict[str, Any]) -> List[TextContent]:
    """Archive a card."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    card_id = args.get("card_id")

    if not card_id:
        return _text("✗ 'card_id' parameter required")

    success = kanban_manager.archive_card(kanban_path, card_id)

    if not success:
        return _text(f"✗ Card `{card_id}` not found")

    return _text(f"📦 Card `{card_id}` archived")


@handler.register("chainguard_kanban_history")
async def handle_kanban_history(args: Dict[str, Any]) -> List[TextContent]:
    """View archived cards."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)
    limit = args.get("limit", 10)

    archive_view = kanban_manager.get_archive_view(kanban_path, limit=limit)
    return _text(archive_view)


@handler.register("chainguard_kanban_show")
async def handle_kanban_show(args: Dict[str, Any]) -> List[TextContent]:
    """Display full graphical Kanban board with ALL details."""
    if not KANBAN_AVAILABLE:
        return _text("❌ Kanban disabled (KANBAN_ENABLED=False or PyYAML not installed)")

    working_dir = args.get("working_dir")
    kanban_path = await pm.resolve_working_dir_async(working_dir)

    full_view = kanban_manager.get_full_board_view(kanban_path)
    return _text(full_view)


# =============================================================================
# MAIN ENTRY POINT (backwards compatibility)
# =============================================================================

async def handle_tool_call(name: str, args: Dict[str, Any]) -> List[TextContent]:
    """Handle a tool call - delegates to HandlerRegistry."""
    return await HandlerRegistry.dispatch(name, args)
