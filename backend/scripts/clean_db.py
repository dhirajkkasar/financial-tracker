"""
Clean all portfolio data from the database.

Clears all user data tables (assets, transactions, valuations, goals, price cache,
portfolio snapshots, CAS snapshots, personal info) while preserving seeded reference
data (interest_rates, interest_rate_history).

Usage:
    cd backend
    .venv/bin/python scripts/clean_db.py              # dry-run: shows row counts
    .venv/bin/python scripts/clean_db.py --confirm    # actually deletes
"""

import argparse
import sys
import os

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal

# Tables to clear, in deletion order (children before parents to respect FK constraints).
# interest_rates and interest_rate_history are intentionally excluded — they are seeded
# reference data, not user data.
TABLES_TO_CLEAR = [
    "goal_allocations",
    "goals",
    "transactions",
    "valuations",
    "fd_details",
    "price_cache",
    "portfolio_snapshots",
    "cas_snapshots",
    "important_data",
    "assets",
]


def count_rows(db, table: str) -> int:
    result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
    return result.scalar()


def main():
    parser = argparse.ArgumentParser(description="Clean all portfolio data from the database.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete data. Without this flag, only shows row counts (dry-run).",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Always show current row counts
        print("\nCurrent row counts:")
        print(f"  {'Table':<30} {'Rows':>6}")
        print(f"  {'-'*30} {'-'*6}")
        totals = {}
        for table in TABLES_TO_CLEAR:
            try:
                n = count_rows(db, table)
                totals[table] = n
                print(f"  {table:<30} {n:>6}")
            except Exception as e:
                print(f"  {table:<30}   (error: {e})")
                totals[table] = 0

        total_rows = sum(totals.values())
        print(f"\n  Total rows to delete: {total_rows}")

        if not args.confirm:
            print("\nDry-run — no data deleted. Re-run with --confirm to actually delete.\n")
            return

        if total_rows == 0:
            print("\nDatabase is already empty. Nothing to do.\n")
            return

        print("\nDeleting...")
        # Disable FK checks for SQLite so we can delete in any order
        db.execute(text("PRAGMA foreign_keys=OFF"))
        for table in TABLES_TO_CLEAR:
            db.execute(text(f"DELETE FROM {table}"))
            print(f"  ✓ cleared {table} ({totals.get(table, 0)} rows)")
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()
        print("\nDone. Database cleared. Interest rates preserved.\n")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
