"""
Unit tests for xml_response.py module.

Tests XML response generation, validation, and parsing.
"""

import pytest
from chainguard.xml_response import (
    XMLResponse,
    ResponseStatus,
    xml_response,
    xml_success,
    xml_error,
    xml_warning,
    xml_info,
    xml_blocked,
    build_context,
    is_valid_xml,
    parse_xml_response,
    VERSION
)


# =============================================================================
# XMLResponse Class Tests
# =============================================================================

class TestXMLResponse:
    """Tests for XMLResponse dataclass."""

    def test_basic_response(self):
        """Test basic XML response generation."""
        response = XMLResponse(
            tool="test_tool",
            status=ResponseStatus.SUCCESS,
            message="Test message"
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert 'tool="test_tool"' in xml
        assert f'version="{VERSION}"' in xml
        assert "<status>success</status>" in xml
        assert "<message>Test message</message>" in xml

    def test_response_with_data(self):
        """Test XML response with nested data."""
        response = XMLResponse(
            tool="set_scope",
            status=ResponseStatus.SUCCESS,
            message="Scope defined",
            data={
                "scope": {
                    "description": "Feature X",
                    "mode": "programming",
                    "modules": "src/*.ts"
                }
            }
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "<data>" in xml
        assert "<scope>" in xml
        assert "<description>Feature X</description>" in xml
        assert "<mode>programming</mode>" in xml

    def test_response_with_list_data(self):
        """Test XML response with list data."""
        response = XMLResponse(
            tool="check_criteria",
            status=ResponseStatus.INFO,
            data={
                "criteria": [
                    {"name": "Test 1", "fulfilled": True},
                    {"name": "Test 2", "fulfilled": False}
                ]
            }
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert xml.count("<criteria>") == 2
        assert "<name>Test 1</name>" in xml
        assert "<fulfilled>true</fulfilled>" in xml
        assert "<fulfilled>false</fulfilled>" in xml

    def test_response_with_context(self):
        """Test XML response with context injection."""
        response = XMLResponse(
            tool="set_scope",
            status=ResponseStatus.SUCCESS,
            context={
                "mode": "programming",
                "rules": [
                    {"priority": "1", "action": "track()"}
                ]
            }
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "<context" in xml
        assert 'mode="programming"' in xml
        assert "<rules>" in xml

    def test_pretty_print(self):
        """Test pretty-printed XML output."""
        response = XMLResponse(
            tool="test",
            status=ResponseStatus.SUCCESS,
            pretty=True
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "\n" in xml  # Pretty print includes newlines

    def test_special_characters_escaped(self):
        """Test that special characters are properly escaped."""
        response = XMLResponse(
            tool="test",
            status=ResponseStatus.SUCCESS,
            message="Test <script> & \"quotes\""
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "&lt;script&gt;" in xml
        assert "&amp;" in xml

    def test_none_values(self):
        """Test handling of None values."""
        response = XMLResponse(
            tool="test",
            status=ResponseStatus.INFO,
            data={"value": None, "other": "text"}
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "<value></value>" in xml or "<value />" in xml

    def test_sanitize_tag_names(self):
        """Test that invalid tag names are sanitized."""
        response = XMLResponse(
            tool="test",
            status=ResponseStatus.SUCCESS,
            data={
                "with space": "value1",
                "with-dash": "value2",
                "123numeric": "value3"
            }
        )
        xml = response.to_xml()

        assert is_valid_xml(xml)
        assert "<with_space>" in xml
        assert "<with_dash>" in xml
        assert "<_123numeric>" in xml


# =============================================================================
# ResponseStatus Tests
# =============================================================================

class TestResponseStatus:
    """Tests for ResponseStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        assert ResponseStatus.SUCCESS.value == "success"
        assert ResponseStatus.ERROR.value == "error"
        assert ResponseStatus.WARNING.value == "warning"
        assert ResponseStatus.INFO.value == "info"
        assert ResponseStatus.BLOCKED.value == "blocked"

    def test_status_string_conversion(self):
        """Test status converts to string correctly."""
        assert str(ResponseStatus.SUCCESS) == "success"
        assert str(ResponseStatus.BLOCKED) == "blocked"


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_xml_success(self):
        """Test xml_success function."""
        xml = xml_success(
            tool="track",
            message="File tracked",
            data={"file": "test.py"}
        )

        assert is_valid_xml(xml)
        assert "<status>success</status>" in xml
        assert "<file>test.py</file>" in xml

    def test_xml_error(self):
        """Test xml_error function."""
        xml = xml_error(
            tool="track",
            message="Syntax error",
            data={"error": {"type": "php", "line": 42}}
        )

        assert is_valid_xml(xml)
        assert "<status>error</status>" in xml
        assert "<message>Syntax error</message>" in xml

    def test_xml_warning(self):
        """Test xml_warning function."""
        xml = xml_warning(
            tool="validate",
            message="Open criteria",
            data={"count": 3}
        )

        assert is_valid_xml(xml)
        assert "<status>warning</status>" in xml

    def test_xml_info(self):
        """Test xml_info function."""
        xml = xml_info(
            tool="status",
            data={"phase": "implementation", "files": 5}
        )

        assert is_valid_xml(xml)
        assert "<status>info</status>" in xml
        assert "<phase>implementation</phase>" in xml

    def test_xml_blocked(self):
        """Test xml_blocked function."""
        xml = xml_blocked(
            tool="track",
            message="No scope set",
            blocker_type="scope_required",
            blocker_data={"next_action": "Call set_scope()"}
        )

        assert is_valid_xml(xml)
        assert "<status>blocked</status>" in xml
        assert "<blocker>" in xml
        assert "<type>scope_required</type>" in xml
        assert "<next_action>" in xml

    def test_xml_response_full(self):
        """Test xml_response with all parameters."""
        xml = xml_response(
            tool="set_scope",
            status=ResponseStatus.SUCCESS,
            message="Scope set",
            data={"scope": {"mode": "programming"}},
            context={"mode": "programming", "rules": []},
            pretty=False
        )

        assert is_valid_xml(xml)
        assert "<data>" in xml
        assert "<context" in xml


# =============================================================================
# Context Builder Tests
# =============================================================================

class TestBuildContext:
    """Tests for build_context function."""

    def test_basic_context(self):
        """Test basic context building."""
        context = build_context(mode="programming")

        assert context["mode"] == "programming"

    def test_context_with_rules(self):
        """Test context with rules."""
        context = build_context(
            mode="programming",
            rules=[
                {"priority": 1, "action": "track()", "when": "after edit"},
                {"priority": 2, "action": "finish()", "when": "at end"}
            ]
        )

        assert "rules" in context
        assert len(context["rules"]["rule"]) == 2

    def test_context_with_features(self):
        """Test context with features."""
        context = build_context(
            mode="devops",
            features={
                "syntax_validation": False,
                "command_logging": True
            }
        )

        assert "features" in context
        assert context["features"]["command_logging"] is True

    def test_context_with_hints(self):
        """Test context with hints."""
        context = build_context(
            mode="content",
            hints=["Use word_count()", "Track chapters"]
        )

        assert "hints" in context
        assert len(context["hints"]["hint"]) == 2


# =============================================================================
# Validation Function Tests
# =============================================================================

class TestValidation:
    """Tests for validation functions."""

    def test_is_valid_xml_true(self):
        """Test valid XML detection."""
        assert is_valid_xml("<root><child>text</child></root>")
        assert is_valid_xml('<root attr="value"/>')

    def test_is_valid_xml_false(self):
        """Test invalid XML detection."""
        assert not is_valid_xml("<root><child></root>")  # Mismatched tags
        assert not is_valid_xml("not xml at all")
        assert not is_valid_xml("<root attr=value/>")  # Unquoted attribute

    def test_parse_xml_response_success(self):
        """Test parsing valid XML response."""
        xml = xml_success("test", "OK", {"value": "123"})
        parsed = parse_xml_response(xml)

        assert parsed is not None
        assert parsed["status"] == "success"
        assert parsed["message"] == "OK"
        assert parsed["data"]["value"] == "123"

    def test_parse_xml_response_failure(self):
        """Test parsing invalid XML returns None."""
        assert parse_xml_response("not xml") is None
        assert parse_xml_response("<broken><xml>") is None

    def test_parse_xml_preserves_attributes(self):
        """Test that parsing preserves XML attributes."""
        xml = '<chainguard tool="test" version="6.0"><status>info</status></chainguard>'
        parsed = parse_xml_response(xml)

        assert parsed is not None
        assert "_attrs" in parsed
        assert parsed["_attrs"]["tool"] == "test"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_data(self):
        """Test response with empty data dict."""
        xml = xml_success("test", "OK", data={})

        assert is_valid_xml(xml)
        # Empty data dict doesn't create data element (no children to add)
        # This is expected behavior - only non-empty data creates elements
        assert "<status>success</status>" in xml

    def test_deeply_nested_data(self):
        """Test deeply nested data structures."""
        xml = xml_success(
            tool="test",
            data={
                "level1": {
                    "level2": {
                        "level3": {
                            "value": "deep"
                        }
                    }
                }
            }
        )

        assert is_valid_xml(xml)
        assert "<level3>" in xml
        assert "<value>deep</value>" in xml

    def test_unicode_content(self):
        """Test Unicode content handling."""
        xml = xml_success(
            tool="test",
            message="Scope: Bücher schreiben 📚",
            data={"emoji": "🔗", "german": "Größe"}
        )

        assert is_valid_xml(xml)
        assert "Bücher" in xml
        assert "📚" in xml
        assert "🔗" in xml

    def test_numeric_values(self):
        """Test numeric value handling."""
        xml = xml_info(
            tool="status",
            data={
                "int_val": 42,
                "float_val": 3.14,
                "zero": 0
            }
        )

        assert is_valid_xml(xml)
        assert "<int_val>42</int_val>" in xml
        assert "<float_val>3.14</float_val>" in xml
        assert "<zero>0</zero>" in xml

    def test_boolean_values(self):
        """Test boolean value handling (lowercase true/false)."""
        xml = xml_info(
            tool="test",
            data={"enabled": True, "disabled": False}
        )

        assert is_valid_xml(xml)
        assert "<enabled>true</enabled>" in xml
        assert "<disabled>false</disabled>" in xml

    def test_mixed_list_content(self):
        """Test lists with mixed content types."""
        xml = xml_info(
            tool="test",
            data={
                "items": ["string", 123, True, None]
            }
        )

        assert is_valid_xml(xml)
        # Count both <items> and <items /> (self-closing for None/empty)
        items_count = xml.count("<items>") + xml.count("<items />")
        assert items_count == 4


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests simulating real usage."""

    def test_set_scope_response(self):
        """Test realistic set_scope response."""
        xml = xml_success(
            tool="set_scope",
            message="Scope defined",
            data={
                "scope": {
                    "description": "Implement user authentication",
                    "mode": "programming",
                    "mode_source": "explicit",
                    "modules": "src/auth/*.ts",
                    "criteria_count": 3,
                    "checklist_count": 2
                }
            },
            context=build_context(
                mode="programming",
                rules=[
                    {"priority": 1, "action": "chainguard_track()", "when": "after each edit"},
                    {"priority": 2, "action": "chainguard_finish()", "when": "at end"}
                ],
                features={
                    "syntax_validation": True,
                    "db_inspection": True
                }
            )
        )

        assert is_valid_xml(xml)
        parsed = parse_xml_response(xml)
        assert parsed["status"] == "success"
        assert "scope" in parsed["data"]

    def test_track_error_response(self):
        """Test realistic track error response."""
        xml = xml_error(
            tool="track",
            message="Syntax error found",
            data={
                "file": "UserController.php",
                "validation": {
                    "status": "fail",
                    "errors": [
                        {
                            "type": "php_syntax",
                            "line": 42,
                            "message": "unexpected }",
                            "suggestion": "Missing semicolon"
                        }
                    ]
                }
            }
        )

        assert is_valid_xml(xml)
        assert "<status>error</status>" in xml
        assert "unexpected }" in xml

    def test_blocked_scope_response(self):
        """Test realistic blocked response."""
        xml = xml_blocked(
            tool="track",
            message="No scope set",
            blocker_type="scope_required",
            blocker_data={
                "description": "You must call chainguard_set_scope() first",
                "example": "chainguard_set_scope(description='...')",
                "next_action": "Set scope, then track files"
            }
        )

        assert is_valid_xml(xml)
        assert "<status>blocked</status>" in xml
        assert "<type>scope_required</type>" in xml
