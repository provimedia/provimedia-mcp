"""
Symbol Validator for Hallucination Prevention (v2.1)

Core validation logic for detecting hallucinated function calls, method calls,
and property accesses by cross-referencing against actual codebase definitions.

Design Principles (v2.1):
- False Positives NEVER block workflow (WARN mode is default)
- Confidence-based scoring reduces false positives
- Session-aware: tracks newly created symbols
"""

import os
import re
import asyncio
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from difflib import SequenceMatcher
import logging

from .symbol_patterns import (
    Language, EXTENSION_MAP, BUILTINS, COMMON_EXTERNAL_NAMES,
    CompiledPatterns, detect_language, is_builtin, is_common_external,
    has_dynamic_patterns
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SymbolIssue:
    """A potential hallucinated symbol with confidence score."""
    name: str
    file: str
    line: int
    confidence: float  # 0.0 - 1.0
    match_type: str  # 'call', 'definition', 'property'
    context: str = ""
    suggestions: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def severity(self) -> str:
        """Get severity based on confidence."""
        if self.confidence > 0.8:
            return "HIGH"
        elif self.confidence > 0.5:
            return "MEDIUM"
        return "LOW"


class SymbolValidationMode(Enum):
    """Validation modes (v2.1: WARN is default)."""
    OFF = "off"           # Disabled
    WARN = "warn"         # Show warnings, NEVER block (DEFAULT)
    STRICT = "strict"     # Block on high confidence (opt-in)
    ADAPTIVE = "adaptive" # Adapts to context (behaves like WARN in v2.1)


@dataclass
class ValidationResult:
    """Result from symbol validation."""
    issues: List['SymbolIssue']
    confidence: float  # Overall confidence (max of all issues)
    should_block: bool  # Whether to block based on mode and confidence

    @property
    def symbol(self) -> str:
        """Alias for backwards compatibility."""
        return self.issues[0].name if self.issues else ""


# =============================================================================
# SYMBOL EXTRACTOR
# =============================================================================

class SymbolExtractor:
    """Extracts symbols (calls, definitions, properties) from source code."""

    def __init__(self):
        CompiledPatterns.initialize()

    def extract_calls(self, content: str, lang: Language) -> List[Tuple[str, int]]:
        """Extract function/method calls from content.

        Returns: List of (symbol_name, line_number) tuples (deduplicated)
        """
        calls = []
        seen = set()  # For deduplication: (name, line)
        lines = content.split('\n')
        patterns = CompiledPatterns.get_call_patterns(lang)

        # Find lines that are inside docstrings/multi-line comments
        skip_lines = self._find_docstring_lines(content, lang)

        for line_num, line in enumerate(lines, 1):
            # Skip docstring/multi-line comment lines
            if line_num in skip_lines:
                continue

            # Skip single-line comments
            if self._is_comment_line(line, lang):
                continue

            for pattern in patterns:
                for match in pattern.finditer(line):
                    # Get the captured group(s)
                    groups = match.groups()
                    for name in groups:
                        if name and self._is_valid_symbol(name, lang):
                            key = (name, line_num)
                            if key not in seen:
                                seen.add(key)
                                calls.append((name, line_num))

        return calls

    def _find_docstring_lines(self, content: str, lang: Language) -> Set[int]:
        """Find line numbers that are inside docstrings or multi-line comments.

        Returns: Set of line numbers (1-indexed) to skip
        """
        skip_lines = set()
        lines = content.split('\n')

        if lang == Language.PYTHON:
            # Python: triple-quoted strings (""" or ''')
            in_docstring = False
            docstring_char = None

            for line_num, line in enumerate(lines, 1):
                # Count triple quotes on this line
                for quote in ['"""', "'''"]:
                    count = line.count(quote)
                    if count > 0:
                        if not in_docstring:
                            # Starting a docstring
                            in_docstring = True
                            docstring_char = quote
                            skip_lines.add(line_num)
                            # Check if it closes on same line (count >= 2)
                            if count >= 2:
                                in_docstring = False
                                docstring_char = None
                        elif docstring_char == quote:
                            # Closing the docstring
                            skip_lines.add(line_num)
                            in_docstring = False
                            docstring_char = None
                        break
                else:
                    if in_docstring:
                        skip_lines.add(line_num)

        elif lang in (Language.PHP, Language.JAVASCRIPT, Language.TYPESCRIPT,
                      Language.CSHARP, Language.GO, Language.RUST):
            # C-style: /* ... */ multi-line comments
            in_comment = False

            for line_num, line in enumerate(lines, 1):
                if in_comment:
                    skip_lines.add(line_num)
                    if '*/' in line:
                        in_comment = False
                elif '/*' in line:
                    skip_lines.add(line_num)
                    if '*/' not in line:
                        in_comment = True

        return skip_lines

    def extract_definitions(self, content: str, lang: Language) -> Set[str]:
        """Extract function/method/class definitions from content.

        Returns: Set of defined symbol names
        """
        definitions = set()
        patterns = CompiledPatterns.get_definition_patterns(lang)

        for pattern in patterns:
            for match in pattern.finditer(content):
                groups = match.groups()
                for name in groups:
                    if name and self._is_valid_symbol(name, lang):
                        definitions.add(name)

        return definitions

    def extract_properties(self, content: str, lang: Language) -> List[Tuple[str, int]]:
        """Extract property accesses from content.

        Returns: List of (property_name, line_number) tuples
        """
        properties = []
        lines = content.split('\n')
        patterns = CompiledPatterns.get_property_patterns(lang)

        for line_num, line in enumerate(lines, 1):
            if self._is_comment_line(line, lang):
                continue

            for pattern in patterns:
                for match in pattern.finditer(line):
                    groups = match.groups()
                    for name in groups:
                        if name and self._is_valid_symbol(name, lang):
                            properties.append((name, line_num))

        return properties

    def _is_comment_line(self, line: str, lang: Language) -> bool:
        """Check if line is a comment."""
        stripped = line.strip()
        if not stripped:
            return True

        # Single-line comments
        if lang in (Language.PHP, Language.JAVASCRIPT, Language.TYPESCRIPT,
                    Language.CSHARP, Language.GO, Language.RUST):
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                return True
        if lang == Language.PHP and stripped.startswith('#'):
            return True
        if lang == Language.PYTHON and stripped.startswith('#'):
            return True

        return False

    def _is_valid_symbol(self, name: str, lang: Language) -> bool:
        """Check if name is a valid symbol (not a keyword, not too short).

        Note: We only filter TRUE language keywords that can NEVER be function names.
        Function-like keywords (map, where, make, append) are NOT filtered here
        because they ARE valid function names in many frameworks.
        """
        if not name or len(name) < 2:
            return False

        # Only filter TRUE language keywords (control flow, declarations)
        # These can NEVER be function names in any language
        keywords = {
            # Control flow (universal)
            'if', 'else', 'elseif', 'elif', 'for', 'while', 'do', 'switch', 'case',
            'break', 'continue', 'return', 'yield', 'try', 'catch', 'finally',
            'throw', 'throws', 'raise',
            # Declarations (universal)
            'class', 'interface', 'trait', 'struct', 'enum', 'function', 'fn', 'func', 'def',
            'const', 'let', 'var', 'static', 'async', 'await',
            # Modifiers
            'public', 'private', 'protected', 'internal', 'final', 'abstract',
            'virtual', 'override',
            # Literals and special values
            'true', 'false', 'null', 'nil', 'None', 'undefined', 'void',
            # Types (only when they're truly reserved)
            'int', 'float', 'double', 'bool', 'boolean',
            # Special
            'this', 'self', 'super',
            # Module/import related
            'import', 'export', 'default', 'use', 'namespace', 'package', 'module',
            # Rust specific
            'mod', 'pub', 'crate', 'impl', 'loop', 'move', 'mut', 'ref', 'unsafe',
            'extern', 'dyn', 'box',
            # Go specific
            'go', 'defer', 'chan', 'select', 'range', 'type',
        }

        return name.lower() not in keywords


# =============================================================================
# CONFIDENCE CALCULATOR
# =============================================================================

class ConfidenceCalculator:
    """Calculates confidence score for symbol issues.

    Higher confidence = more likely a real hallucination.
    Lower confidence = more likely a false positive.
    """

    def calculate(
        self,
        name: str,
        lang: Language,
        file_content: str,
        has_similar: bool,
        similar_names: List[str]
    ) -> float:
        """Calculate confidence score (0.0 - 1.0).

        Args:
            name: Symbol name
            lang: Programming language
            file_content: Full file content
            has_similar: Whether similar symbols exist in codebase
            similar_names: List of similar symbol names found
        """
        confidence = 1.0

        # 1. Common external name? (-0.3)
        if is_common_external(name):
            confidence -= 0.3

        # 2. File has many imports? (-0.15)
        if self._has_many_imports(file_content, lang):
            confidence -= 0.15

        # 3. Dynamic patterns in file? (-0.25)
        if has_dynamic_patterns(file_content, lang):
            confidence -= 0.25

        # 4. Similar symbol exists? (+0.1 - likely typo)
        if has_similar:
            confidence += 0.1

        # 5. Very short name? (-0.2)
        if len(name) <= 3:
            confidence -= 0.2

        # 6. Looks like external library method? (-0.2)
        if self._looks_like_external(name, lang):
            confidence -= 0.2

        # 7. Common naming patterns? (-0.15)
        if self._is_common_pattern(name):
            confidence -= 0.15

        # 8. CamelCase in snake_case language or vice versa? (-0.1)
        if self._naming_convention_mismatch(name, lang):
            confidence -= 0.1

        return max(0.1, min(1.0, confidence))

    def _has_many_imports(self, content: str, lang: Language) -> bool:
        """Check if file has many imports (suggests external dependencies)."""
        import_patterns = {
            Language.PHP: r'use\s+\w+',
            Language.JAVASCRIPT: r'(?:import|require)\s*\(?',
            Language.TYPESCRIPT: r'(?:import|require)\s*\(?',
            Language.PYTHON: r'(?:import|from)\s+\w+',
            Language.CSHARP: r'using\s+\w+',
            Language.GO: r'import\s+',
            Language.RUST: r'use\s+\w+',
        }

        pattern = import_patterns.get(lang)
        if pattern:
            matches = re.findall(pattern, content)
            return len(matches) > 5

        return False

    def _looks_like_external(self, name: str, lang: Language) -> bool:
        """Check if name looks like an external library method."""
        # Common external prefixes/suffixes
        external_patterns = [
            r'^get[A-Z]', r'^set[A-Z]', r'^is[A-Z]', r'^has[A-Z]',
            r'^on[A-Z]', r'^handle[A-Z]', r'^fetch[A-Z]',
            r'Async$', r'Sync$', r'Callback$', r'Handler$',
        ]

        for pattern in external_patterns:
            if re.match(pattern, name):
                return True

        return False

    def _is_common_pattern(self, name: str) -> bool:
        """Check if name follows common method naming patterns."""
        common_patterns = [
            r'^(get|set|is|has|can|should|will|did|on|before|after)',
            r'^(create|update|delete|find|fetch|load|save|store)',
            r'^(handle|process|execute|perform|run|start|stop)',
            r'^(init|setup|configure|validate|transform|convert)',
            r'^(add|remove|clear|reset|enable|disable)',
        ]

        for pattern in common_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True

        return False

    def _naming_convention_mismatch(self, name: str, lang: Language) -> bool:
        """Check for naming convention mismatch."""
        # Python/Rust use snake_case
        if lang in (Language.PYTHON, Language.RUST, Language.GO):
            # If name is CamelCase in snake_case language
            if re.match(r'^[a-z]+[A-Z]', name):
                return True

        # PHP/JS/TS/C# use camelCase/PascalCase
        if lang in (Language.PHP, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.CSHARP):
            # If name is snake_case in CamelCase language
            if '_' in name and not name.startswith('_'):
                return True

        return False


# =============================================================================
# SYMBOL VALIDATOR
# =============================================================================

class SymbolValidator:
    """Main validator for detecting hallucinated symbols."""

    def __init__(
        self,
        working_dir: str,
        session_symbols: Optional[Set[str]] = None,
        whitelist: Optional[Set[str]] = None
    ):
        """Initialize validator.

        Args:
            working_dir: Project root directory
            session_symbols: Symbols defined in current session (not hallucinations)
            whitelist: User-defined whitelist (known false positives)
        """
        self.working_dir = Path(working_dir)
        self.session_symbols = session_symbols or set()
        self.whitelist = whitelist or set()
        self.extractor = SymbolExtractor()
        self.confidence_calc = ConfidenceCalculator()

        # Caches
        self._definition_cache: Dict[Language, Set[str]] = {}
        self._file_cache: Dict[str, str] = {}

    def validate_file(self, file_path: str) -> List[SymbolIssue]:
        """Validate a single file for hallucinated symbols.

        Returns: List of SymbolIssue objects
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.working_dir / path

        if not path.exists():
            return []

        lang = detect_language(str(path))
        if not lang:
            return []

        content = self._read_file(path)
        if not content:
            return []

        issues = []

        # Get all definitions in codebase for this language
        all_definitions = self._get_all_definitions(lang)

        # Extract calls and properties from file
        calls = self.extractor.extract_calls(content, lang)
        # Note: Property validation is more prone to false positives, so we skip it for now
        # properties = self.extractor.extract_properties(content, lang)

        # Also extract definitions from this file (same-file definitions are valid)
        local_definitions = self.extractor.extract_definitions(content, lang)

        # Check each call
        for name, line in calls:
            issue = self._check_symbol(
                name=name,
                line=line,
                file_path=str(path.relative_to(self.working_dir) if path.is_relative_to(self.working_dir) else path),
                match_type='call',
                lang=lang,
                content=content,
                all_definitions=all_definitions,
                local_definitions=local_definitions
            )
            if issue:
                issues.append(issue)

        return issues

    def _check_symbol(
        self,
        name: str,
        line: int,
        file_path: str,
        match_type: str,
        lang: Language,
        content: str,
        all_definitions: Set[str],
        local_definitions: Set[str]
    ) -> Optional[SymbolIssue]:
        """Check if a symbol is potentially hallucinated."""

        # Skip if builtin
        if is_builtin(name, lang):
            return None

        # Skip if whitelisted
        if name in self.whitelist:
            return None

        # Skip if defined in session
        if name in self.session_symbols:
            return None

        # Skip if defined locally (same file)
        if name in local_definitions:
            return None

        # Skip if defined anywhere in codebase
        if name in all_definitions:
            return None

        # At this point, the symbol was not found - calculate confidence
        similar_names = self._find_similar(name, all_definitions)
        has_similar = len(similar_names) > 0

        confidence = self.confidence_calc.calculate(
            name=name,
            lang=lang,
            file_content=content,
            has_similar=has_similar,
            similar_names=similar_names
        )

        # Get context line
        lines = content.split('\n')
        context = lines[line - 1].strip() if 0 < line <= len(lines) else ""

        # Build reason
        reason = "Symbol not found in codebase"
        if has_similar:
            reason = f"Possibly misspelled. Similar: {', '.join(similar_names[:3])}"

        return SymbolIssue(
            name=name,
            file=file_path,
            line=line,
            confidence=confidence,
            match_type=match_type,
            context=context,
            suggestions=similar_names[:5],
            reason=reason
        )

    def _get_all_definitions(self, lang: Language) -> Set[str]:
        """Get all symbol definitions in codebase for a language."""
        if lang in self._definition_cache:
            return self._definition_cache[lang]

        definitions = set()

        # Get file extension for this language
        extensions = [ext for ext, l in EXTENSION_MAP.items() if l == lang]

        # Scan files
        for ext in extensions:
            for file_path in self.working_dir.rglob(f'*{ext}'):
                # Skip common non-source directories
                if self._should_skip_path(file_path):
                    continue

                content = self._read_file(file_path)
                if content:
                    file_defs = self.extractor.extract_definitions(content, lang)
                    definitions.update(file_defs)

        self._definition_cache[lang] = definitions
        return definitions

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped during scanning."""
        skip_dirs = {
            'node_modules', 'vendor', '.git', '__pycache__', '.venv', 'venv',
            'env', '.env', 'dist', 'build', 'target', 'bin', 'obj', '.idea',
            '.vscode', 'coverage', '.pytest_cache', '.mypy_cache', '.tox',
        }

        parts = path.parts
        for part in parts:
            if part in skip_dirs:
                return True

        return False

    def _read_file(self, path: Path) -> str:
        """Read file content with caching."""
        key = str(path)
        if key in self._file_cache:
            return self._file_cache[key]

        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            self._file_cache[key] = content
            return content
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return ""

    def _find_similar(self, name: str, definitions: Set[str], threshold: float = 0.6) -> List[str]:
        """Find similar symbol names using string similarity."""
        similar = []

        for defined in definitions:
            ratio = SequenceMatcher(None, name.lower(), defined.lower()).ratio()
            if ratio >= threshold:
                similar.append((defined, ratio))

        # Sort by similarity (descending)
        similar.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in similar]

    # ==========================================================================
    # CLASS-LEVEL METHODS (Static API for handlers)
    # ==========================================================================

    _global_mode: SymbolValidationMode = SymbolValidationMode.WARN

    @classmethod
    def set_mode(cls, mode: SymbolValidationMode) -> None:
        """Set the global validation mode."""
        cls._global_mode = mode

    @classmethod
    def get_mode(cls) -> SymbolValidationMode:
        """Get the current validation mode."""
        return cls._global_mode

    @classmethod
    def validate(
        cls,
        code: str,
        file_path: str,
        known_symbols: Optional[Set[str]] = None
    ) -> ValidationResult:
        """Validate code against known symbols (static interface).

        Args:
            code: Source code to validate
            file_path: File path (for language detection)
            known_symbols: Set of known valid symbols from codebase

        Returns:
            ValidationResult with issues, confidence, and should_block
        """
        # Check mode first
        if cls._global_mode == SymbolValidationMode.OFF:
            return ValidationResult(issues=[], confidence=0.0, should_block=False)

        lang = detect_language(file_path)
        if not lang:
            return ValidationResult(issues=[], confidence=0.0, should_block=False)

        extractor = SymbolExtractor()
        confidence_calc = ConfidenceCalculator()

        # Extract calls and definitions
        calls = extractor.extract_calls(code, lang)
        local_definitions = extractor.extract_definitions(code, lang)

        all_known = (known_symbols or set()) | local_definitions

        issues = []
        for name, line in calls:
            # Skip builtins
            if is_builtin(name, lang):
                continue

            # Skip if known
            if name in all_known:
                continue

            # Skip common external names
            if is_common_external(name):
                continue

            # Check if file has dynamic patterns (reduces confidence)
            has_dynamic = has_dynamic_patterns(code, lang)

            # Calculate confidence
            confidence = confidence_calc.calculate(
                name=name,
                lang=lang,
                file_content=code,
                has_similar=False,  # Simple check, no similar name lookup
                similar_names=[]
            )

            # Dynamic patterns reduce confidence
            if has_dynamic:
                confidence *= 0.5

            # Get context line
            lines = code.split('\n')
            context = lines[line - 1].strip() if 0 < line <= len(lines) else ""

            issues.append(SymbolIssue(
                name=name,
                file=file_path,
                line=line,
                confidence=confidence,
                match_type='call',
                context=context,
                suggestions=[],
                reason="Symbol not found in codebase"
            ))

        # Calculate overall confidence
        max_confidence = max((i.confidence for i in issues), default=0.0)

        # v2.1: Only block in STRICT mode with high confidence
        should_block = (
            cls._global_mode == SymbolValidationMode.STRICT and
            max_confidence > 0.9 and
            len([i for i in issues if i.confidence > 0.8]) >= 5
        )

        return ValidationResult(
            issues=issues,
            confidence=max_confidence,
            should_block=should_block
        )


