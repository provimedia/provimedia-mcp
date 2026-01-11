"""
Symbol Patterns for Hallucination Prevention (v2.2)

Regex patterns for extracting function calls, definitions, and properties
across 7 programming languages: PHP, JavaScript, TypeScript, Python, C#, Go, Rust.

Design Principle: Regex is "good enough" (~90% accuracy) and much faster than AST parsing.

v2.2: Added lazy-loading of PHP builtins from generated JSON (5000+ functions)
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Set, Pattern, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Language(Enum):
    """Supported programming languages."""
    PHP = "php"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    PYTHON = "python"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"


# File extension to language mapping
EXTENSION_MAP: Dict[str, Language] = {
    '.php': Language.PHP,
    '.js': Language.JAVASCRIPT,
    '.mjs': Language.JAVASCRIPT,
    '.cjs': Language.JAVASCRIPT,
    '.jsx': Language.JAVASCRIPT,
    '.ts': Language.TYPESCRIPT,
    '.tsx': Language.TYPESCRIPT,
    '.mts': Language.TYPESCRIPT,
    '.py': Language.PYTHON,
    '.pyw': Language.PYTHON,
    '.cs': Language.CSHARP,
    '.go': Language.GO,
    '.rs': Language.RUST,
}


@dataclass
class SymbolMatch:
    """A matched symbol (function call, definition, or property)."""
    name: str
    line: int
    column: int
    match_type: str  # 'call', 'definition', 'property'
    context: str  # surrounding code for context


# =============================================================================
# CALL PATTERNS - Patterns for function/method calls
# =============================================================================

CALL_PATTERNS: Dict[Language, List[str]] = {
    Language.PHP: [
        # Simple function call: functionName(...)
        r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Method call: $obj->methodName(...)
        r'->\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Static call: ClassName::methodName(...) - only capture method, not class
        r'(?:[A-Z][a-zA-Z0-9_]*)::([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Null-safe method call: $obj?->methodName(...)
        r'\?->\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    ],

    Language.JAVASCRIPT: [
        # Function call: functionName(...)
        r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # Method call: obj.methodName(...)
        r'\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # Optional chaining: obj?.methodName(...)
        r'\?\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
    ],

    Language.TYPESCRIPT: [
        # Inherit JavaScript patterns
        r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        r'\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        r'\?\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # Generic call: methodName<Type>(...)
        r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*<[^>]+>\s*\(',
    ],

    Language.PYTHON: [
        # Function call: function_name(...) or camelCase(...)
        r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Method call: obj.method_name(...)
        r'\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    ],

    Language.CSHARP: [
        # Method call: MethodName(...)
        r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        # Instance method: obj.MethodName(...)
        r'\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        # Static call: ClassName.MethodName(...) - only capture method, not class
        r'(?:[A-Z][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        # Generic call: MethodName<Type>(...)
        r'\b([A-Za-z_][A-Za-z0-9_]*)\s*<[^>]+>\s*\(',
        # Await call: await MethodName(...)
        r'await\s+(?:\w+\s*\.\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        # Null-conditional: obj?.MethodName(...)
        r'\?\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(',
    ],

    Language.GO: [
        # Function call: functionName(...)
        r'\b([a-z][a-zA-Z0-9]*)\s*\(',
        # Exported function: FunctionName(...)
        r'\b([A-Z][a-zA-Z0-9]*)\s*\(',
        # Method call: obj.MethodName(...)
        r'\.\s*([A-Z][a-zA-Z0-9]*)\s*\(',
        # Package call: pkg.FunctionName(...) - only capture function, not package
        r'(?:[a-z][a-zA-Z0-9]*)\s*\.\s*([A-Z][a-zA-Z0-9]*)\s*\(',
    ],

    Language.RUST: [
        # Function call: function_name(...) or camelCase
        r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Method call: obj.method_name(...)
        r'\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Turbofish: function_name::<Type>(...)
        r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*::\s*<[^>]+>\s*\(',
        # Associated function: Type::function_name(...) - only capture function, not type
        r'(?:[A-Z][a-zA-Z0-9]*)\s*::\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # Macro call: macro_name!(...)
        r'\b([a-z_][a-z0-9_]*)\s*!\s*[(\[]',
    ],
}


# =============================================================================
# DEFINITION PATTERNS - Patterns for function/method definitions
# =============================================================================

DEFINITION_PATTERNS: Dict[Language, List[str]] = {
    Language.PHP: [
        # function name(...) {
        r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
        # public/private/protected function name(...)
        r'(?:public|private|protected)\s+(?:static\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    ],

    Language.JAVASCRIPT: [
        # function name(...) {
        r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # const/let/var name = (...) =>
        r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        # const/let/var name = function(...)
        r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?function',
        # Class method: methodName(...) {
        r'^\s*(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{',
        # Static/async method
        r'(?:static\s+)?(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{',
    ],

    Language.TYPESCRIPT: [
        # Inherit JavaScript patterns plus:
        r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]+>)?\s*\(',
        r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?function',
        # Typed function: function name(arg: Type): ReturnType {
        r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]+>)?\s*\([^)]*\)\s*:\s*\w+',
        # Interface method: methodName(arg: Type): ReturnType;
        r'^\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]+>)?\s*\([^)]*\)\s*:\s*\w+\s*;',
        # Class method with REQUIRED modifier (at least one must be present)
        r'(?:public|private|protected)\s+(?:static\s+)?(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # Static method (static is required)
        r'static\s+(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',
        # Async method: async methodName(): Type
        r'async\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*:\s*\w+',
        # Abstract method: abstract methodName(): Type;
        r'abstract\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*:\s*\w+',
        # Method with return type annotation inside class: methodName(): Type {
        r'^\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*:\s*\w+[^;]*\{',
    ],

    Language.PYTHON: [
        # def function_name(...):
        r'def\s+([a-z_][a-z0-9_]*)\s*\(',
        # async def function_name(...):
        r'async\s+def\s+([a-z_][a-z0-9_]*)\s*\(',
        # class ClassName:
        r'class\s+([A-Z][a-zA-Z0-9_]*)\s*[:\(]',
    ],

    Language.CSHARP: [
        # Standard method: public void MethodName(...)
        r'(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:override\s+)?(?:virtual\s+)?(?:abstract\s+)?(?:\w+(?:<[^>]+>)?)\s+([A-Z][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(',
        # Constructor: public ClassName(...)
        r'(?:public|private|protected|internal)\s+([A-Z][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?::|{)',
        # Expression-bodied: public int GetValue() =>
        r'(?:public|private|protected|internal)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+([A-Z][A-Za-z0-9_]*)\s*\([^)]*\)\s*=>',
        # Interface method
        r'^\s*(?:\w+(?:<[^>]+>)?)\s+([A-Z][A-Za-z0-9_]*)\s*\([^)]*\)\s*;',
    ],

    Language.GO: [
        # func functionName(...) {
        r'func\s+([a-zA-Z][a-zA-Z0-9]*)\s*\(',
        # func (r *Receiver) MethodName(...) {
        r'func\s+\([^)]+\)\s+([A-Z][a-zA-Z0-9]*)\s*\(',
        # type StructName struct {
        r'type\s+([A-Z][a-zA-Z0-9]*)\s+struct\s*\{',
        # type InterfaceName interface {
        r'type\s+([A-Z][a-zA-Z0-9]*)\s+interface\s*\{',
    ],

    Language.RUST: [
        # fn function_name(...) {
        r'fn\s+([a-z_][a-z0-9_]*)\s*(?:<[^>]+>)?\s*\(',
        # pub fn function_name(...) {
        r'pub\s+(?:async\s+)?fn\s+([a-z_][a-z0-9_]*)\s*(?:<[^>]+>)?\s*\(',
        # struct StructName {
        r'(?:pub\s+)?struct\s+([A-Z][a-zA-Z0-9]*)',
        # enum EnumName {
        r'(?:pub\s+)?enum\s+([A-Z][a-zA-Z0-9]*)',
        # trait TraitName {
        r'(?:pub\s+)?trait\s+([A-Z][a-zA-Z0-9]*)',
        # impl block
        r'impl(?:<[^>]+>)?\s+([A-Z][a-zA-Z0-9]*)',
    ],
}


# =============================================================================
# PROPERTY PATTERNS - Patterns for property/field access
# =============================================================================

PROPERTY_PATTERNS: Dict[Language, List[str]] = {
    Language.PHP: [
        # public $propertyName;
        r'(?:public|private|protected)\s+\$([a-zA-Z_][a-zA-Z0-9_]*)',
        # $this->propertyName
        r'\$this\s*->\s*([a-zA-Z_][a-zA-Z0-9_]*)',
    ],

    Language.JAVASCRIPT: [
        # this.propertyName
        r'this\s*\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)',
        # obj.propertyName (without parentheses = not a call)
        r'\.([a-zA-Z_$][a-zA-Z0-9_$]*)(?!\s*\()',
    ],

    Language.TYPESCRIPT: [
        # Inherit JavaScript patterns
        r'this\s*\.\s*([a-zA-Z_$][a-zA-Z0-9_$]*)',
        r'\.([a-zA-Z_$][a-zA-Z0-9_$]*)(?!\s*[<(])',
    ],

    Language.PYTHON: [
        # self.property_name = ...
        r'self\s*\.\s*([a-z_][a-z0-9_]*)\s*=',
        # self.property_name (access)
        r'self\s*\.\s*([a-z_][a-z0-9_]*)',
    ],

    Language.CSHARP: [
        # Auto-Property: public string Name { get; set; }
        r'(?:public|private|protected|internal)\s+(?:static\s+)?(?:virtual\s+)?(?:\w+(?:<[^>]+>)?)\s+([A-Z][A-Za-z0-9_]*)\s*\{\s*get',
        # Field: private int _fieldName;
        r'(?:private|protected)\s+(?:readonly\s+)?(?:\w+(?:<[^>]+>)?)\s+(_[a-z][A-Za-z0-9_]*)\s*[;=]',
    ],

    Language.GO: [
        # struct.FieldName
        r'\.([A-Z][a-zA-Z0-9]*)\b(?!\s*\()',
    ],

    Language.RUST: [
        # struct.field_name
        r'\.([a-z_][a-z0-9_]*)(?!\s*[(<])',
    ],
}


# =============================================================================
# BUILTIN FUNCTIONS - Functions that should be ignored (not hallucinations)
# =============================================================================

BUILTINS: Dict[Language, Set[str]] = {
    Language.PHP: {
        # Language constructs (these look like function calls but are keywords)
        'isset', 'empty', 'array', 'list', 'echo', 'print', 'die', 'exit',
        'include', 'include_once', 'require', 'require_once', 'eval',
        'foreach', 'while', 'for', 'if', 'elseif', 'else', 'switch', 'case',
        'catch', 'match', 'fn', 'unset', 'declare', 'enddeclare',
        'endfor', 'endforeach', 'endif', 'endswitch', 'endwhile',
        # Type functions
        'is_array', 'is_string', 'is_null', 'is_numeric', 'is_object', 'is_bool',
        'is_int', 'is_float', 'is_callable', 'is_resource', 'gettype', 'settype',
        'intval', 'floatval', 'strval', 'boolval', 'arrayval',
        # String functions
        'strlen', 'strpos', 'stripos', 'strrpos', 'strripos', 'substr', 'str_replace',
        'str_ireplace', 'strtolower', 'strtoupper', 'ucfirst', 'lcfirst', 'ucwords',
        'trim', 'ltrim', 'rtrim', 'str_pad', 'str_repeat', 'str_split', 'str_word_count',
        'sprintf', 'printf', 'sscanf', 'number_format', 'money_format',
        'explode', 'implode', 'join', 'chunk_split', 'wordwrap', 'nl2br',
        'htmlspecialchars', 'htmlentities', 'strip_tags', 'addslashes', 'stripslashes',
        'preg_match', 'preg_match_all', 'preg_replace', 'preg_split', 'preg_grep',
        'str_contains', 'str_starts_with', 'str_ends_with',
        # Array functions
        'count', 'sizeof', 'array_push', 'array_pop', 'array_shift', 'array_unshift',
        'array_merge', 'array_combine', 'array_keys', 'array_values', 'array_flip',
        'array_reverse', 'array_slice', 'array_splice', 'array_chunk', 'array_unique',
        'array_filter', 'array_map', 'array_reduce', 'array_walk', 'array_search',
        'in_array', 'array_key_exists', 'array_column', 'array_fill', 'array_pad',
        'sort', 'rsort', 'asort', 'arsort', 'ksort', 'krsort', 'usort', 'uasort', 'uksort',
        'array_multisort', 'shuffle', 'array_rand', 'current', 'key', 'next', 'prev', 'reset', 'end',
        # JSON functions
        'json_encode', 'json_decode', 'json_last_error', 'json_last_error_msg',
        # File functions
        'file_get_contents', 'file_put_contents', 'file_exists', 'is_file', 'is_dir',
        'fopen', 'fclose', 'fread', 'fwrite', 'fgets', 'fgetc', 'feof', 'fseek', 'ftell',
        'file', 'readfile', 'glob', 'scandir', 'mkdir', 'rmdir', 'unlink', 'rename', 'copy',
        'dirname', 'basename', 'pathinfo', 'realpath', 'is_readable', 'is_writable',
        # Date/Time
        'date', 'time', 'mktime', 'strtotime', 'getdate', 'localtime', 'checkdate',
        'date_create', 'date_format', 'date_modify', 'date_diff', 'date_add', 'date_sub',
        # Math
        'abs', 'ceil', 'floor', 'round', 'max', 'min', 'pow', 'sqrt', 'log', 'log10',
        'rand', 'mt_rand', 'random_int', 'random_bytes',
        # Variable handling
        'var_dump', 'print_r', 'var_export', 'debug_zval_dump', 'serialize', 'unserialize',
        # Class/Object
        'class_exists', 'interface_exists', 'trait_exists', 'method_exists', 'property_exists',
        'get_class', 'get_parent_class', 'get_class_methods', 'get_class_vars', 'get_object_vars',
        # Magic methods
        '__construct', '__destruct', '__call', '__callStatic', '__get', '__set', '__isset',
        '__unset', '__sleep', '__wakeup', '__serialize', '__unserialize', '__toString',
        '__invoke', '__set_state', '__clone', '__debugInfo',
        # Error handling
        'trigger_error', 'user_error', 'error_reporting', 'set_error_handler',
        # Sessions
        'session_start', 'session_destroy', 'session_regenerate_id', 'session_id',
        # Header/Output
        'header', 'headers_sent', 'setcookie', 'setrawcookie', 'ob_start', 'ob_end_flush',
        'ob_end_clean', 'ob_get_contents', 'ob_flush', 'flush',
        # Misc
        'defined', 'define', 'constant', 'compact', 'extract', 'call_user_func',
        'call_user_func_array', 'func_get_args', 'func_num_args',
        # SQL functions commonly used in PHP code (v6.4.4)
        # These appear inside SQL queries and should not be flagged
        'curdate', 'curtime', 'now', 'current_date', 'current_time', 'current_timestamp',
        'date_format', 'date_add', 'date_sub', 'datediff', 'timediff', 'timestampdiff',
        'year', 'month', 'day', 'hour', 'minute', 'second', 'dayofweek', 'dayofmonth', 'dayofyear',
        'weekday', 'weekofyear', 'week', 'quarter', 'last_day', 'makedate', 'maketime',
        'concat', 'concat_ws', 'substring', 'substr', 'left', 'right', 'lpad', 'rpad',
        'upper', 'lower', 'trim', 'ltrim', 'rtrim', 'reverse', 'replace', 'insert',
        'coalesce', 'ifnull', 'nullif', 'isnull', 'greatest', 'least',
        'sum', 'avg', 'min', 'max', 'count', 'group_concat',
        'abs', 'ceil', 'ceiling', 'floor', 'round', 'truncate', 'mod', 'pow', 'power', 'sqrt',
        'rand', 'sign', 'pi', 'exp', 'ln', 'log', 'log10', 'log2',
        'cast', 'convert', 'binary',
        'if', 'case', 'when', 'then', 'else', 'end',
        'exists', 'not', 'and', 'or', 'in', 'between', 'like', 'regexp', 'rlike',
        'asc', 'desc', 'limit', 'offset', 'order', 'by', 'group', 'having', 'distinct',
        'inner', 'outer', 'left', 'right', 'cross', 'join', 'on', 'using',
        'insert', 'update', 'delete', 'select', 'from', 'where', 'set', 'into', 'values',
    },

    Language.JAVASCRIPT: {
        # Console
        'console', 'log', 'warn', 'error', 'info', 'debug', 'trace', 'table', 'dir',
        'assert', 'clear', 'count', 'countReset', 'group', 'groupEnd', 'time', 'timeEnd',
        # Timers
        'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
        'requestAnimationFrame', 'cancelAnimationFrame',
        # Type conversion
        'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'Number', 'String', 'Boolean',
        # JSON
        'JSON', 'parse', 'stringify',
        # Object
        'Object', 'keys', 'values', 'entries', 'assign', 'freeze', 'seal', 'create',
        'defineProperty', 'defineProperties', 'getOwnPropertyNames', 'getPrototypeOf',
        'hasOwnProperty', 'isPrototypeOf', 'propertyIsEnumerable',
        # Array
        'Array', 'from', 'isArray', 'of', 'map', 'filter', 'reduce', 'reduceRight',
        'forEach', 'find', 'findIndex', 'findLast', 'findLastIndex', 'includes',
        'indexOf', 'lastIndexOf', 'some', 'every', 'flat', 'flatMap',
        'slice', 'splice', 'concat', 'join', 'reverse', 'sort', 'fill', 'copyWithin',
        'push', 'pop', 'shift', 'unshift', 'at', 'with', 'toSorted', 'toReversed',
        # String
        'charAt', 'charCodeAt', 'codePointAt', 'concat', 'endsWith', 'startsWith',
        'includes', 'indexOf', 'lastIndexOf', 'localeCompare', 'match', 'matchAll',
        'normalize', 'padEnd', 'padStart', 'repeat', 'replace', 'replaceAll',
        'search', 'slice', 'split', 'substring', 'toLowerCase', 'toUpperCase',
        'trim', 'trimStart', 'trimEnd', 'valueOf', 'toString', 'at',
        # Promise
        'Promise', 'resolve', 'reject', 'all', 'allSettled', 'race', 'any',
        'then', 'catch', 'finally',
        # Fetch/Network
        'fetch', 'Request', 'Response', 'Headers', 'URL', 'URLSearchParams',
        # Math
        'Math', 'abs', 'ceil', 'floor', 'round', 'random', 'max', 'min', 'pow', 'sqrt',
        'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2', 'log', 'log10', 'log2',
        'exp', 'sign', 'trunc', 'cbrt', 'hypot', 'clz32', 'imul', 'fround',
        # Date
        'Date', 'now', 'getTime', 'getFullYear', 'getMonth', 'getDate', 'getDay',
        'getHours', 'getMinutes', 'getSeconds', 'getMilliseconds', 'toISOString',
        'toJSON', 'toDateString', 'toTimeString', 'toLocaleDateString', 'toLocaleTimeString',
        # Error
        'Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError',
        'EvalError', 'URIError', 'AggregateError',
        # Encoding
        'encodeURI', 'encodeURIComponent', 'decodeURI', 'decodeURIComponent',
        'btoa', 'atob',
        # RegExp
        'RegExp', 'test', 'exec',
        # Modules
        'require', 'module', 'exports', 'import', 'export', 'default',
        # DOM (if in browser)
        'document', 'window', 'navigator', 'location', 'history', 'localStorage', 'sessionStorage',
        'getElementById', 'getElementsByClassName', 'getElementsByTagName', 'getElementsByName',
        'querySelector', 'querySelectorAll', 'createElement', 'createTextNode',
        'appendChild', 'removeChild', 'insertBefore', 'replaceChild', 'cloneNode',
        'addEventListener', 'removeEventListener', 'dispatchEvent',
        'getAttribute', 'setAttribute', 'removeAttribute', 'hasAttribute',
        'classList', 'add', 'remove', 'toggle', 'contains', 'replace',
        'style', 'innerText', 'innerHTML', 'textContent', 'value',
        'preventDefault', 'stopPropagation', 'stopImmediatePropagation',
        # Symbols
        'Symbol', 'iterator', 'asyncIterator', 'toStringTag', 'species',
        # Reflect/Proxy
        'Reflect', 'Proxy', 'apply', 'construct', 'deleteProperty', 'get', 'set',
        # TypedArrays
        'ArrayBuffer', 'DataView', 'Int8Array', 'Uint8Array', 'Uint8ClampedArray',
        'Int16Array', 'Uint16Array', 'Int32Array', 'Uint32Array',
        'Float32Array', 'Float64Array', 'BigInt64Array', 'BigUint64Array',
        # Maps/Sets
        'Map', 'Set', 'WeakMap', 'WeakSet', 'has', 'get', 'set', 'delete', 'clear', 'size',
        # Misc
        'eval', 'globalThis', 'undefined', 'null', 'NaN', 'Infinity',
        'queueMicrotask', 'structuredClone', 'crypto', 'getRandomValues',
        # Web APIs - Observers (v6.4.4)
        'IntersectionObserver', 'MutationObserver', 'ResizeObserver',
        'PerformanceObserver', 'ReportingObserver',
        'observe', 'unobserve', 'disconnect', 'takeRecords',
        # Web APIs - Other
        'FormData', 'Blob', 'File', 'FileReader', 'FileList',
        'XMLHttpRequest', 'WebSocket', 'EventSource', 'BroadcastChannel',
        'Worker', 'SharedWorker', 'ServiceWorker', 'MessageChannel', 'MessagePort',
        'CustomEvent', 'Event', 'EventTarget',
        'AbortController', 'AbortSignal',
        'TextEncoder', 'TextDecoder',
        'DOMParser', 'XMLSerializer',
        'requestIdleCallback', 'cancelIdleCallback',
        'matchMedia', 'MediaQueryList',
        'getComputedStyle', 'getBoundingClientRect', 'getClientRects',
        'scrollTo', 'scrollBy', 'scrollIntoView',
        'focus', 'blur', 'click', 'submit', 'reset',
    },

    Language.TYPESCRIPT: set(),  # Will inherit from JavaScript

    Language.PYTHON: {
        # Built-in functions
        'abs', 'aiter', 'all', 'any', 'anext', 'ascii', 'bin', 'bool', 'breakpoint',
        'bytearray', 'bytes', 'callable', 'chr', 'classmethod', 'compile', 'complex',
        'delattr', 'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
        'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help',
        'hex', 'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list',
        'locals', 'map', 'max', 'memoryview', 'min', 'next', 'object', 'oct', 'open',
        'ord', 'pow', 'print', 'property', 'range', 'repr', 'reversed', 'round', 'set',
        'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple',
        'type', 'vars', 'zip',
        # String methods
        'capitalize', 'casefold', 'center', 'count', 'encode', 'endswith', 'expandtabs',
        'find', 'format', 'format_map', 'index', 'isalnum', 'isalpha', 'isascii',
        'isdecimal', 'isdigit', 'isidentifier', 'islower', 'isnumeric', 'isprintable',
        'isspace', 'istitle', 'isupper', 'join', 'ljust', 'lower', 'lstrip', 'maketrans',
        'partition', 'removeprefix', 'removesuffix', 'replace', 'rfind', 'rindex',
        'rjust', 'rpartition', 'rsplit', 'rstrip', 'split', 'splitlines', 'startswith',
        'strip', 'swapcase', 'title', 'translate', 'upper', 'zfill',
        # List methods
        'append', 'clear', 'copy', 'count', 'extend', 'index', 'insert', 'pop', 'remove',
        'reverse', 'sort',
        # Dict methods
        'clear', 'copy', 'fromkeys', 'get', 'items', 'keys', 'pop', 'popitem',
        'setdefault', 'update', 'values',
        # Set methods
        'add', 'clear', 'copy', 'difference', 'difference_update', 'discard',
        'intersection', 'intersection_update', 'isdisjoint', 'issubset', 'issuperset',
        'pop', 'remove', 'symmetric_difference', 'symmetric_difference_update', 'union', 'update',
        # File methods
        'read', 'readline', 'readlines', 'write', 'writelines', 'seek', 'tell', 'close',
        'flush', 'fileno', 'isatty', 'truncate',
        # Exception classes
        'BaseException', 'Exception', 'ArithmeticError', 'AssertionError',
        'AttributeError', 'BlockingIOError', 'BrokenPipeError', 'BufferError',
        'BytesWarning', 'ChildProcessError', 'ConnectionAbortedError',
        'ConnectionError', 'ConnectionRefusedError', 'ConnectionResetError',
        'DeprecationWarning', 'EOFError', 'EnvironmentError', 'FileExistsError',
        'FileNotFoundError', 'FloatingPointError', 'FutureWarning', 'GeneratorExit',
        'IOError', 'ImportError', 'ImportWarning', 'IndentationError', 'IndexError',
        'InterruptedError', 'IsADirectoryError', 'KeyError', 'KeyboardInterrupt',
        'LookupError', 'MemoryError', 'ModuleNotFoundError', 'NameError',
        'NotADirectoryError', 'NotImplemented', 'NotImplementedError', 'OSError',
        'OverflowError', 'PendingDeprecationWarning', 'PermissionError',
        'ProcessLookupError', 'RecursionError', 'ReferenceError', 'ResourceWarning',
        'RuntimeError', 'RuntimeWarning', 'StopAsyncIteration', 'StopIteration',
        'SyntaxError', 'SyntaxWarning', 'SystemError', 'SystemExit', 'TabError',
        'TimeoutError', 'TypeError', 'UnboundLocalError', 'UnicodeDecodeError',
        'UnicodeEncodeError', 'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning',
        'UserWarning', 'ValueError', 'Warning', 'ZeroDivisionError',
        # Magic methods
        '__init__', '__new__', '__del__', '__repr__', '__str__', '__bytes__',
        '__format__', '__lt__', '__le__', '__eq__', '__ne__', '__gt__', '__ge__',
        '__hash__', '__bool__', '__getattr__', '__getattribute__', '__setattr__',
        '__delattr__', '__dir__', '__get__', '__set__', '__delete__', '__set_name__',
        '__init_subclass__', '__class_getitem__', '__call__', '__len__', '__length_hint__',
        '__getitem__', '__setitem__', '__delitem__', '__missing__', '__iter__',
        '__reversed__', '__contains__', '__add__', '__sub__', '__mul__', '__matmul__',
        '__truediv__', '__floordiv__', '__mod__', '__divmod__', '__pow__', '__lshift__',
        '__rshift__', '__and__', '__xor__', '__or__', '__neg__', '__pos__', '__abs__',
        '__invert__', '__complex__', '__int__', '__float__', '__index__', '__round__',
        '__trunc__', '__floor__', '__ceil__', '__enter__', '__exit__', '__await__',
        '__aiter__', '__anext__', '__aenter__', '__aexit__',
        # Common stdlib functions (dataclasses, typing, functools, etc.)
        'field', 'dataclass', 'asdict', 'astuple', 'make_dataclass', 'fields',
        'Optional', 'List', 'Dict', 'Set', 'Tuple', 'Union', 'Any', 'Callable',
        'TypeVar', 'Generic', 'Protocol', 'Literal', 'Final', 'ClassVar',
        'partial', 'reduce', 'wraps', 'lru_cache', 'cache', 'cached_property',
        'Path', 'PurePath', 'PosixPath', 'WindowsPath',
        'datetime', 'date', 'time', 'timedelta', 'timezone',
        'dumps', 'loads', 'dump', 'load',  # json
        'match', 'search', 'findall', 'sub', 'compile',  # re
        'sleep', 'perf_counter', 'monotonic',  # time
        'environ', 'getcwd', 'chdir', 'listdir', 'makedirs', 'remove', 'rename',  # os
        'run', 'Popen', 'PIPE', 'STDOUT',  # subprocess
        'gather', 'create_task', 'wait', 'to_thread',  # asyncio
        'getLogger', 'debug', 'info', 'warning', 'error', 'critical',  # logging
    },

    Language.CSHARP: {
        # System
        'ToString', 'GetType', 'Equals', 'GetHashCode', 'ReferenceEquals', 'MemberwiseClone',
        # Console
        'Console', 'WriteLine', 'ReadLine', 'Write', 'Read', 'Clear', 'Beep',
        # Collections
        'Add', 'Remove', 'Contains', 'Clear', 'Count', 'Length', 'Capacity',
        'Insert', 'RemoveAt', 'IndexOf', 'LastIndexOf', 'CopyTo', 'ToArray',
        # LINQ
        'Where', 'Select', 'SelectMany', 'OrderBy', 'OrderByDescending', 'ThenBy',
        'ThenByDescending', 'GroupBy', 'Join', 'GroupJoin', 'Distinct', 'Union',
        'Intersect', 'Except', 'Concat', 'Zip', 'Reverse', 'SequenceEqual',
        'First', 'FirstOrDefault', 'Last', 'LastOrDefault', 'Single', 'SingleOrDefault',
        'ElementAt', 'ElementAtOrDefault', 'DefaultIfEmpty', 'Skip', 'SkipWhile',
        'Take', 'TakeWhile', 'Any', 'All', 'Count', 'LongCount', 'Sum', 'Min', 'Max',
        'Average', 'Aggregate', 'ToList', 'ToArray', 'ToDictionary', 'ToHashSet',
        'ToLookup', 'AsEnumerable', 'AsQueryable', 'Cast', 'OfType',
        # String
        'Format', 'Concat', 'Join', 'Split', 'Trim', 'TrimStart', 'TrimEnd',
        'PadLeft', 'PadRight', 'Replace', 'Remove', 'Insert', 'Substring',
        'ToLower', 'ToUpper', 'ToLowerInvariant', 'ToUpperInvariant',
        'StartsWith', 'EndsWith', 'Contains', 'IndexOf', 'LastIndexOf',
        'IsNullOrEmpty', 'IsNullOrWhiteSpace', 'Compare', 'CompareTo',
        'Equals', 'GetHashCode', 'ToCharArray', 'CopyTo',
        # Task/Async
        'Task', 'Run', 'Wait', 'WaitAll', 'WaitAny', 'WhenAll', 'WhenAny',
        'FromResult', 'FromException', 'FromCanceled', 'Delay', 'Yield',
        'ConfigureAwait', 'GetAwaiter', 'GetResult', 'ContinueWith',
        # DateTime
        'DateTime', 'Now', 'Today', 'UtcNow', 'Parse', 'TryParse', 'ParseExact',
        'AddDays', 'AddHours', 'AddMinutes', 'AddSeconds', 'AddMilliseconds',
        'AddMonths', 'AddYears', 'Subtract', 'DayOfWeek', 'DayOfYear',
        # TimeSpan
        'TimeSpan', 'FromDays', 'FromHours', 'FromMinutes', 'FromSeconds',
        'FromMilliseconds', 'FromTicks', 'TotalDays', 'TotalHours', 'TotalMinutes',
        'TotalSeconds', 'TotalMilliseconds',
        # Guid
        'Guid', 'NewGuid', 'Empty', 'Parse', 'TryParse',
        # Math
        'Math', 'Abs', 'Ceiling', 'Floor', 'Round', 'Truncate', 'Max', 'Min',
        'Pow', 'Sqrt', 'Log', 'Log10', 'Log2', 'Exp', 'Sin', 'Cos', 'Tan',
        'Asin', 'Acos', 'Atan', 'Atan2', 'Sign', 'Clamp',
        # File/IO
        'File', 'Exists', 'ReadAllText', 'WriteAllText', 'ReadAllLines',
        'WriteAllLines', 'ReadAllBytes', 'WriteAllBytes', 'Create', 'Delete',
        'Copy', 'Move', 'AppendAllText', 'AppendAllLines',
        'Directory', 'CreateDirectory', 'GetFiles', 'GetDirectories',
        'Path', 'Combine', 'GetFileName', 'GetDirectoryName', 'GetExtension',
        'GetFileNameWithoutExtension', 'GetFullPath', 'GetTempPath', 'GetTempFileName',
        # Stream
        'Stream', 'Read', 'Write', 'Seek', 'Flush', 'Close', 'Dispose',
        'CopyTo', 'CopyToAsync', 'ReadAsync', 'WriteAsync', 'FlushAsync',
        # JSON (System.Text.Json / Newtonsoft)
        'JsonSerializer', 'Serialize', 'Deserialize', 'SerializeAsync', 'DeserializeAsync',
        'JsonConvert', 'SerializeObject', 'DeserializeObject',
        # DI
        'GetService', 'GetRequiredService', 'CreateScope',
        'AddScoped', 'AddTransient', 'AddSingleton', 'AddDbContext',
        # ASP.NET
        'UseRouting', 'UseEndpoints', 'UseAuthentication', 'UseAuthorization',
        'MapControllers', 'MapGet', 'MapPost', 'MapPut', 'MapDelete',
        'AddControllers', 'AddMvc', 'AddRazorPages',
        # EF Core
        'DbContext', 'DbSet', 'SaveChanges', 'SaveChangesAsync',
        'Include', 'ThenInclude', 'AsNoTracking', 'AsQueryable',
        'Find', 'FindAsync', 'Add', 'AddAsync', 'Update', 'Remove', 'Attach',
        'Entry', 'ChangeTracker', 'Database', 'Migrate', 'EnsureCreated',
    },

    Language.GO: {
        # fmt
        'fmt', 'Print', 'Println', 'Printf', 'Sprint', 'Sprintf', 'Sprintln',
        'Fprint', 'Fprintln', 'Fprintf', 'Scan', 'Scanln', 'Scanf',
        'Errorf', 'Sscan', 'Sscanln', 'Sscanf',
        # Builtins
        'append', 'cap', 'close', 'complex', 'copy', 'delete', 'imag', 'len',
        'make', 'new', 'panic', 'print', 'println', 'real', 'recover',
        # errors
        'errors', 'New', 'Is', 'As', 'Unwrap',
        # context
        'context', 'Background', 'TODO', 'WithCancel', 'WithDeadline',
        'WithTimeout', 'WithValue', 'Canceled', 'DeadlineExceeded',
        # http
        'http', 'Get', 'Post', 'Head', 'NewRequest', 'ListenAndServe',
        'Handle', 'HandleFunc', 'Serve', 'FileServer', 'NotFound', 'Redirect',
        # json
        'json', 'Marshal', 'Unmarshal', 'MarshalIndent', 'NewEncoder', 'NewDecoder',
        'Encode', 'Decode', 'Valid',
        # io
        'io', 'Reader', 'Writer', 'ReadAll', 'Copy', 'CopyN', 'CopyBuffer',
        'ReadFull', 'WriteString', 'Pipe', 'TeeReader', 'LimitReader',
        'NopCloser', 'EOF', 'ErrUnexpectedEOF', 'ErrClosedPipe',
        # os
        'os', 'Open', 'Create', 'OpenFile', 'Remove', 'RemoveAll', 'Rename',
        'Mkdir', 'MkdirAll', 'ReadFile', 'WriteFile', 'Stat', 'Lstat',
        'Getenv', 'Setenv', 'Unsetenv', 'Environ', 'Exit', 'Getwd', 'Chdir',
        'Args', 'Stdin', 'Stdout', 'Stderr',
        # strings
        'strings', 'Contains', 'ContainsAny', 'ContainsRune', 'Count',
        'EqualFold', 'Fields', 'HasPrefix', 'HasSuffix', 'Index', 'IndexAny',
        'IndexByte', 'IndexFunc', 'IndexRune', 'Join', 'LastIndex',
        'LastIndexAny', 'LastIndexByte', 'LastIndexFunc', 'Map', 'Repeat',
        'Replace', 'ReplaceAll', 'Split', 'SplitAfter', 'SplitAfterN', 'SplitN',
        'Title', 'ToLower', 'ToTitle', 'ToUpper', 'Trim', 'TrimFunc',
        'TrimLeft', 'TrimLeftFunc', 'TrimPrefix', 'TrimRight', 'TrimRightFunc',
        'TrimSpace', 'TrimSuffix',
        # strconv
        'strconv', 'Atoi', 'Itoa', 'ParseBool', 'ParseFloat', 'ParseInt',
        'ParseUint', 'FormatBool', 'FormatFloat', 'FormatInt', 'FormatUint',
        'Quote', 'QuoteRune', 'Unquote', 'UnquoteChar',
        # time
        'time', 'Now', 'Since', 'Until', 'Sleep', 'After', 'AfterFunc', 'Tick',
        'NewTicker', 'NewTimer', 'Parse', 'ParseDuration', 'ParseInLocation',
        'Date', 'Unix', 'UnixMilli', 'UnixMicro', 'UnixNano',
        'Second', 'Minute', 'Hour', 'Millisecond', 'Microsecond', 'Nanosecond',
        # sync
        'sync', 'Mutex', 'RWMutex', 'WaitGroup', 'Once', 'Cond', 'Pool', 'Map',
        'Lock', 'Unlock', 'RLock', 'RUnlock', 'Add', 'Done', 'Wait', 'Do',
        # log
        'log', 'Print', 'Println', 'Printf', 'Fatal', 'Fatalln', 'Fatalf',
        'Panic', 'Panicln', 'Panicf', 'SetOutput', 'SetFlags', 'SetPrefix',
        # testing
        'testing', 'T', 'B', 'M', 'Error', 'Errorf', 'Fail', 'FailNow',
        'Fatal', 'Fatalf', 'Log', 'Logf', 'Run', 'Skip', 'Skipf', 'SkipNow',
        # reflect
        'reflect', 'TypeOf', 'ValueOf', 'DeepEqual', 'Copy', 'Append',
        'MakeSlice', 'MakeMap', 'MakeChan', 'MakeFunc', 'Zero', 'New',
        # sort
        'sort', 'Ints', 'IntsAreSorted', 'Float64s', 'Float64sAreSorted',
        'Strings', 'StringsAreSorted', 'Slice', 'SliceStable', 'SliceIsSorted',
        'Search', 'SearchInts', 'SearchFloat64s', 'SearchStrings', 'Sort', 'Reverse',
    },

    Language.RUST: {
        # std macros
        'println', 'print', 'eprintln', 'eprint', 'format', 'write', 'writeln',
        'panic', 'assert', 'assert_eq', 'assert_ne', 'debug_assert', 'debug_assert_eq',
        'debug_assert_ne', 'todo', 'unimplemented', 'unreachable', 'cfg', 'env',
        'concat', 'stringify', 'include', 'include_str', 'include_bytes',
        'file', 'line', 'column', 'module_path', 'option_env',
        'vec', 'format_args', 'matches', 'try',
        # Common traits
        'clone', 'Clone', 'copy', 'Copy', 'default', 'Default', 'eq', 'Eq',
        'ord', 'Ord', 'hash', 'Hash', 'debug', 'Debug', 'display', 'Display',
        'from', 'From', 'into', 'Into', 'as_ref', 'AsRef', 'as_mut', 'AsMut',
        'deref', 'Deref', 'deref_mut', 'DerefMut', 'drop', 'Drop',
        'iterator', 'Iterator', 'into_iter', 'IntoIterator', 'iter', 'iter_mut',
        'partial_eq', 'PartialEq', 'partial_ord', 'PartialOrd',
        # Option
        'Option', 'Some', 'None', 'is_some', 'is_none', 'unwrap', 'unwrap_or',
        'unwrap_or_else', 'unwrap_or_default', 'expect', 'ok_or', 'ok_or_else',
        'map', 'map_or', 'map_or_else', 'and', 'and_then', 'or', 'or_else',
        'filter', 'take', 'replace', 'cloned', 'copied', 'flatten', 'transpose',
        # Result
        'Result', 'Ok', 'Err', 'is_ok', 'is_err', 'ok', 'err', 'unwrap', 'unwrap_err',
        'unwrap_or', 'unwrap_or_else', 'unwrap_or_default', 'expect', 'expect_err',
        'map', 'map_err', 'map_or', 'map_or_else', 'and', 'and_then', 'or', 'or_else',
        # String
        'String', 'new', 'from', 'with_capacity', 'push', 'push_str', 'pop',
        'truncate', 'clear', 'len', 'is_empty', 'capacity', 'reserve',
        'shrink_to_fit', 'as_str', 'as_bytes', 'as_mut_str', 'insert', 'insert_str',
        'remove', 'retain', 'split_off', 'drain', 'replace_range',
        # str
        'len', 'is_empty', 'as_bytes', 'as_ptr', 'get', 'get_unchecked',
        'chars', 'bytes', 'char_indices', 'split', 'rsplit', 'split_terminator',
        'rsplit_terminator', 'splitn', 'rsplitn', 'lines', 'contains', 'starts_with',
        'ends_with', 'find', 'rfind', 'matches', 'rmatches', 'match_indices',
        'rmatch_indices', 'trim', 'trim_start', 'trim_end', 'trim_matches',
        'strip_prefix', 'strip_suffix', 'parse', 'replace', 'replacen',
        'to_lowercase', 'to_uppercase', 'repeat', 'to_string', 'to_owned',
        # Vec
        'Vec', 'new', 'with_capacity', 'from', 'push', 'pop', 'insert', 'remove',
        'swap_remove', 'retain', 'truncate', 'clear', 'len', 'is_empty',
        'capacity', 'reserve', 'shrink_to_fit', 'into_boxed_slice', 'first',
        'last', 'get', 'get_mut', 'iter', 'iter_mut', 'split', 'splitn',
        'chunks', 'windows', 'sort', 'sort_by', 'sort_by_key', 'reverse',
        'binary_search', 'binary_search_by', 'binary_search_by_key',
        'contains', 'starts_with', 'ends_with', 'extend', 'append', 'drain',
        'split_off', 'resize', 'dedup', 'dedup_by', 'dedup_by_key',
        # HashMap
        'HashMap', 'new', 'with_capacity', 'insert', 'remove', 'get', 'get_mut',
        'contains_key', 'len', 'is_empty', 'clear', 'keys', 'values', 'values_mut',
        'iter', 'iter_mut', 'drain', 'entry', 'or_insert', 'or_insert_with',
        # HashSet
        'HashSet', 'new', 'with_capacity', 'insert', 'remove', 'contains', 'get',
        'len', 'is_empty', 'clear', 'iter', 'drain', 'difference', 'symmetric_difference',
        'intersection', 'union', 'is_disjoint', 'is_subset', 'is_superset',
        # Box/Rc/Arc
        'Box', 'Rc', 'Arc', 'new', 'clone', 'downgrade', 'upgrade', 'strong_count',
        'weak_count', 'ptr_eq', 'as_ref', 'into_inner',
        # Cell/RefCell/Mutex
        'Cell', 'RefCell', 'Mutex', 'RwLock', 'new', 'get', 'set', 'take',
        'replace', 'borrow', 'borrow_mut', 'try_borrow', 'try_borrow_mut',
        'lock', 'try_lock', 'read', 'write', 'try_read', 'try_write',
        # std::fs
        'read', 'read_to_string', 'write', 'create', 'open', 'remove_file',
        'remove_dir', 'remove_dir_all', 'create_dir', 'create_dir_all',
        'read_dir', 'copy', 'rename', 'metadata', 'canonicalize',
        # std::io
        'Read', 'Write', 'BufRead', 'Seek', 'BufReader', 'BufWriter',
        'stdin', 'stdout', 'stderr', 'read_line', 'read_to_end', 'read_to_string',
        'write_all', 'flush', 'seek',
        # std::path
        'Path', 'PathBuf', 'new', 'join', 'push', 'pop', 'set_file_name',
        'set_extension', 'file_name', 'file_stem', 'extension', 'parent',
        'ancestors', 'components', 'is_absolute', 'is_relative', 'exists',
        'is_file', 'is_dir', 'display', 'to_str', 'to_string_lossy',
        # std::env
        'args', 'args_os', 'var', 'var_os', 'vars', 'vars_os', 'set_var',
        'remove_var', 'current_dir', 'set_current_dir', 'temp_dir', 'home_dir',
        # std::thread
        'spawn', 'sleep', 'yield_now', 'current', 'park', 'park_timeout',
        'JoinHandle', 'join', 'thread', 'is_finished',
        # std::time
        'Instant', 'Duration', 'SystemTime', 'now', 'elapsed', 'duration_since',
        'from_secs', 'from_millis', 'from_micros', 'from_nanos',
        'as_secs', 'as_millis', 'as_micros', 'as_nanos', 'subsec_nanos',
    },
}

# TypeScript inherits JavaScript builtins
BUILTINS[Language.TYPESCRIPT] = BUILTINS[Language.JAVASCRIPT] | {
    # TypeScript-specific utility types (used as functions sometimes)
    'Partial', 'Required', 'Readonly', 'Pick', 'Omit', 'Record',
    'Exclude', 'Extract', 'NonNullable', 'ReturnType', 'Parameters',
    'InstanceType', 'ThisParameterType', 'OmitThisParameter', 'ThisType',
    'Uppercase', 'Lowercase', 'Capitalize', 'Uncapitalize',
    'Awaited', 'ConstructorParameters', 'NoInfer',
}


# =============================================================================
# LAZY-LOADED PHP BUILTINS FROM GENERATED JSON
# =============================================================================

class PHPBuiltinsLoader:
    """Lazy-loads PHP built-in symbols from generated JSON file.

    The JSON is generated by generate_php_builtins.py from JetBrains phpstorm-stubs.
    Contains 5000+ functions, 1000+ classes, 10000+ methods.
    """

    _loaded: bool = False
    _functions: Set[str] = set()
    _classes: Set[str] = set()
    _methods: Set[str] = set()

    @classmethod
    def load(cls) -> None:
        """Load PHP builtins from JSON file (lazy, one-time)."""
        if cls._loaded:
            return

        json_path = Path(__file__).parent / 'data' / 'php_builtins.json'

        if not json_path.exists():
            logger.warning(
                f"PHP builtins JSON not found at {json_path}. "
                "Run 'python generate_php_builtins.py' to generate it."
            )
            cls._loaded = True
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            symbols = data.get('symbols', {})
            cls._functions = set(symbols.get('functions', []))
            cls._classes = set(symbols.get('classes', []))
            cls._methods = set(symbols.get('methods', []))

            # Merge into global BUILTINS
            BUILTINS[Language.PHP].update(cls._functions)
            BUILTINS[Language.PHP].update(cls._classes)
            BUILTINS[Language.PHP].update(cls._methods)

            stats = data.get('stats', {})
            logger.debug(
                f"Loaded PHP builtins: {stats.get('functions', 0)} functions, "
                f"{stats.get('classes', 0)} classes, {stats.get('methods', 0)} methods"
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PHP builtins JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to load PHP builtins: {e}")
        finally:
            cls._loaded = True

    @classmethod
    def get_functions(cls) -> Set[str]:
        """Get all PHP built-in functions."""
        cls.load()
        return cls._functions

    @classmethod
    def get_classes(cls) -> Set[str]:
        """Get all PHP built-in classes."""
        cls.load()
        return cls._classes

    @classmethod
    def get_methods(cls) -> Set[str]:
        """Get all PHP built-in methods."""
        cls.load()
        return cls._methods

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if builtins have been loaded."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset loader state (for testing)."""
        cls._loaded = False
        cls._functions = set()
        cls._classes = set()
        cls._methods = set()


