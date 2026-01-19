"""
CHAINGUARD MCP Server - Database Inspector Module

Live database schema inspection for accurate SQL query generation.
Prevents LLM from guessing field names by providing verified schema info.

Copyright (c) 2026 Provimedia GmbH
Licensed under the Polyform Noncommercial License 1.0.0
See LICENSE file in the project root for full license information.
"""

import asyncio
import time
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from .config import logger

# Database constants
DB_SCHEMA_CACHE_TTL = 300  # 5 minutes
DB_SAMPLE_ROWS = 5
DB_MAX_TABLES = 50

# SQL Injection Prevention: Allowed characters for identifiers
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def validate_identifier(name: str) -> bool:
    """
    Validate SQL identifier (table/column name) to prevent SQL injection.
    Only allows alphanumeric characters and underscores, starting with letter/underscore.
    """
    if not name or len(name) > 128:
        return False
    return bool(IDENTIFIER_PATTERN.match(name))


def safe_identifier(name: str, db_type: str = "mysql") -> str:
    """
    Return a safely quoted identifier or raise ValueError if invalid.
    """
    if not validate_identifier(name):
        raise ValueError(f"Invalid identifier: {name}")

    if db_type == "postgres":
        return f'"{name}"'
    else:  # mysql, sqlite
        return f"`{name}`"


@dataclass
class DBConfig:
    """Database connection configuration."""
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    db_type: str = "mysql"  # mysql, postgres, sqlite

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DBConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ColumnInfo:
    """Column metadata."""
    name: str
    type: str
    nullable: bool = True
    key: str = ""  # PRI, UNI, MUL
    default: Any = None
    extra: str = ""  # auto_increment etc.
    fk_ref: str = ""  # table.column if foreign key


@dataclass
class TableInfo:
    """Table metadata."""
    name: str
    columns: List[ColumnInfo] = field(default_factory=list)
    row_count: int = 0
    primary_key: List[str] = field(default_factory=list)
    foreign_keys: Dict[str, str] = field(default_factory=dict)  # column -> table.column


@dataclass
class SchemaInfo:
    """Complete database schema."""
    database: str
    db_type: str
    version: str = ""
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    cached_at: float = 0


