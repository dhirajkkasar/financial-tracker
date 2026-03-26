"""
Seed multiple realistic NPS scheme assets (Tier I + Tier II).

Schemes (anonymised SM codes from real account):
  Tier I:
    DFC Scheme E  (SM008001) — equity; primary employer contribution
    HDFC Scheme G (SM008003) — govt securities; secondary contribution
    SBI Scheme C  (SM001004) — corporate bonds; tertiary contribution
  Tier II:
    HDFC Scheme E (SM008004) — equity voluntary tier-II savings
    LIC Scheme G  (SM003010) — govt securities; switch-in target

Monthly contributions start Jan 2023.
Quarterly BILLING charges added per scheme.
One SWITCH_OUT/SWITCH_IN between Tier II schemes (annual rebalance).
"""
import sys, os, hashlib, uuid
from datetime import date, datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.price_cache import PriceCache


def _p(inr: float) -> int:
    return round(inr * 100)


def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _lot() -> str:
    return str(uuid.uuid4())


def _find_or_create_asset(db, identifier: str, name: str, **kwargs) -> Asset:
    existing = db.query(Asset).filter_by(identifier=identifier).first()
    if existing:
        print(f"  skip '{name}' (exists)")
        return existing
    a = Asset(identifier=identifier, name=name, **kwargs)
    db.add(a)
    db.flush()
    print(f"  + {name} ({identifier})")
    return a


def _add_txn(db, asset_id, txn_type: str, txn_date: date,
             amount_inr: float, units: Optional[float] = None,
             price_per_unit: Optional[float] = None, notes: Optional[str] = None):
    tid = _txn_id("nps", asset_id, txn_type, txn_date, amount_inr, units or "")
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return
    needs_lot = txn_type in ("CONTRIBUTION", "SWITCH_IN")
    db.add(Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        units=units,
        price_per_unit=price_per_unit,
        amount_inr=_p(amount_inr),
        charges_inr=0,
        lot_id=_lot() if needs_lot else None,
        notes=notes,
    ))


def _add_price_cache(db, asset_id: int, price_inr: float):
    if not db.query(PriceCache).filter_by(asset_id=asset_id).first():
        db.add(PriceCache(
            asset_id=asset_id,
            price_inr=_p(price_inr),
            fetched_at=datetime.utcnow(),
            source="demo_seed",
            is_stale=False,
        ))


# ---------------------------------------------------------------------------
# NAV checkpoints for linear interpolation
# ---------------------------------------------------------------------------

def _lerp(checkpoints: list[tuple[date, float]], target: date) -> float:
    if target <= checkpoints[0][0]:
        return checkpoints[0][1]
    if target >= checkpoints[-1][0]:
        return checkpoints[-1][1]
    for i in range(len(checkpoints) - 1):
        d0, v0 = checkpoints[i]
        d1, v1 = checkpoints[i + 1]
        if d0 <= target <= d1:
            t = (target - d0).days / (d1 - d0).days
            return v0 + t * (v1 - v0)
    return checkpoints[-1][1]


# approximate quarterly NAV history per scheme
NAV_HISTORY = {
    "SM008001": [  # DFC Scheme E (equity)
        (date(2023,  1, 1), 28.50),
        (date(2023,  7, 1), 33.00),
        (date(2024,  1, 1), 40.00),
        (date(2024,  7, 1), 46.00),
        (date(2025,  1, 1), 52.00),
        (date(2025,  7, 1), 58.00),
        (date(2026,  3, 1), 64.00),
    ],
    "SM008003": [  # HDFC Scheme G (govt)
        (date(2023,  1, 1), 18.50),
        (date(2023,  7, 1), 19.20),
        (date(2024,  1, 1), 20.00),
        (date(2024,  7, 1), 20.80),
        (date(2025,  1, 1), 21.50),
        (date(2025,  7, 1), 22.20),
        (date(2026,  3, 1), 23.00),
    ],
    "SM001004": [  # SBI Scheme C (corporate bonds)
        (date(2023,  1, 1), 22.00),
        (date(2023,  7, 1), 23.10),
        (date(2024,  1, 1), 24.30),
        (date(2024,  7, 1), 25.50),
        (date(2025,  1, 1), 26.70),
        (date(2025,  7, 1), 27.80),
        (date(2026,  3, 1), 29.00),
    ],
    "SM008004": [  # HDFC Scheme E Tier II (equity)
        (date(2023,  1, 1), 26.00),
        (date(2023,  7, 1), 30.50),
        (date(2024,  1, 1), 37.00),
        (date(2024,  7, 1), 42.50),
        (date(2025,  1, 1), 48.00),
        (date(2025,  7, 1), 53.50),
        (date(2026,  3, 1), 59.00),
    ],
    "SM003010": [  # LIC Scheme G Tier II (govt)
        (date(2023,  1, 1), 16.80),
        (date(2023,  7, 1), 17.40),
        (date(2024,  1, 1), 18.10),
        (date(2024,  7, 1), 18.80),
        (date(2025,  1, 1), 19.50),
        (date(2025,  7, 1), 20.20),
        (date(2026,  3, 1), 21.00),
    ],
}


def _monthly_dates(start: date, end: date):
    d = start
    while d <= end:
        yield d
        mo = d.month % 12 + 1
        yr = d.year + (1 if d.month == 12 else 0)
        d = d.replace(year=yr, month=mo)


