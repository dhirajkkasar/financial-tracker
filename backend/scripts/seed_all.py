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
import scripts.seed_closed_positions as _scp
import scripts.seed_market_assets as _sma
import scripts.seed_personal_info as _spi
import scripts.seed_nps_schemes as _sns
import scripts.seed_epf_rich as _ser
import scripts.seed_fd_comprehensive as _sfc
import scripts.seed_us_stocks_rsu as _susr
import scripts.seed_cas_snapshots as _scs
import scripts.seed_portfolio_snapshots as _sps
import scripts.seed_price_cache as _spc
import scripts.seed_valuations as _sv


def main():
    print("=" * 60)
    print("Step 1/14 — Interest rates")
    print("=" * 60)
    db = SessionLocal()
    try:
        _sir.seed(db)
    finally:
        db.close()

    print()
    print("=" * 60)
    print("Step 2/14 — Demo assets (deposits, PPF, EPF, NPS, gold …)")
    print("=" * 60)
    _sdd.main()

    print()
    print("=" * 60)
    print("Step 3/14 — Historical SIPs & stock BUY lots")
    print("=" * 60)
    _shs.main()

    print()
    print("=" * 60)
    print("Step 4/14 — Closed positions (inactive stocks, MFs, matured FDs)")
    print("=" * 60)
    _scp.main()

    print()
    print("=" * 60)
    print("Step 5/14 — Market assets (MF and Indian stock assets)")
    print("=" * 60)
    _sma.main()

    print()
    print("=" * 60)
    print("Step 6/14 — Personal info data")
    print("=" * 60)
    _spi.main()

    print()
    print("=" * 60)
    print("Step 7/14 — NPS schemes")
    print("=" * 60)
    _sns.main()

    print()
    print("=" * 60)
    print("Step 8/14 — Rich EPF data")
    print("=" * 60)
    _ser.main()

    print()
    print("=" * 60)
    print("Step 9/14 — Comprehensive FD/RD assets")
    print("=" * 60)
    _sfc.main()

    print()
    print("=" * 60)
    print("Step 10/14 — US stocks RSU data")
    print("=" * 60)
    _susr.main()

    print()
    print("=" * 60)
    print("Step 11/14 — CAS snapshots for MF assets")
    print("=" * 60)
    _scs.main()

    print()
    print("=" * 60)
    print("Step 12/14 — Portfolio snapshots")
    print("=" * 60)
    _sps.main()

    print()
    print("=" * 60)
    print("Step 13/14 — Price cache for market assets")
    print("=" * 60)
    _spc.main()

    print()
    print("=" * 60)
    print("Step 14/14 — Manual valuations")
    print("=" * 60)
    _sv.main()

    print()
    print("All done. Database is ready.")


if __name__ == "__main__":
    main()
