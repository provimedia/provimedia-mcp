"""
Tests for chainguard.db_inspector module.

Tests DBConfig, DBInspector, and schema formatting functionality.
"""

import time
import pytest
from dataclasses import asdict

from chainguard.db_inspector import (
    DBConfig,
    DBInspector,
    ColumnInfo,
    TableInfo,
    SchemaInfo,
    get_inspector,
    clear_inspector
)


class TestDBConfig:
    """Tests for DBConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DBConfig()
        assert config.host == "localhost"
        assert config.port == 3306
        assert config.user == ""
        assert config.password == ""
        assert config.database == ""
        assert config.db_type == "mysql"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = DBConfig(
            host="db.example.com",
            port=5432,
            user="admin",
            password="secret",
            database="mydb",
            db_type="postgres"
        )
        assert config.host == "db.example.com"
        assert config.port == 5432
        assert config.user == "admin"
        assert config.database == "mydb"
        assert config.db_type == "postgres"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = DBConfig(user="test", database="testdb")
        d = config.to_dict()
        assert d["user"] == "test"
        assert d["database"] == "testdb"
        assert d["host"] == "localhost"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "host": "remotehost",
            "port": 3307,
            "user": "dbuser",
            "password": "pass",
            "database": "proddb",
            "db_type": "mysql"
        }
        config = DBConfig.from_dict(data)
        assert config.host == "remotehost"
        assert config.port == 3307
        assert config.database == "proddb"

    def test_from_dict_ignores_unknown_fields(self):
        """Test that unknown fields are ignored."""
        data = {
            "user": "test",
            "database": "db",
            "unknown_field": "ignored"
        }
        config = DBConfig.from_dict(data)
        assert config.user == "test"
        assert not hasattr(config, "unknown_field")


class TestColumnInfo:
    """Tests for ColumnInfo dataclass."""

    def test_basic_column(self):
        """Test basic column creation."""
        col = ColumnInfo(name="id", type="INT")
        assert col.name == "id"
        assert col.type == "INT"
        assert col.nullable is True
        assert col.key == ""
        assert col.fk_ref == ""

    def test_primary_key_column(self):
        """Test primary key column."""
        col = ColumnInfo(
            name="id",
            type="INT",
            nullable=False,
            key="PRI",
            extra="auto_increment"
        )
        assert col.key == "PRI"
        assert "auto_increment" in col.extra

    def test_foreign_key_column(self):
        """Test foreign key column."""
        col = ColumnInfo(
            name="user_id",
            type="INT",
            fk_ref="users.id"
        )
        assert col.fk_ref == "users.id"


class TestTableInfo:
    """Tests for TableInfo dataclass."""

    def test_empty_table(self):
        """Test empty table creation."""
        table = TableInfo(name="empty_table")
        assert table.name == "empty_table"
        assert table.columns == []
        assert table.row_count == 0
        assert table.primary_key == []
        assert table.foreign_keys == {}

    def test_table_with_columns(self):
        """Test table with columns."""
        cols = [
            ColumnInfo(name="id", type="INT", key="PRI"),
            ColumnInfo(name="name", type="VARCHAR(255)"),
            ColumnInfo(name="email", type="VARCHAR(255)", key="UNI")
        ]
        table = TableInfo(
            name="users",
            columns=cols,
            row_count=100,
            primary_key=["id"]
        )
        assert len(table.columns) == 3
        assert table.row_count == 100
        assert "id" in table.primary_key


class TestSchemaInfo:
    """Tests for SchemaInfo dataclass."""

    def test_empty_schema(self):
        """Test empty schema creation."""
        schema = SchemaInfo(database="testdb", db_type="mysql")
        assert schema.database == "testdb"
        assert schema.db_type == "mysql"
        assert schema.tables == {}
        assert schema.cached_at == 0

    def test_schema_with_tables(self):
        """Test schema with tables."""
        schema = SchemaInfo(
            database="mydb",
            db_type="postgres",
            version="14.0",
            cached_at=time.time()
        )
        schema.tables["users"] = TableInfo(name="users", row_count=50)
        schema.tables["posts"] = TableInfo(name="posts", row_count=200)

        assert len(schema.tables) == 2
        assert "users" in schema.tables
        assert schema.tables["posts"].row_count == 200


class TestDBInspector:
    """Tests for DBInspector class."""

    def test_initial_state(self):
        """Test inspector initial state."""
        inspector = DBInspector()
        assert not inspector.is_connected()
        assert inspector._config is None
        assert inspector._schema is None

    def test_clear(self):
        """Test clearing inspector state."""
        inspector = DBInspector()
        inspector._connected = True
        inspector._config = DBConfig(database="test")
        inspector._schema = SchemaInfo(database="test", db_type="mysql")

        inspector.clear()

        assert not inspector.is_connected()
        assert inspector._config is None
        assert inspector._schema is None

    def test_format_schema_empty(self):
        """Test formatting empty schema."""
        inspector = DBInspector()
        result = inspector.format_schema(None)
        assert "Kein Schema" in result

    def test_format_schema_with_tables(self):
        """Test formatting schema with tables."""
        inspector = DBInspector()

        schema = SchemaInfo(
            database="testdb",
            db_type="mysql",
            version="8.0",
            cached_at=time.time()
        )

        # Add users table
        users = TableInfo(name="users", row_count=10)
        users.columns = [
            ColumnInfo(name="id", type="INT", key="PRI", extra="auto_increment"),
            ColumnInfo(name="username", type="VARCHAR(255)", key="UNI"),
            ColumnInfo(name="email", type="VARCHAR(255)")
        ]
        schema.tables["users"] = users

        # Add posts table with foreign key
        posts = TableInfo(name="posts", row_count=50)
        posts.columns = [
            ColumnInfo(name="id", type="INT", key="PRI"),
            ColumnInfo(name="user_id", type="INT", fk_ref="users.id"),
            ColumnInfo(name="title", type="VARCHAR(255)")
        ]
        posts.foreign_keys["user_id"] = "users.id"
        schema.tables["posts"] = posts

        result = inspector.format_schema(schema)

        # Check output contains expected elements
        assert "testdb" in result
        assert "mysql" in result
        assert "users" in result
        assert "posts" in result
        assert "PK" in result
        assert "AUTO" in result
        assert "FK→users.id" in result
        assert "UNIQUE" in result


class TestInspectorRegistry:
    """Tests for global inspector registry functions."""

    def test_get_inspector_creates_new(self):
        """Test that get_inspector creates new instance."""
        inspector = get_inspector("project_1")
        assert isinstance(inspector, DBInspector)

    def test_get_inspector_returns_same(self):
        """Test that get_inspector returns same instance for same project."""
        inspector1 = get_inspector("project_2")
        inspector2 = get_inspector("project_2")
        assert inspector1 is inspector2

    def test_get_inspector_different_projects(self):
        """Test that different projects get different inspectors."""
        inspector1 = get_inspector("project_a")
        inspector2 = get_inspector("project_b")
        assert inspector1 is not inspector2

    def test_clear_inspector(self):
        """Test clearing inspector for project."""
        inspector = get_inspector("project_to_clear")
        inspector._connected = True

        clear_inspector("project_to_clear")

        # Getting again should create new instance
        new_inspector = get_inspector("project_to_clear")
        assert not new_inspector.is_connected()

    def test_clear_nonexistent_inspector(self):
        """Test clearing non-existent inspector doesn't error."""
        # Should not raise
        clear_inspector("nonexistent_project_xyz")