# =============================================================================
# COMMON EXTERNAL NAMES - Names likely from external libraries (reduce confidence)
# =============================================================================

COMMON_EXTERNAL_NAMES: Set[str] = {
    # HTTP/API
    'request', 'response', 'get', 'post', 'put', 'delete', 'patch',
    'fetch', 'send', 'call', 'invoke', 'dispatch',

    # Repository/ORM Pattern (WICHTIG für Laravel, Doctrine, EF, etc.)
    'find', 'findById', 'findOne', 'findAll', 'findBy', 'findWhere',
    'findOrFail', 'findFirst', 'findLast', 'firstOrCreate', 'firstOrNew',
    'updateOrCreate', 'firstWhere', 'getById', 'getAll', 'getOne',

    # Query Builder
    'where', 'select', 'from', 'join', 'orderBy', 'groupBy', 'having',
    'limit', 'offset', 'take', 'skip', 'paginate', 'count', 'sum', 'avg',

    # Collection/Array Operations
    'map', 'filter', 'reduce', 'each', 'every', 'some', 'sort', 'reverse',
    'first', 'last', 'pluck', 'chunk', 'flatten', 'unique', 'merge',

    # CRUD
    'save', 'update', 'create', 'destroy', 'delete', 'remove', 'insert',
    'persist', 'flush', 'refresh', 'detach', 'attach', 'sync',

    # Service/Handler Pattern
    'execute', 'handle', 'process', 'run', 'perform', 'apply',
    'validate', 'transform', 'parse', 'serialize', 'deserialize',
    'render', 'build', 'make', 'resolve', 'bind',

    # Event/Observer
    'emit', 'on', 'off', 'trigger', 'listen', 'subscribe', 'publish',
    'notify', 'observe', 'dispatch', 'broadcast',

    # Logging/Debug
    'log', 'info', 'warn', 'error', 'debug', 'trace', 'dump',

    # Lifecycle
    'init', 'start', 'stop', 'boot', 'register', 'destroy', 'dispose',
    'mount', 'unmount', 'setup', 'teardown', 'configure',
}


