"""
Script para comparar schemas entre banco local e produção.

Compara:
- Tabelas
- Colunas (nome, tipo, nullable, default)
- Índices
- Constraints (PK, FK, UNIQUE)

Uso:
    DATABASE_URL_PROD="postgresql://..." python -m src.scripts.compare_schemas

Ou comparando dois bancos específicos:
    DATABASE_URL_LOCAL="postgresql://..." DATABASE_URL_PROD="postgresql://..." python -m src.scripts.compare_schemas
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


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
    """Obtém informações das colunas de uma tabela."""
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
    """Obtém primary keys de uma tabela."""
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
    """Obtém foreign keys de uma tabela."""
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
    """Obtém índices de uma tabela."""
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
    """Obtém informações completas do schema."""
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
    """Compara dois schemas e retorna diferenças."""
    differences = {
        "tables_missing_in_prod": [],
        "tables_extra_in_prod": [],
        "column_differences": {},
        "type_differences": {},
        "nullable_differences": {},
    }

    local_tables = set(local_schema.keys())
    prod_tables = set(prod_schema.keys())

    # Tabelas faltando na produção
    differences["tables_missing_in_prod"] = sorted(local_tables - prod_tables)

    # Tabelas extras na produção
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

            # Normalizar tipos para comparação
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
    """Normaliza tipos de dados para comparação."""
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


def print_report(differences: dict, local_schema: dict, prod_schema: dict):
    """Imprime relatório de diferenças."""
    print("\n" + "=" * 60)
    print("RELATÓRIO DE COMPARAÇÃO DE SCHEMAS")
    print("=" * 60)

    print(f"\nTabelas no banco LOCAL: {len(local_schema)}")
    print(f"Tabelas no banco PRODUÇÃO: {len(prod_schema)}")

    # Tabelas faltando na produção
    if differences["tables_missing_in_prod"]:
        print(f"\n{'='*60}")
        print("TABELAS FALTANDO NA PRODUÇÃO:")
        print("=" * 60)
        for table in differences["tables_missing_in_prod"]:
            print(f"  - {table}")
            if table in local_schema:
                cols = list(local_schema[table].columns.keys())
                print(f"    Colunas: {', '.join(cols[:5])}{'...' if len(cols) > 5 else ''}")
    else:
        print("\n[OK] Todas as tabelas do local existem na produção")

    # Tabelas extras na produção
    if differences["tables_extra_in_prod"]:
        print(f"\n{'='*60}")
        print("TABELAS EXTRAS NA PRODUÇÃO (não existem no local):")
        print("=" * 60)
        for table in differences["tables_extra_in_prod"]:
            print(f"  - {table}")

    # Diferenças de colunas
    if differences["column_differences"]:
        print(f"\n{'='*60}")
        print("DIFERENÇAS DE COLUNAS:")
        print("=" * 60)
        for table, cols in differences["column_differences"].items():
            print(f"\n  Tabela: {table}")
            if cols["missing_in_prod"]:
                print(f"    Colunas faltando na PROD: {', '.join(cols['missing_in_prod'])}")
            if cols["extra_in_prod"]:
                print(f"    Colunas extras na PROD: {', '.join(cols['extra_in_prod'])}")
    else:
        print("\n[OK] Todas as colunas estão sincronizadas")

    # Diferenças de tipos
    if differences["type_differences"]:
        print(f"\n{'='*60}")
        print("DIFERENÇAS DE TIPOS:")
        print("=" * 60)
        for table, cols in differences["type_differences"].items():
            print(f"\n  Tabela: {table}")
            for col, types in cols.items():
                print(f"    {col}: LOCAL={types['local']} vs PROD={types['prod']}")

    # Diferenças de nullable
    if differences["nullable_differences"]:
        print(f"\n{'='*60}")
        print("DIFERENÇAS DE NULLABLE:")
        print("=" * 60)
        for table, cols in differences["nullable_differences"].items():
            print(f"\n  Tabela: {table}")
            for col, nullable in cols.items():
                local_n = "NULL" if nullable['local'] else "NOT NULL"
                prod_n = "NULL" if nullable['prod'] else "NOT NULL"
                print(f"    {col}: LOCAL={local_n} vs PROD={prod_n}")

    # Resumo
    has_issues = (
        differences["tables_missing_in_prod"] or
        differences["column_differences"] or
        differences["type_differences"]
    )

    print(f"\n{'='*60}")
    print("RESUMO")
    print("=" * 60)
    if has_issues:
        print("\n[!] ATENÇÃO: Existem diferenças entre os schemas!")
        print("    Execute as migrações necessárias na produção.")
    else:
        print("\n[OK] Os schemas estão compatíveis!")

    print("\n")


async def main():
    """Executa comparação de schemas."""
    # URLs dos bancos
    local_url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    prod_url = os.getenv("DATABASE_URL_PROD")

    if not local_url:
        print("Erro: DATABASE_URL_LOCAL ou DATABASE_URL não definida")
        print("Defina a variável de ambiente com a URL do banco local")
        return

    if not prod_url:
        print("Erro: DATABASE_URL_PROD não definida")
        print("Defina a variável de ambiente com a URL do banco de produção")
        return

    print("Conectando aos bancos de dados...")

    try:
        print("  - Obtendo schema do banco LOCAL...")
        local_schema = await get_schema_info(local_url)
        print(f"    Encontradas {len(local_schema)} tabelas")
    except Exception as e:
        print(f"Erro ao conectar no banco LOCAL: {e}")
        return

    try:
        print("  - Obtendo schema do banco PRODUÇÃO...")
        prod_schema = await get_schema_info(prod_url)
        print(f"    Encontradas {len(prod_schema)} tabelas")
    except Exception as e:
        print(f"Erro ao conectar no banco PRODUÇÃO: {e}")
        return

    # Comparar schemas
    differences = compare_schemas(local_schema, prod_schema)

    # Imprimir relatório
    print_report(differences, local_schema, prod_schema)


if __name__ == "__main__":
    asyncio.run(main())