CONTRIBUTION_END = date(2026, 3, 31)


# ---------------------------------------------------------------------------
# Scheme definitions
# ---------------------------------------------------------------------------

SCHEMES = [
    {
        "identifier": "SM008001",
        "name": "NPS - DFC Scheme E Tier I",
        "asset_class": AssetClass.EQUITY,
        "monthly_amount": 8411.0,   # employer + employee combined
        "voluntary_months": {4: 37500.0},  # April bonus contribution
        "billing_quarterly": 85.0,
        "tier": "I",
        "start": date(2023, 1, 10),
    },
    {
        "identifier": "SM008003",
        "name": "NPS - HDFC Scheme G Tier I",
        "asset_class": AssetClass.DEBT,
        "monthly_amount": 1476.0,
        "voluntary_months": {},
        "billing_quarterly": 15.0,
        "tier": "I",
        "start": date(2023, 1, 10),
    },
    {
        "identifier": "SM001004",
        "name": "NPS - SBI Scheme C Tier I",
        "asset_class": AssetClass.DEBT,
        "monthly_amount": 1682.0,
        "voluntary_months": {4: 7500.0},   # April voluntary contribution
        "billing_quarterly": 18.0,
        "tier": "I",
        "start": date(2023, 1, 10),
    },
    {
        "identifier": "SM008004",
        "name": "NPS - HDFC Scheme E Tier II",
        "asset_class": AssetClass.EQUITY,
        "monthly_amount": 5000.0,    # voluntary tier-II SIP
        "voluntary_months": {},
        "billing_quarterly": 12.0,
        "tier": "II",
        "start": date(2023, 4, 15),
    },
    {
        "identifier": "SM003010",
        "name": "NPS - LIC Scheme G Tier II",
        "asset_class": AssetClass.DEBT,
        "monthly_amount": 0.0,       # no regular contributions — only switch-ins
        "voluntary_months": {},
        "billing_quarterly": 8.0,
        "tier": "II",
        "start": date(2023, 4, 15),
    },
]


def seed(db):
    print("\n[NPS Schemes]")

    assets = {}
    for s in SCHEMES:
        a = _find_or_create_asset(
            db, identifier=s["identifier"], name=s["name"],
            asset_type=AssetType.NPS,
            asset_class=s["asset_class"],
            currency="INR",
            is_active=True,
        )
        assets[s["identifier"]] = a
        nav_history = NAV_HISTORY[s["identifier"]]
        latest_nav = _lerp(nav_history, date(2026, 3, 31))
        _add_price_cache(db, a.id, latest_nav)

    # ── Monthly contributions ────────────────────────────────────────────────
    for s in SCHEMES:
        a = assets[s["identifier"]]
        nav_history = NAV_HISTORY[s["identifier"]]
        if s["monthly_amount"] == 0:
            continue

        for d in _monthly_dates(s["start"], CONTRIBUTION_END):
            nav = _lerp(nav_history, d)
            units = round(s["monthly_amount"] / nav, 4)
            _add_txn(db, a.id, "CONTRIBUTION", d,
                     -s["monthly_amount"], units=units, price_per_unit=round(nav, 4),
                     notes="Monthly NPS contribution")

            # annual voluntary top-up (in April each year)
            vol_amt = s["voluntary_months"].get(d.month, 0)
            if vol_amt:
                vol_units = round(vol_amt / nav, 4)
                _add_txn(db, a.id, "CONTRIBUTION", d,
                         -vol_amt, units=vol_units, price_per_unit=round(nav, 4),
                         notes="Voluntary NPS contribution")

    # ── Quarterly BILLING charges ────────────────────────────────────────────
    billing_quarters = [
        date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31),
        date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31),
        date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31),
        date(2026, 3, 31),
    ]
    for s in SCHEMES:
        a = assets[s["identifier"]]
        for bq in billing_quarters:
            if bq < s["start"]:
                continue
            _add_txn(db, a.id, "BILLING", bq, -s["billing_quarterly"],
                     notes="NPS fund management charge")

    # ── SWITCH_OUT / SWITCH_IN: HDFC Tier II → LIC Tier II ──────────────────
    # Annual rebalancing: Dec each year, move 50,000 from HDFC E Tier II to LIC G Tier II
    hdfc_t2 = assets["SM008004"]
    lic_t2  = assets["SM003010"]
    switch_events = [
        (date(2023, 12, 15), 50000.0),
        (date(2024, 12, 15), 75000.0),
        (date(2025, 12, 15), 80000.0),
    ]
    for sw_date, sw_amt in switch_events:
        nav_out = _lerp(NAV_HISTORY["SM008004"], sw_date)
        nav_in  = _lerp(NAV_HISTORY["SM003010"], sw_date)
        units_out = round(sw_amt / nav_out, 4)
        units_in  = round(sw_amt / nav_in,  4)
        _add_txn(db, hdfc_t2.id, "SWITCH_OUT", sw_date,
                 sw_amt, units=units_out, price_per_unit=round(nav_out, 4),
                 notes="Rebalance: switch to LIC G Tier II")
        _add_txn(db, lic_t2.id, "SWITCH_IN", sw_date,
                 -sw_amt, units=units_in, price_per_unit=round(nav_in, 4),
                 notes="Rebalance: switch from HDFC E Tier II")

    db.commit()
    print(f"  {len(SCHEMES)} NPS schemes seeded with contributions, billing, switch events.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