# =============================================================================
# DYNAMIC PATTERNS - Patterns indicating dynamic/reflection code
# =============================================================================

DYNAMIC_PATTERNS: Dict[Language, List[str]] = {
    Language.PHP: [
        r'\$\w+\s*\(',              # $variable()
        r'\$this\s*->\s*\$\w+',     # $this->$variable
        r'call_user_func',          # call_user_func()
        r'call_user_func_array',    # call_user_func_array()
        r'__call\s*\(',             # Magic __call
        r'ReflectionMethod',        # Reflection
        r'ReflectionClass',
        r'method_exists',
        r'property_exists',
    ],

    Language.JAVASCRIPT: [
        r'\[\s*\w+\s*\]\s*\(',      # obj[variable]()
        r'eval\s*\(',               # eval()
        r'Function\s*\(',           # new Function()
        r'apply\s*\(',              # .apply()
        r'call\s*\(',               # .call()
        r'Reflect\.',               # Reflect API
        r'Proxy\s*\(',              # Proxy
    ],

    Language.TYPESCRIPT: [
        r'\[\s*\w+\s*\]\s*\(',
        r'eval\s*\(',
        r'Function\s*\(',
        r'apply\s*\(',
        r'call\s*\(',
        r'Reflect\.',
        r'Proxy\s*\(',
        r'as\s+any',                # Type assertion to any
        r'as\s+unknown',            # Type assertion to unknown
    ],

    Language.PYTHON: [
        r'getattr\s*\(',            # getattr()
        r'setattr\s*\(',            # setattr()
        r'hasattr\s*\(',            # hasattr()
        r'__getattr__',             # Magic method
        r'__getattribute__',
        r'exec\s*\(',               # exec()
        r'eval\s*\(',               # eval()
        r'globals\s*\(',            # globals()
        r'locals\s*\(',             # locals()
    ],

    Language.CSHARP: [
        r'GetMethod\s*\(',          # Reflection
        r'GetProperty\s*\(',
        r'Invoke\s*\(',
        r'typeof\s*\(',
        r'GetType\s*\(',
        r'Activator\.CreateInstance',
        r'dynamic\s+',              # dynamic keyword
        r'ExpandoObject',
    ],

    Language.GO: [
        r'reflect\.',               # reflect package
        r'interface\s*\{\s*\}',     # empty interface
    ],

    Language.RUST: [
        r'Any',                     # std::any::Any
        r'downcast',
        r'type_id',
    ],
}


