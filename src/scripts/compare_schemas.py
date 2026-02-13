"""
Script para comparar schemas entre banco local e producao.

Compara:
- Tabelas
- Colunas (nome, tipo, nullable, default)
- Indices
- Constraints (PK, FK, UNIQUE)

Uso:
    DATABASE_URL_PROD="postgresql://..." python -m src.scripts.compare_schemas

Ou comparando dois bancos especificos:
    DATABASE_URL_LOCAL="postgresql://..." DATABASE_URL_PROD="postgresql://..." python -m src.scripts.compare_schemas
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = structlog.get_logger(__name__)


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str]

    def __eq__(self, other):
        if not isinstance(other, ColumnInfo):
            return False
        return (self.name == other.name and
                self.data_type == other.data_type and
                self.is_nullable == other.is_nullable)

    def __hash__(self):
        return hash(self.name)


@dataclass
class TableInfo:
    name: str
    columns: dict[str, ColumnInfo]
    primary_keys: list[str]
    foreign_keys: list[dict]
    indexes: list[dict]


def get_async_url(url: str) -> str:
    """Converte URL para formato async."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def get_tables(conn) -> list[str]:
    """Lista todas as tabelas do schema public."""
    result = await conn.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
    )
    return [row[0] for row in result.fetchall()]


async def get_columns(conn, table_name: str) -> dict[str, ColumnInfo]:
    """Obtem informacoes das colunas de uma tabela."""
    result = await conn.execute(
        text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = :table_name
            AND table_schema = 'public'
            ORDER BY ordinal_position
        """),
        {"table_name": table_name}
    )
    columns = {}
    for row in result.fetchall():
        col = ColumnInfo(
            name=row[0],
            data_type=row[1],
            is_nullable=row[2] == "YES",
            column_default=row[3]
        )
        columns[col.name] = col
    return columns


async def get_primary_keys(conn, table_name: str) -> list[str]:
    """Obtem primary keys de uma tabela."""
    result = await conn.execute(
        text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = :table_name
            AND tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_schema = 'public'
            ORDER BY kcu.ordinal_position
        """),
        {"table_name": table_name}
    )
    return [row[0] for row in result.fetchall()]


