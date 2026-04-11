"""
Migrate data from local SQLite database to Supabase PostgreSQL.

Usage:
    uv run python scripts/migrate_sqlite_to_postgres.py [--sqlite-path PATH] [--dry-run]

Defaults:
    --sqlite-path  dhiraj_financial_portfolio.db  (relative to backend/)
    --dry-run      False

The script reads rows from SQLite and bulk-inserts them into Postgres in
FK-safe order. It is idempotent: rows that already exist (by primary key)
are skipped (ON CONFLICT DO NOTHING).

Requires:
    - DATABASE_URL in .env pointing to Supabase (postgresql+psycopg://...)
    - Alembic migrations already applied to Supabase (schema must exist)
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg
from dotenv import load_dotenv

# Tables in FK-safe insertion order (parents before children)
TABLES_IN_ORDER = [
    "members",           # no FK
    "interest_rates",    # no FK
    "goals",             # no FK
    "assets",            # FK → members
    "fd_details",        # FK → assets
    "transactions",      # FK → assets
    "valuations",        # FK → assets
    "cas_snapshots",     # FK → assets
    "price_cache",       # FK → assets
    "portfolio_snapshots",  # FK → members
    "goal_allocations",  # FK → goals, assets
    "important_data",    # FK → members
    # alembic_version is intentionally skipped — managed by Alembic
]


def build_pg_dsn(database_url: str) -> str:
    """Convert SQLAlchemy URL (postgresql+psycopg://...) to plain psycopg DSN."""
    # Strip the +psycopg driver suffix so psycopg can parse it directly
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return dsn


def get_columns(sqlite_cur: sqlite3.Cursor, table: str) -> list[str]:
    sqlite_cur.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in sqlite_cur.fetchall()]


def get_pg_bool_columns(pg_con: psycopg.Connection, table: str) -> set[str]:
    """Return the set of column names that are boolean type in Postgres."""
    with pg_con.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND data_type = 'boolean'
            """,
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def coerce_row(row: tuple, columns: list[str], bool_cols: set[str]) -> tuple:
    """Convert SQLite integer booleans (0/1) to Python bool for Postgres."""
    if not bool_cols:
        return row
    return tuple(
        bool(val) if col in bool_cols and val is not None else val
        for col, val in zip(columns, row)
    )


def get_pg_existing_ids(pg_con: psycopg.Connection, table: str) -> set[int]:
    """Return all primary key IDs already present in the Postgres table."""
    with pg_con.cursor() as cur:
        cur.execute(f'SELECT id FROM "{table}"')
        return {row[0] for row in cur.fetchall()}


def filter_fk_orphans(
    rows: list[tuple],
    columns: list[str],
    fk_col: str,
    valid_ids: set[int],
) -> tuple[list[tuple], int]:
    """Drop rows where fk_col references an ID not in valid_ids."""
    if fk_col not in columns:
        return rows, 0
    idx = columns.index(fk_col)
    kept, dropped = [], 0
    for row in rows:
        if row[idx] is None or row[idx] in valid_ids:
            kept.append(row)
        else:
            dropped += 1
    return kept, dropped


# FK columns to validate per table (table → (fk_column, parent_table))
FK_CHECKS: dict[str, list[tuple[str, str]]] = {
    "assets":             [("member_id", "members")],
    "fd_details":         [("asset_id", "assets")],
    "transactions":       [("asset_id", "assets")],
    "valuations":         [("asset_id", "assets")],
    "cas_snapshots":      [("asset_id", "assets")],
    "price_cache":        [("asset_id", "assets")],
    "portfolio_snapshots":[("member_id", "members")],
    "goal_allocations":   [("goal_id", "goals"), ("asset_id", "assets")],
    "important_data":     [("member_id", "members")],
}


def migrate_table(
    sqlite_con: sqlite3.Connection,
    pg_con: psycopg.Connection,
    table: str,
    dry_run: bool,
    valid_ids_cache: dict[str, set[int]],
) -> int:
    sqlite_cur = sqlite_con.cursor()
    sqlite_cur.execute(f'SELECT * FROM "{table}"')
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"  {table}: 0 rows — skipped")
        return 0

    columns = get_columns(sqlite_cur, table)
    bool_cols = get_pg_bool_columns(pg_con, table)

    # Filter out orphaned FK rows
    total_dropped = 0
    for fk_col, parent_table in FK_CHECKS.get(table, []):
        if parent_table not in valid_ids_cache:
            valid_ids_cache[parent_table] = get_pg_existing_ids(pg_con, parent_table)
        rows, dropped = filter_fk_orphans(rows, columns, fk_col, valid_ids_cache[parent_table])
        total_dropped += dropped

    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f"ON CONFLICT DO NOTHING"
    )

    orphan_note = f" ({total_dropped} orphaned rows skipped)" if total_dropped else ""
    if dry_run:
        print(f"  {table}: {len(rows)} rows — DRY RUN (would insert){orphan_note}")
        return len(rows)

    coerced_rows = [coerce_row(row, columns, bool_cols) for row in rows]
    with pg_con.cursor() as pg_cur:
        pg_cur.executemany(sql, coerced_rows)

    pg_con.commit()
    print(f"  {table}: {len(rows)} rows — inserted (duplicates skipped){orphan_note}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite → Supabase PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default="dhiraj_financial_portfolio.db",
        help="Path to the SQLite database file (default: dhiraj_financial_portfolio.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be migrated without writing to Postgres",
    )
    args = parser.parse_args()

    # Load .env from backend directory
    backend_dir = Path(__file__).parent.parent
    load_dotenv(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or not database_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL is not set or not a PostgreSQL URL.")
        print("  Set DATABASE_URL in backend/.env to your Supabase connection string.")
        sys.exit(1)

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_absolute():
        sqlite_path = backend_dir / sqlite_path

    if not sqlite_path.exists():
        print(f"ERROR: SQLite file not found: {sqlite_path}")
        sys.exit(1)

    pg_dsn = build_pg_dsn(database_url)

    print(f"Source:      {sqlite_path}")
    print(f"Destination: {pg_dsn.split('@')[-1]}")  # hide credentials
    print(f"Dry run:     {args.dry_run}")
    print()

    sqlite_con = sqlite3.connect(sqlite_path)
    sqlite_con.row_factory = None  # keep as tuples for executemany

    try:
        with psycopg.connect(pg_dsn) as pg_con:
            print("Connected to Supabase PostgreSQL.")
            print()

            total_rows = 0
            valid_ids_cache: dict[str, set[int]] = {}
            for table in TABLES_IN_ORDER:
                try:
                    count = migrate_table(sqlite_con, pg_con, table, args.dry_run, valid_ids_cache)
                    total_rows += count
                except Exception as exc:
                    print(f"  {table}: FAILED — {exc}")
                    if not args.dry_run:
                        pg_con.rollback()
                    raise

            print()
            action = "would migrate" if args.dry_run else "migrated"
            print(f"Done. {action} {total_rows} rows across {len(TABLES_IN_ORDER)} tables.")

    finally:
        sqlite_con.close()


if __name__ == "__main__":
    main()