class TestSchemaFormatting:
    """Additional tests for schema formatting edge cases."""

    def test_format_table_with_all_flags(self):
        """Test column with all possible flags."""
        inspector = DBInspector()
        schema = SchemaInfo(database="test", db_type="mysql", version="8.0")

        table = TableInfo(name="complex", row_count=5)
        table.columns = [
            ColumnInfo(
                name="id",
                type="BIGINT",
                nullable=False,
                key="PRI",
                extra="auto_increment",
                fk_ref=""
            )
        ]
        schema.tables["complex"] = table

        result = inspector.format_schema(schema)
        assert "PK" in result
        assert "AUTO" in result

    def test_format_empty_database(self):
        """Test formatting database with no tables."""
        inspector = DBInspector()
        schema = SchemaInfo(database="empty", db_type="sqlite", version="3.0")

        result = inspector.format_schema(schema)
        assert "empty" in result
        assert "sqlite" in result

    def test_format_postgres_serial(self):
        """Test PostgreSQL serial type detection."""
        inspector = DBInspector()
        schema = SchemaInfo(database="pgdb", db_type="postgres", version="14")

        table = TableInfo(name="test")
        table.columns = [
            ColumnInfo(name="id", type="integer", key="PRI", extra="serial")
        ]
        schema.tables["test"] = table

        result = inspector.format_schema(schema)
        assert "AUTO" in result  # Serial should show as AUTO