# =============================================================================
# ASYNC SYMBOL VALIDATOR
# =============================================================================

class AsyncSymbolValidator(SymbolValidator):
    """Async version of SymbolValidator for better performance."""

    async def validate_files_async(self, file_paths: List[str]) -> List[SymbolIssue]:
        """Validate multiple files asynchronously."""
        tasks = [
            asyncio.to_thread(self.validate_file, fp)
            for fp in file_paths
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        issues = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Validation error: {result}")
            elif isinstance(result, list):
                issues.extend(result)

        return issues

    async def quality_check_async(
        self,
        file_paths: List[str],
        whitelist: Optional[Set[str]] = None
    ) -> List[SymbolIssue]:
        """Run quality check on multiple files.

        Args:
            file_paths: List of files to check
            whitelist: Additional whitelist symbols
        """
        if whitelist:
            self.whitelist.update(whitelist)

        return await self.validate_files_async(file_paths)


# =============================================================================
# ADAPTIVE SYMBOL VALIDATION
# =============================================================================

# Patterns for strict mode (critical files)
SYMBOL_STRICT_PATTERNS = [
    r'Controller\.', r'Service\.', r'Repository\.',
    r'Api/', r'Handler\.', r'Middleware\.',
    r'UseCase\.', r'Command\.', r'Query\.',
]

# Patterns for relaxed mode (test/config files)
SYMBOL_RELAXED_PATTERNS = [
    r'/test', r'/tests', r'Test\.', r'Spec\.',
    r'/config', r'/migrations', r'/seeds',
    r'\.config\.', r'\.env',
]


class AdaptiveSymbolValidation:
    """Context-based symbol validation mode selection (v2.1)."""

    def get_mode_for_file(
        self,
        file: str,
        strict_files: Optional[Set[str]] = None,
        ignore_files: Optional[Set[str]] = None
    ) -> SymbolValidationMode:
        """Determine validation mode based on file context.

        Args:
            file: File path
            strict_files: User-defined strict files
            ignore_files: User-defined ignored files
        """
        strict_files = strict_files or set()
        ignore_files = ignore_files or set()

        # 1. User overrides have highest priority
        if file in strict_files:
            return SymbolValidationMode.STRICT
        if file in ignore_files:
            return SymbolValidationMode.OFF

        # 2. Critical files -> STRICT (but only if user opted in globally)
        # v2.1: We don't auto-escalate to STRICT anymore
        # for pattern in SYMBOL_STRICT_PATTERNS:
        #     if re.search(pattern, file, re.IGNORECASE):
        #         return SymbolValidationMode.STRICT

        # 3. Test/Config files -> WARN only
        for pattern in SYMBOL_RELAXED_PATTERNS:
            if re.search(pattern, file, re.IGNORECASE):
                return SymbolValidationMode.WARN

        # 4. Default -> WARN (v2.1: changed from ADAPTIVE)
        return SymbolValidationMode.WARN

    def should_block(
        self,
        issues: List[SymbolIssue],
        mode: SymbolValidationMode
    ) -> bool:
        """Determine if finish should be blocked.

        v2.1: Only STRICT can block, and only with very high thresholds.
        """
        # OFF, WARN, ADAPTIVE: NEVER block
        if mode in (SymbolValidationMode.OFF,
                    SymbolValidationMode.WARN,
                    SymbolValidationMode.ADAPTIVE):
            return False

        # STRICT: Block only with very high confidence issues
        if mode == SymbolValidationMode.STRICT:
            # v2.1: Higher thresholds
            # - Confidence must be > 0.9 (was 0.8)
            # - At least 5 issues (was 3)
            very_high = [i for i in issues if i.confidence > 0.9]
            return len(very_high) >= 5

        return False

    def get_effective_mode(
        self,
        files: List[str],
        user_mode: Optional[SymbolValidationMode] = None,
        strict_files: Optional[Set[str]] = None,
        ignore_files: Optional[Set[str]] = None
    ) -> SymbolValidationMode:
        """Determine effective mode for a list of files.

        v2.1: Changed from "strictest wins" to "safest default".
        """
        # User override has highest priority
        if user_mode == SymbolValidationMode.STRICT:
            return SymbolValidationMode.STRICT
        if user_mode == SymbolValidationMode.OFF:
            return SymbolValidationMode.OFF

        modes = [
            self.get_mode_for_file(f, strict_files, ignore_files)
            for f in files
        ]

        # v2.1: STRICT only if ALL files require it (very rare)
        if all(m == SymbolValidationMode.STRICT for m in modes) and modes:
            return SymbolValidationMode.STRICT

        # Default: WARN (safe)
        return SymbolValidationMode.WARN


# =============================================================================
# REPORT FORMATTER
# =============================================================================

def format_issues_report(
    issues: List[SymbolIssue],
    mode: SymbolValidationMode = SymbolValidationMode.WARN
) -> str:
    """Format issues as a readable report.

    Args:
        issues: List of issues to format
        mode: Current validation mode
    """
    if not issues:
        return "Symbol Validation: All symbols verified"

    # Group by severity
    high = [i for i in issues if i.severity == "HIGH"]
    medium = [i for i in issues if i.severity == "MEDIUM"]
    low = [i for i in issues if i.severity == "LOW"]

    parts = [f"Symbol Validation: {len(issues)} potential issues (mode: {mode.value})"]
    parts.append("")

    if high:
        parts.append("HIGH CONFIDENCE (likely issues):")
        for issue in high[:5]:  # Max 5
            parts.append(f"  {issue.name}() in {issue.file}:{issue.line} [{issue.confidence:.0%}]")
            if issue.suggestions:
                parts.append(f"    -> Did you mean: {', '.join(issue.suggestions[:3])}?")
        if len(high) > 5:
            parts.append(f"  ... and {len(high) - 5} more")
        parts.append("")

    if medium:
        parts.append("MEDIUM CONFIDENCE (review recommended):")
        for issue in medium[:3]:  # Max 3
            parts.append(f"  {issue.name}() in {issue.file}:{issue.line} [{issue.confidence:.0%}]")
        if len(medium) > 3:
            parts.append(f"  ... and {len(medium) - 3} more")
        parts.append("")

    if low:
        parts.append(f"LOW CONFIDENCE: {len(low)} items (likely OK)")
        parts.append("")

    # v2.1: Never show blocking message unless in STRICT mode
    if mode == SymbolValidationMode.STRICT and high:
        parts.append("Use force=True or chainguard_symbol_mode(mode='warn') to proceed.")
    else:
        parts.append("These are warnings only. Use chainguard_symbol_feedback() to report false positives.")

    return "\n".join(parts)