# =============================================================================
# COMPILED PATTERNS - Pre-compiled regex for performance
# =============================================================================

class CompiledPatterns:
    """Pre-compiled regex patterns for performance."""

    _call_patterns: Dict[Language, List[Pattern]] = {}
    _definition_patterns: Dict[Language, List[Pattern]] = {}
    _property_patterns: Dict[Language, List[Pattern]] = {}
    _dynamic_patterns: Dict[Language, List[Pattern]] = {}
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Compile all patterns."""
        if cls._initialized:
            return

        for lang in Language:
            cls._call_patterns[lang] = [
                re.compile(p, re.MULTILINE) for p in CALL_PATTERNS.get(lang, [])
            ]
            cls._definition_patterns[lang] = [
                re.compile(p, re.MULTILINE) for p in DEFINITION_PATTERNS.get(lang, [])
            ]
            cls._property_patterns[lang] = [
                re.compile(p, re.MULTILINE) for p in PROPERTY_PATTERNS.get(lang, [])
            ]
            cls._dynamic_patterns[lang] = [
                re.compile(p, re.MULTILINE) for p in DYNAMIC_PATTERNS.get(lang, [])
            ]

        cls._initialized = True

    @classmethod
    def get_call_patterns(cls, lang: Language) -> List[Pattern]:
        cls.initialize()
        return cls._call_patterns.get(lang, [])

    @classmethod
    def get_definition_patterns(cls, lang: Language) -> List[Pattern]:
        cls.initialize()
        return cls._definition_patterns.get(lang, [])

    @classmethod
    def get_property_patterns(cls, lang: Language) -> List[Pattern]:
        cls.initialize()
        return cls._property_patterns.get(lang, [])

    @classmethod
    def get_dynamic_patterns(cls, lang: Language) -> List[Pattern]:
        cls.initialize()
        return cls._dynamic_patterns.get(lang, [])


def detect_language(file_path: str) -> Optional[Language]:
    """Detect programming language from file extension."""
    import os
    _, ext = os.path.splitext(file_path)
    return EXTENSION_MAP.get(ext.lower())


def is_builtin(name: str, lang: Language) -> bool:
    """Check if a symbol name is a builtin for the given language.

    For PHP, this automatically loads 5000+ builtins from generated JSON.
    PHP is case-insensitive, so we compare lowercase.
    """
    # Lazy-load PHP builtins on first PHP check
    if lang == Language.PHP and not PHPBuiltinsLoader.is_loaded():
        PHPBuiltinsLoader.load()

    # PHP is case-insensitive - compare lowercase
    if lang == Language.PHP:
        return name.lower() in BUILTINS.get(lang, set())

    return name in BUILTINS.get(lang, set())


def is_common_external(name: str) -> bool:
    """Check if a symbol name is commonly from external libraries."""
    return name in COMMON_EXTERNAL_NAMES or name.lower() in COMMON_EXTERNAL_NAMES


def has_dynamic_patterns(content: str, lang: Language) -> bool:
    """Check if content contains dynamic/reflection patterns."""
    patterns = CompiledPatterns.get_dynamic_patterns(lang)
    for pattern in patterns:
        if pattern.search(content):
            return True
    return False
