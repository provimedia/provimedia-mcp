"""
CHAINGUARD MCP Server - XML Response Module (v6.0)

Provides structured XML responses for better Claude comprehension.
Based on research showing +56% accuracy improvement with XML vs JSON for Claude.

Key benefits:
- Semantic + syntactic boundaries (XML tags are both)
- Better context retention in long sessions
- Reduced instruction drift
- Easier post-processing

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import xml.etree.ElementTree as ET
from xml.dom import minidom

VERSION = "6.0"


class ResponseStatus(str, Enum):
    """Response status types for XML responses."""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    BLOCKED = "blocked"

    def __str__(self) -> str:
        return self.value


@dataclass
class XMLResponse:
    """
    Structured XML response builder for Chainguard MCP.

    Usage:
        response = XMLResponse(
            tool="set_scope",
            status=ResponseStatus.SUCCESS,
            message="Scope defined",
            data={"scope": {"description": "Feature X", "mode": "programming"}}
        )
        xml_string = response.to_xml()
    """
    tool: str
    status: ResponseStatus
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    pretty: bool = False  # Enable pretty-printing (costs more tokens)

    def to_xml(self) -> str:
        """Generate XML string from response data."""
        root = ET.Element("chainguard", tool=self.tool, version=VERSION)

        # Status element (required)
        status_el = ET.SubElement(root, "status")
        status_el.text = str(self.status)

        # Message element (optional)
        if self.message:
            msg_el = ET.SubElement(root, "message")
            msg_el.text = self.message

        # Data element (optional)
        if self.data:
            data_el = ET.SubElement(root, "data")
            self._dict_to_xml(data_el, self.data)

        # Context element (optional)
        if self.context:
            ctx_el = ET.SubElement(root, "context")
            if isinstance(self.context, dict) and "mode" in self.context:
                ctx_el.set("mode", str(self.context.get("mode", "")))
                # Remove mode from dict to avoid duplication
                context_copy = {k: v for k, v in self.context.items() if k != "mode"}
                self._dict_to_xml(ctx_el, context_copy)
            else:
                self._dict_to_xml(ctx_el, self.context)

        # Generate XML string
        xml_str = ET.tostring(root, encoding="unicode")

        if self.pretty:
            # Pretty print with indentation (costs more tokens)
            return minidom.parseString(xml_str).toprettyxml(indent="  ")

        return xml_str

    def _dict_to_xml(self, parent: ET.Element, data: Dict[str, Any]) -> None:
        """
        Recursively convert dictionary to XML elements.

        Handles:
        - Nested dicts -> nested elements
        - Lists -> repeated elements with same tag
        - Primitives -> text content
        - None -> empty element
        - Attributes via special _attrs key
        """
        for key, value in data.items():
            # Skip internal keys
            if key.startswith("_"):
                continue

            # Sanitize key for XML (no spaces, special chars)
            safe_key = self._sanitize_tag_name(key)

            if isinstance(value, dict):
                child = ET.SubElement(parent, safe_key)
                # Handle attributes if present
                if "_attrs" in value:
                    for attr_key, attr_val in value["_attrs"].items():
                        child.set(attr_key, str(attr_val))
                self._dict_to_xml(child, value)

            elif isinstance(value, (list, tuple)):
                for item in value:
                    child = ET.SubElement(parent, safe_key)
                    if isinstance(item, dict):
                        self._dict_to_xml(child, item)
                    else:
                        child.text = self._to_text(item)

            else:
                child = ET.SubElement(parent, safe_key)
                child.text = self._to_text(value)

    def _sanitize_tag_name(self, name: str) -> str:
        """
        Sanitize string to be valid XML tag name.

        - Replace spaces with underscores
        - Remove invalid characters
        - Ensure starts with letter or underscore
        """
        # Replace common separators
        name = name.replace(" ", "_").replace("-", "_").replace(".", "_")

        # Remove invalid characters (keep alphanumeric and underscore)
        name = "".join(c for c in name if c.isalnum() or c == "_")

        # Ensure starts with letter or underscore
        if name and not (name[0].isalpha() or name[0] == "_"):
            name = "_" + name

        return name or "item"

    def _to_text(self, value: Any) -> str:
        """Convert value to XML text content."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)


