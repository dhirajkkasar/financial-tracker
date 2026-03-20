"""
Master seed script — runs all seeds in the correct order.

Usage:
    python scripts/seed_all.py

Individual scripts can still be run independently if needed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
import scripts.seed_interest_rates as _sir
import scripts.seed_demo_data as _sdd
import scripts.seed_historical_sips as _shs


def main():
    print("=" * 60)
    print("Step 1/3 — Interest rates")
    print("=" * 60)
    db = SessionLocal()
    try:
        _sir.seed(db)
    finally:
        db.close()

    print()
    print("=" * 60)
    print("Step 2/3 — Demo assets (deposits, PPF, EPF, NPS, gold …)")
    print("=" * 60)
    _sdd.main()

    print()
    print("=" * 60)
    print("Step 3/3 — Historical SIPs & stock BUY lots")
    print("=" * 60)
    _shs.main()

    print()
    print("All done. Database is ready.")


if __name__ == "__main__":
    main()