class DBInspector:
    """
    Database schema inspector with TTL caching.

    Usage:
        inspector = DBInspector()
        await inspector.connect(config)
        schema = await inspector.get_schema()
        print(inspector.format_schema(schema))
    """

    def __init__(self):
        self._config: Optional[DBConfig] = None
        self._schema: Optional[SchemaInfo] = None
        self._cache_ttl: int = DB_SCHEMA_CACHE_TTL
        self._connected: bool = False

    def is_connected(self) -> bool:
        return self._connected and self._config is not None

    async def connect(self, config: DBConfig) -> Dict[str, Any]:
        """
        Test connection and store config.
        Credentials are stored in memory only.
        """
        self._config = config
        result = {"success": False, "message": "", "version": ""}

        try:
            if config.db_type == "mysql":
                result = await self._connect_mysql(config)
            elif config.db_type == "postgres":
                result = await self._connect_postgres(config)
            elif config.db_type == "sqlite":
                result = await self._connect_sqlite(config)
            else:
                result["message"] = f"Unsupported db_type: {config.db_type}"

            if result["success"]:
                self._connected = True
                logger.info(f"DB connected: {config.database} ({config.db_type})")

        except Exception as e:
            result["message"] = str(e)[:100]
            logger.error(f"DB connection failed: {e}")

        return result

    async def _connect_mysql(self, config: DBConfig) -> Dict[str, Any]:
        """Connect to MySQL and get version."""
        try:
            import aiomysql
        except ImportError:
            return {"success": False, "message": "aiomysql not installed. Run: pip install aiomysql"}

        # Debug: Log password characteristics (not the password itself!)
        pw_len = len(config.password) if config.password else 0
        pw_has_special = bool(config.password and any(c in config.password for c in '!@#$%^&*()'))
        logger.debug(f"MySQL connect: user={config.user}, db={config.database}, pw_len={pw_len}, pw_has_special={pw_has_special}")

        try:
            conn = await aiomysql.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                db=config.database,
                connect_timeout=10
            )

            async with conn.cursor() as cur:
                await cur.execute("SELECT VERSION()")
                version = (await cur.fetchone())[0]

            conn.close()
            return {"success": True, "message": f"Connected to {config.database}", "version": version}

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__

            # Log detailed error for debugging
            logger.error(f"MySQL connect failed: {error_type}: {error_msg}")
            if pw_has_special:
                logger.warning(f"Password contains special characters - this may cause issues with some MySQL configurations")

            # Provide helpful hints for common errors
            hint = ""
            if "Access denied" in error_msg:
                hint = " (check credentials)"
                if pw_has_special:
                    hint = " (password has special chars - try escaping or changing)"
            elif "Can't connect" in error_msg or "Connection refused" in error_msg:
                hint = " (check host/port)"

            return {"success": False, "message": f"{error_msg[:80]}{hint}", "version": ""}

    async def _connect_postgres(self, config: DBConfig) -> Dict[str, Any]:
        """Connect to PostgreSQL and get version."""
        try:
            import asyncpg
        except ImportError:
            return {"success": False, "message": "asyncpg not installed. Run: pip install asyncpg"}

        # Debug: Log password characteristics
        pw_len = len(config.password) if config.password else 0
        pw_has_special = bool(config.password and any(c in config.password for c in '!@#$%^&*()'))
        logger.debug(f"Postgres connect: user={config.user}, db={config.database}, pw_len={pw_len}, pw_has_special={pw_has_special}")

        try:
            conn = await asyncpg.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                database=config.database,
                timeout=10
            )

            version = await conn.fetchval("SELECT version()")
            await conn.close()

            # Extract version number
            version_short = version.split()[1] if version else ""
            return {"success": True, "message": f"Connected to {config.database}", "version": version_short}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Postgres connect failed: {type(e).__name__}: {error_msg}")
            if pw_has_special:
                logger.warning("Password contains special characters")

            hint = ""
            if "password authentication failed" in error_msg.lower():
                hint = " (check credentials)"
                if pw_has_special:
                    hint = " (password has special chars)"

            return {"success": False, "message": f"{error_msg[:80]}{hint}", "version": ""}

    async def _connect_sqlite(self, config: DBConfig) -> Dict[str, Any]:
        """Connect to SQLite database file."""
        try:
            import aiosqlite
        except ImportError:
            return {"success": False, "message": "aiosqlite not installed. Run: pip install aiosqlite"}

        db_path = config.database
        if not Path(db_path).exists():
            return {"success": False, "message": f"SQLite file not found: {db_path}"}

        try:
            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.execute("SELECT sqlite_version()")
                version = (await cursor.fetchone())[0]

            return {"success": True, "message": f"Connected to {db_path}", "version": version}

        except Exception as e:
            return {"success": False, "message": str(e)[:100], "version": ""}

    async def get_schema(self, force_refresh: bool = False) -> Optional[SchemaInfo]:
        """
        Get database schema with TTL caching.
        Returns cached schema if still valid, otherwise fetches fresh.
        """
        if not self._config:
            return None

        # Check cache
        if not force_refresh and self._schema:
            if time.time() - self._schema.cached_at < self._cache_ttl:
                return self._schema

        # Fetch fresh schema
        try:
            if self._config.db_type == "mysql":
                self._schema = await self._fetch_mysql_schema()
            elif self._config.db_type == "postgres":
                self._schema = await self._fetch_postgres_schema()
            elif self._config.db_type == "sqlite":
                self._schema = await self._fetch_sqlite_schema()

            if self._schema:
                self._schema.cached_at = time.time()
                logger.info(f"Schema loaded: {len(self._schema.tables)} tables")

        except Exception as e:
            logger.error(f"Schema fetch failed: {e}")

        return self._schema

    async def _fetch_mysql_schema(self) -> SchemaInfo:
        """Fetch MySQL schema."""
        import aiomysql

        schema = SchemaInfo(
            database=self._config.database,
            db_type="mysql"
        )

        conn = await aiomysql.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            db=self._config.database
        )

        try:
            async with conn.cursor() as cur:
                # Get version
                await cur.execute("SELECT VERSION()")
                schema.version = (await cur.fetchone())[0]

                # Get tables
                await cur.execute("SHOW TABLES")
                tables = [row[0] for row in await cur.fetchall()]

                for table_name in tables[:DB_MAX_TABLES]:
                    # Validate table name to prevent SQL injection
                    if not validate_identifier(table_name):
                        logger.warning(f"Skipping invalid table name: {table_name}")
                        continue

                    table = TableInfo(name=table_name)
                    safe_table = safe_identifier(table_name, "mysql")

                    # Get columns
                    await cur.execute(f"DESCRIBE {safe_table}")
                    for row in await cur.fetchall():
                        # Field, Type, Null, Key, Default, Extra
                        col = ColumnInfo(
                            name=row[0],
                            type=row[1],
                            nullable=(row[2] == "YES"),
                            key=row[3] or "",
                            default=row[4],
                            extra=row[5] or ""
                        )
                        if col.key == "PRI":
                            table.primary_key.append(col.name)
                        table.columns.append(col)

                    # Get row count (approximate for large tables)
                    await cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
                    table.row_count = (await cur.fetchone())[0]

                    # Get foreign keys
                    await cur.execute("""
                        SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                        AND REFERENCED_TABLE_NAME IS NOT NULL
                    """, (self._config.database, table_name))

                    for fk_row in await cur.fetchall():
                        col_name, ref_table, ref_col = fk_row
                        table.foreign_keys[col_name] = f"{ref_table}.{ref_col}"
                        # Update column info
                        for col in table.columns:
                            if col.name == col_name:
                                col.fk_ref = f"{ref_table}.{ref_col}"

                    schema.tables[table_name] = table

        finally:
            conn.close()

        return schema

    async def _fetch_postgres_schema(self) -> SchemaInfo:
        """Fetch PostgreSQL schema."""
        import asyncpg

        schema = SchemaInfo(
            database=self._config.database,
            db_type="postgres"
        )

        conn = await asyncpg.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database
        )

        try:
            # Get version
            version_str = await conn.fetchval("SELECT version()")
            schema.version = version_str.split()[1] if version_str else ""

            # Get tables
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)

            for table_row in tables[:DB_MAX_TABLES]:
                table_name = table_row['table_name']

                # Validate table name to prevent SQL injection
                if not validate_identifier(table_name):
                    logger.warning(f"Skipping invalid table name: {table_name}")
                    continue

                table = TableInfo(name=table_name)
                safe_table = safe_identifier(table_name, "postgres")

                # Get columns
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY ordinal_position
                """, table_name)

                for col_row in columns:
                    col = ColumnInfo(
                        name=col_row['column_name'],
                        type=col_row['data_type'],
                        nullable=(col_row['is_nullable'] == 'YES'),
                        default=col_row['column_default']
                    )

                    # Check for auto-increment (serial)
                    if col.default and 'nextval' in str(col.default):
                        col.extra = "serial"

                    table.columns.append(col)

                # Get primary keys (use safe_table for regclass to prevent injection)
                pk = await conn.fetch(f"""
                    SELECT a.attname FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = {safe_table}::regclass AND i.indisprimary
                """)
                table.primary_key = [p['attname'] for p in pk]

                for col in table.columns:
                    if col.name in table.primary_key:
                        col.key = "PRI"

                # Get row count
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {safe_table}")
                table.row_count = count

                # Get foreign keys
                fks = await conn.fetch("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS ref_table,
                        ccu.column_name AS ref_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = $1
                """, table_name)

                for fk_row in fks:
                    col_name = fk_row['column_name']
                    ref = f"{fk_row['ref_table']}.{fk_row['ref_column']}"
                    table.foreign_keys[col_name] = ref
                    for col in table.columns:
                        if col.name == col_name:
                            col.fk_ref = ref

                schema.tables[table_name] = table

        finally:
            await conn.close()

        return schema

    async def _fetch_sqlite_schema(self) -> SchemaInfo:
        """Fetch SQLite schema."""
        import aiosqlite

        schema = SchemaInfo(
            database=self._config.database,
            db_type="sqlite"
        )

        async with aiosqlite.connect(self._config.database) as conn:
            # Get version
            cursor = await conn.execute("SELECT sqlite_version()")
            schema.version = (await cursor.fetchone())[0]

            # Get tables
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

            for table_name in tables[:DB_MAX_TABLES]:
                # Validate table name to prevent SQL injection
                if not validate_identifier(table_name):
                    logger.warning(f"Skipping invalid table name: {table_name}")
                    continue

                table = TableInfo(name=table_name)
                safe_table = safe_identifier(table_name, "sqlite")

                # Get columns using PRAGMA
                cursor = await conn.execute(f"PRAGMA table_info({safe_table})")
                for row in await cursor.fetchall():
                    # cid, name, type, notnull, dflt_value, pk
                    col = ColumnInfo(
                        name=row[1],
                        type=row[2],
                        nullable=(row[3] == 0),
                        default=row[4],
                        key="PRI" if row[5] else ""
                    )
                    if col.key == "PRI":
                        table.primary_key.append(col.name)
                    table.columns.append(col)

                # Get row count
                cursor = await conn.execute(f"SELECT COUNT(*) FROM {safe_table}")
                table.row_count = (await cursor.fetchone())[0]

                # Get foreign keys
                cursor = await conn.execute(f"PRAGMA foreign_key_list({safe_table})")
                for fk_row in await cursor.fetchall():
                    # id, seq, table, from, to, on_update, on_delete, match
                    col_name = fk_row[3]
                    ref = f"{fk_row[2]}.{fk_row[4]}"
                    table.foreign_keys[col_name] = ref
                    for col in table.columns:
                        if col.name == col_name:
                            col.fk_ref = ref

                schema.tables[table_name] = table

        return schema

    async def get_table_details(self, table_name: str, show_sample: bool = False) -> Optional[str]:
        """Get detailed info for a single table, optionally with sample rows."""
        schema = await self.get_schema()
        if not schema or table_name not in schema.tables:
            return None

        table = schema.tables[table_name]
        lines = [
            f"## {table_name}",
            f"Rows: ~{table.row_count}",
            "",
            "### Columns"
        ]

        for col in table.columns:
            flags = []
            if col.key == "PRI":
                flags.append("PK")
            if "auto_increment" in col.extra.lower() or "serial" in col.extra.lower():
                flags.append("AUTO")
            if col.key == "UNI":
                flags.append("UNIQUE")
            if col.fk_ref:
                flags.append(f"FK→{col.fk_ref}")
            if not col.nullable:
                flags.append("NOT NULL")

            flag_str = " " + " ".join(flags) if flags else ""
            lines.append(f"- {col.name}: {col.type}{flag_str}")

        if table.foreign_keys:
            lines.append("")
            lines.append("### Foreign Keys")
            for col, ref in table.foreign_keys.items():
                lines.append(f"- {col} → {ref}")

        if show_sample:
            sample = await self._get_sample_rows(table_name)
            if sample:
                lines.append("")
                lines.append(f"### Sample Data ({len(sample)} rows)")
                lines.extend(sample)

        return "\n".join(lines)

    async def _get_sample_rows(self, table_name: str) -> List[str]:
        """Get sample rows from table."""
        if not self._config:
            return []

        # Validate table name to prevent SQL injection
        if not validate_identifier(table_name):
            return [f"(invalid table name: {table_name})"]

        safe_table = safe_identifier(table_name, self._config.db_type)

        try:
            if self._config.db_type == "mysql":
                import aiomysql
                conn = await aiomysql.connect(
                    host=self._config.host,
                    port=self._config.port,
                    user=self._config.user,
                    password=self._config.password,
                    db=self._config.database
                )
                async with conn.cursor() as cur:
                    await cur.execute(f"SELECT * FROM {safe_table} LIMIT {DB_SAMPLE_ROWS}")
                    rows = await cur.fetchall()
                    cols = [d[0] for d in cur.description]
                conn.close()

            elif self._config.db_type == "postgres":
                import asyncpg
                conn = await asyncpg.connect(
                    host=self._config.host,
                    port=self._config.port,
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database
                )
                rows = await conn.fetch(f"SELECT * FROM {safe_table} LIMIT {DB_SAMPLE_ROWS}")
                cols = list(rows[0].keys()) if rows else []
                rows = [tuple(r.values()) for r in rows]
                await conn.close()

            elif self._config.db_type == "sqlite":
                import aiosqlite
                async with aiosqlite.connect(self._config.database) as conn:
                    cursor = await conn.execute(f"SELECT * FROM {safe_table} LIMIT {DB_SAMPLE_ROWS}")
                    rows = await cursor.fetchall()
                    cols = [d[0] for d in cursor.description]

            else:
                return []

            if not rows:
                return ["(keine Daten)"]

            # Format as simple table
            lines = [" | ".join(cols)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                values = [str(v)[:20] if v is not None else "NULL" for v in row]
                lines.append(" | ".join(values))

            return lines

        except Exception as e:
            return [f"(Fehler: {str(e)[:50]})"]

    def format_schema(self, schema: SchemaInfo) -> str:
        """
        Format schema for token-efficient output.
        ~50-100 tokens for typical database.
        """
        if not schema:
            return "Kein Schema geladen."

        lines = [f"📊 Database: {schema.database} ({schema.db_type} {schema.version})", ""]

        for table_name, table in schema.tables.items():
            lines.append(f"{table_name} ({len(table.columns)} cols, ~{table.row_count} rows)")

            for i, col in enumerate(table.columns):
                prefix = "└─" if i == len(table.columns) - 1 else "├─"

                flags = []
                if col.key == "PRI":
                    flags.append("PK")
                if "auto_increment" in col.extra.lower() or "serial" in col.extra.lower():
                    flags.append("AUTO")
                if col.key == "UNI":
                    flags.append("UNIQUE")
                if col.fk_ref:
                    flags.append(f"FK→{col.fk_ref}")

                flag_str = " " + " ".join(flags) if flags else ""
                lines.append(f"{prefix} {col.name}: {col.type}{flag_str}")

            lines.append("")

        cache_age = int(time.time() - schema.cached_at) if schema.cached_at else 0
        if cache_age > 0:
            lines.append(f"(Cache: {cache_age}s alt, TTL: {self._cache_ttl}s)")

        return "\n".join(lines)

    def clear(self):
        """Clear connection and cache."""
        self._config = None
        self._schema = None
        self._connected = False


# =============================================================================
# Global inspector instances per project
# =============================================================================
_inspectors: Dict[str, DBInspector] = {}


def get_inspector(project_id: str) -> DBInspector:
    """Get or create inspector for project."""
    if project_id not in _inspectors:
        _inspectors[project_id] = DBInspector()
    return _inspectors[project_id]


def clear_inspector(project_id: str):
    """Clear inspector for project."""
    if project_id in _inspectors:
        _inspectors[project_id].clear()
        del _inspectors[project_id]