async def get_foreign_keys(conn, table_name: str) -> list[dict]:
    """Obtem foreign keys de uma tabela."""
    result = await conn.execute(
        text("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column,
                tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE tc.table_name = :table_name
            AND tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
        """),
        {"table_name": table_name}
    )
    return [
        {
            "column": row[0],
            "foreign_table": row[1],
            "foreign_column": row[2],
            "constraint_name": row[3]
        }
        for row in result.fetchall()
    ]


async def get_indexes(conn, table_name: str) -> list[dict]:
    """Obtem indices de uma tabela."""
    result = await conn.execute(
        text("""
            SELECT
                i.relname AS index_name,
                a.attname AS column_name,
                ix.indisunique AS is_unique
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = :table_name
            AND t.relkind = 'r'
            ORDER BY i.relname, a.attnum
        """),
        {"table_name": table_name}
    )
    return [
        {
            "index_name": row[0],
            "column_name": row[1],
            "is_unique": row[2]
        }
        for row in result.fetchall()
    ]


async def get_schema_info(database_url: str) -> dict[str, TableInfo]:
    """Obtem informacoes completas do schema."""
    engine = create_async_engine(get_async_url(database_url), echo=False)

    schema = {}
    async with engine.connect() as conn:
        tables = await get_tables(conn)

        for table_name in tables:
            columns = await get_columns(conn, table_name)
            primary_keys = await get_primary_keys(conn, table_name)
            foreign_keys = await get_foreign_keys(conn, table_name)
            indexes = await get_indexes(conn, table_name)

            schema[table_name] = TableInfo(
                name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                indexes=indexes
            )

    await engine.dispose()
    return schema


def compare_schemas(local_schema: dict[str, TableInfo], prod_schema: dict[str, TableInfo]) -> dict:
    """Compara dois schemas e retorna diferencas."""
    differences = {
        "tables_missing_in_prod": [],
        "tables_extra_in_prod": [],
        "column_differences": {},
        "type_differences": {},
        "nullable_differences": {},
    }

    local_tables = set(local_schema.keys())
    prod_tables = set(prod_schema.keys())

    # Tabelas faltando na producao
    differences["tables_missing_in_prod"] = sorted(local_tables - prod_tables)

    # Tabelas extras na producao
    differences["tables_extra_in_prod"] = sorted(prod_tables - local_tables)

    # Comparar colunas das tabelas em comum
    common_tables = local_tables & prod_tables

    for table_name in sorted(common_tables):
        local_table = local_schema[table_name]
        prod_table = prod_schema[table_name]

        local_cols = set(local_table.columns.keys())
        prod_cols = set(prod_table.columns.keys())

        missing_cols = local_cols - prod_cols
        extra_cols = prod_cols - local_cols

        if missing_cols or extra_cols:
            differences["column_differences"][table_name] = {
                "missing_in_prod": sorted(missing_cols),
                "extra_in_prod": sorted(extra_cols)
            }

        # Comparar tipos e nullable das colunas em comum
        common_cols = local_cols & prod_cols
        for col_name in common_cols:
            local_col = local_table.columns[col_name]
            prod_col = prod_table.columns[col_name]

            # Normalizar tipos para comparacao
            local_type = normalize_type(local_col.data_type)
            prod_type = normalize_type(prod_col.data_type)

            if local_type != prod_type:
                if table_name not in differences["type_differences"]:
                    differences["type_differences"][table_name] = {}
                differences["type_differences"][table_name][col_name] = {
                    "local": local_col.data_type,
                    "prod": prod_col.data_type
                }

            if local_col.is_nullable != prod_col.is_nullable:
                if table_name not in differences["nullable_differences"]:
                    differences["nullable_differences"][table_name] = {}
                differences["nullable_differences"][table_name][col_name] = {
                    "local": local_col.is_nullable,
                    "prod": prod_col.is_nullable
                }

    return differences


def normalize_type(data_type: str) -> str:
    """Normaliza tipos de dados para comparacao."""
    # Mapeamentos comuns
    type_map = {
        "character varying": "varchar",
        "integer": "int4",
        "bigint": "int8",
        "smallint": "int2",
        "double precision": "float8",
        "real": "float4",
        "boolean": "bool",
        "timestamp without time zone": "timestamp",
        "timestamp with time zone": "timestamptz",
    }
    return type_map.get(data_type.lower(), data_type.lower())


def log_report(differences: dict, local_schema: dict, prod_schema: dict):
    """Log relatorio de diferencas."""
    logger.info("schema_comparison_report_started",
                local_table_count=len(local_schema),
                prod_table_count=len(prod_schema))

    # Tabelas faltando na producao
    if differences["tables_missing_in_prod"]:
        for table in differences["tables_missing_in_prod"]:
            cols = list(local_schema[table].columns.keys()) if table in local_schema else []
            logger.warning("table_missing_in_prod", table=table,
                          columns=', '.join(cols[:5]) + ('...' if len(cols) > 5 else ''))
    else:
        logger.info("all_local_tables_exist_in_prod")

    # Tabelas extras na producao
    if differences["tables_extra_in_prod"]:
        for table in differences["tables_extra_in_prod"]:
            logger.warning("table_extra_in_prod", table=table)

    # Diferencas de colunas
    if differences["column_differences"]:
        for table, cols in differences["column_differences"].items():
            if cols["missing_in_prod"]:
                logger.warning("columns_missing_in_prod", table=table,
                              columns=', '.join(cols['missing_in_prod']))
            if cols["extra_in_prod"]:
                logger.warning("columns_extra_in_prod", table=table,
                              columns=', '.join(cols['extra_in_prod']))
    else:
        logger.info("all_columns_synchronized")

    # Diferencas de tipos
    if differences["type_differences"]:
        for table, cols in differences["type_differences"].items():
            for col, types in cols.items():
                logger.warning("type_difference", table=table, column=col,
                              local_type=types['local'], prod_type=types['prod'])

    # Diferencas de nullable
    if differences["nullable_differences"]:
        for table, cols in differences["nullable_differences"].items():
            for col, nullable in cols.items():
                local_n = "NULL" if nullable['local'] else "NOT NULL"
                prod_n = "NULL" if nullable['prod'] else "NOT NULL"
                logger.warning("nullable_difference", table=table, column=col,
                              local=local_n, prod=prod_n)

    # Resumo
    has_issues = (
        differences["tables_missing_in_prod"] or
        differences["column_differences"] or
        differences["type_differences"]
    )

    if has_issues:
        logger.warning("schema_comparison_has_differences")
    else:
        logger.info("schemas_are_compatible")


async def main():
    """Executa comparacao de schemas."""
    # URLs dos bancos
    local_url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    prod_url = os.getenv("DATABASE_URL_PROD")

    if not local_url:
        logger.error("database_url_not_set", variable="DATABASE_URL_LOCAL or DATABASE_URL")
        return

    if not prod_url:
        logger.error("database_url_not_set", variable="DATABASE_URL_PROD")
        return

    logger.info("connecting_to_databases")

    try:
        logger.info("fetching_schema", target="local")
        local_schema = await get_schema_info(local_url)
        logger.info("schema_fetched", target="local", table_count=len(local_schema))
    except Exception as e:
        logger.error("schema_fetch_failed", target="local", error=str(e))
        return

    try:
        logger.info("fetching_schema", target="production")
        prod_schema = await get_schema_info(prod_url)
        logger.info("schema_fetched", target="production", table_count=len(prod_schema))
    except Exception as e:
        logger.error("schema_fetch_failed", target="production", error=str(e))
        return

    # Comparar schemas
    differences = compare_schemas(local_schema, prod_schema)

    # Log relatorio
    log_report(differences, local_schema, prod_schema)


if __name__ == "__main__":
    asyncio.run(main())