# =============================================================================
# Convenience Functions
# =============================================================================

def xml_response(
    tool: str,
    status: ResponseStatus,
    message: str = "",
    data: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    pretty: bool = False
) -> str:
    """
    Create an XML response string.

    Args:
        tool: Tool name (e.g., "set_scope", "track")
        status: Response status (success, error, warning, info, blocked)
        message: Human-readable message
        data: Tool-specific response data
        context: Optional context injection (rules, features)
        pretty: Enable pretty-printing (default: False for token efficiency)

    Returns:
        XML string

    Example:
        xml = xml_response(
            tool="set_scope",
            status=ResponseStatus.SUCCESS,
            message="Scope defined",
            data={"scope": {"description": "Feature X"}}
        )
    """
    return XMLResponse(
        tool=tool,
        status=status,
        message=message,
        data=data,
        context=context,
        pretty=pretty
    ).to_xml()


def xml_success(
    tool: str,
    message: str = "",
    data: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """Create a success XML response."""
    return xml_response(tool, ResponseStatus.SUCCESS, message, data, context)


def xml_error(
    tool: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Create an error XML response."""
    return xml_response(tool, ResponseStatus.ERROR, message, data)


def xml_warning(
    tool: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Create a warning XML response."""
    return xml_response(tool, ResponseStatus.WARNING, message, data)


def xml_info(
    tool: str,
    message: str = "",
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Create an info XML response."""
    return xml_response(tool, ResponseStatus.INFO, message, data)


def xml_blocked(
    tool: str,
    message: str,
    blocker_type: str,
    blocker_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a blocked XML response.

    Args:
        tool: Tool name
        message: Block reason
        blocker_type: Type of blocker (e.g., "scope_required", "db_check_required")
        blocker_data: Additional blocker information

    Example:
        xml = xml_blocked(
            tool="track",
            message="No scope set",
            blocker_type="scope_required",
            blocker_data={"next_action": "Call chainguard_set_scope() first"}
        )
    """
    data = {
        "blocker": {
            "type": blocker_type,
            **(blocker_data or {})
        }
    }
    return xml_response(tool, ResponseStatus.BLOCKED, message, data)


# =============================================================================
# Context Builders
# =============================================================================

def build_context(
    mode: str,
    rules: Optional[List[Dict[str, Any]]] = None,
    features: Optional[Dict[str, Any]] = None,
    hints: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Build a context dict for XML response.

    Args:
        mode: Task mode (programming, content, devops, research, generic)
        rules: List of rules with priority, action, when
        features: Feature flags dict
        hints: Optional hints/tips

    Returns:
        Context dict suitable for XMLResponse

    Example:
        context = build_context(
            mode="programming",
            rules=[
                {"priority": 1, "action": "chainguard_track()", "when": "after each edit"}
            ],
            features={"syntax_validation": True}
        )
    """
    context: Dict[str, Any] = {"mode": mode}

    if rules:
        context["rules"] = {"rule": rules}

    if features:
        context["features"] = features

    if hints:
        context["hints"] = {"hint": hints}

    return context


# =============================================================================
# Validation
# =============================================================================

def is_valid_xml(xml_string: str) -> bool:
    """Check if string is valid XML."""
    try:
        ET.fromstring(xml_string)
        return True
    except ET.ParseError:
        return False


def parse_xml_response(xml_string: str) -> Optional[Dict[str, Any]]:
    """
    Parse XML response back to dict (for testing/debugging).

    Returns None if parsing fails.
    """
    try:
        root = ET.fromstring(xml_string)
        return _xml_to_dict(root)
    except ET.ParseError:
        return None


def _xml_to_dict(element: ET.Element) -> Dict[str, Any]:
    """Convert XML element to dict (recursive)."""
    result: Dict[str, Any] = {}

    # Add attributes
    if element.attrib:
        result["_attrs"] = dict(element.attrib)

    # Add text content
    if element.text and element.text.strip():
        if len(element) == 0:  # No children
            return element.text.strip()
        result["_text"] = element.text.strip()

    # Add children
    for child in element:
        child_data = _xml_to_dict(child)

        if child.tag in result:
            # Convert to list if multiple same-tag children
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_data)
        else:
            result[child.tag] = child_data

    return result