class TestCacheTTL:
    """Tests for schema cache TTL behavior."""

    def test_cache_not_expired(self):
        """Test that fresh cache is used."""
        inspector = DBInspector()
        inspector._cache_ttl = 300  # 5 minutes

        schema = SchemaInfo(database="test", db_type="mysql")
        schema.cached_at = time.time()  # Fresh
        inspector._schema = schema

        # Should not need refresh
        age = time.time() - schema.cached_at
        assert age < inspector._cache_ttl

    def test_cache_expired(self):
        """Test that expired cache triggers refresh."""
        inspector = DBInspector()
        inspector._cache_ttl = 1  # 1 second for test

        schema = SchemaInfo(database="test", db_type="mysql")
        schema.cached_at = time.time() - 10  # 10 seconds ago
        inspector._schema = schema

        # Should need refresh
        age = time.time() - schema.cached_at
        assert age >= inspector._cache_ttl


class TestPasswordSpecialChars:
    """Tests for password special character handling."""

    def test_config_with_exclamation_mark(self):
        """Test DBConfig with password containing ! character."""
        config = DBConfig(
            user="root",
            password="test!password",
            database="mydb"
        )
        assert config.password == "test!password"
        assert "!" in config.password

    def test_config_with_multiple_special_chars(self):
        """Test password with multiple special characters."""
        config = DBConfig(
            user="root",
            password='p@ss!w0rd#$%^&*()',
            database="mydb"
        )
        assert config.password == 'p@ss!w0rd#$%^&*()'

    def test_password_roundtrip_via_dict(self):
        """Test that special chars survive dict serialization."""
        original_password = "secret!pass@word#123"
        config = DBConfig(
            user="test",
            password=original_password,
            database="db"
        )

        # Serialize and deserialize
        d = config.to_dict()
        restored = DBConfig.from_dict(d)

        assert restored.password == original_password

    def test_password_in_json_roundtrip(self):
        """Test that special chars survive JSON serialization."""
        import json

        passwords_to_test = [
            "simple",
            "with!exclaim",
            "with@at",
            "with#hash",
            "complex!@#$%^&*()",
            "quotes'and\"double",
            "backslash\\here",
            "unicode\u00e4\u00f6\u00fc",
        ]

        for original_pw in passwords_to_test:
            config = DBConfig(user="u", password=original_pw, database="db")

            # JSON roundtrip (like MCP parameter passing)
            json_str = json.dumps(config.to_dict())
            restored_dict = json.loads(json_str)
            restored = DBConfig.from_dict(restored_dict)

            assert restored.password == original_pw, f"Failed for: {original_pw}"

    def test_password_special_char_detection(self):
        """Test detection of special characters in password."""
        special_chars = '!@#$%^&*()'

        test_cases = [
            ("simplepass", False),
            ("pass!word", True),
            ("pass@word", True),
            ("p@ss#word!", True),
            ("", False),
        ]

        for password, expected_has_special in test_cases:
            has_special = bool(password and any(c in password for c in special_chars))
            assert has_special == expected_has_special, f"Failed for: {password}"
