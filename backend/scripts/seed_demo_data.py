"""
Seed realistic demo data for all asset types.
Idempotent — safe to run multiple times (skips existing assets by identifier/name).

Coverage:
  Deposits  — SBI FD + HDFC RD
  PPF       — PPF Account (contributions + valuation)
  EPF       — EPF Account (contributions + valuation)
  NPS       — NPS Tier-I HDFC (contributions + valuation)
  US Stocks — Apple Inc (BUY lots) + Infosys RSU (VEST lots)
  Gold      — Digital Gold (BUY lots) + SGB Series XI
  Real Est. — Bengaluru Apartment (valuation-based)
  Goals     — Retirement / Home Down Payment / Child Education
  Personal  — Bank accounts, MF folios, identity, insurance
"""
import sys, os, hashlib, uuid, json
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.valuation import Valuation
from app.models.fd_detail import FDDetail, FDType, CompoundingType
from app.models.price_cache import PriceCache
from app.models.goal import Goal, GoalAllocation
from app.models.important_data import ImportantData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paise(inr: float) -> int:
    return round(inr * 100)

def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]

def _lot_id() -> str:
    return str(uuid.uuid4())

def _find_or_create_asset(db, identifier: str, **kwargs) -> Asset:
    existing = db.query(Asset).filter_by(identifier=identifier).first()
    if existing:
        print(f"  skip asset '{kwargs.get('name')}' (already exists)")
        return existing
    asset = Asset(identifier=identifier, **kwargs)
    db.add(asset)
    db.flush()
    print(f"  + asset '{kwargs.get('name')}'")
    return asset

def _find_or_create_asset_by_name(db, name: str, **kwargs) -> Asset:
    existing = db.query(Asset).filter_by(name=name).first()
    if existing:
        print(f"  skip asset '{name}' (already exists)")
        return existing
    asset = Asset(name=name, **kwargs)
    db.add(asset)
    db.flush()
    print(f"  + asset '{name}'")
    return asset

def _add_txn(db, asset_id, txn_type, txn_date, amount_inr, units=None,
             price_per_unit=None, forex_rate=None, charges_inr=0.0, notes=None):
    tid = _txn_id(asset_id, txn_type, txn_date, amount_inr, units)
    existing = db.query(Transaction).filter_by(txn_id=tid).first()
    if existing:
        return existing
    lot_id = _lot_id() if txn_type in ("BUY", "SIP", "CONTRIBUTION", "VEST") else None
    t = Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        units=units,
        price_per_unit=price_per_unit,
        forex_rate=forex_rate,
        amount_inr=_paise(amount_inr),
        charges_inr=_paise(charges_inr),
        lot_id=lot_id,
        notes=notes,
    )
    db.add(t)
    return t

def _add_valuation(db, asset_id, val_date, value_inr, source="manual"):
    existing = db.query(Valuation).filter_by(asset_id=asset_id, date=val_date).first()
    if existing:
        return existing
    v = Valuation(asset_id=asset_id, date=val_date, value_inr=_paise(value_inr), source=source)
    db.add(v)
    return v

def _add_price_cache(db, asset_id, price_inr):
    existing = db.query(PriceCache).filter_by(asset_id=asset_id).first()
    if existing:
        return existing
    pc = PriceCache(
        asset_id=asset_id,
        price_inr=_paise(price_inr),
        fetched_at=datetime.utcnow(),
        source="demo_seed",
        is_stale=False,
    )
    db.add(pc)
    return pc


# ---------------------------------------------------------------------------
# Deposits (FD + RD)
# ---------------------------------------------------------------------------

def seed_deposits(db):
    print("\n[Deposits]")

    # SBI Fixed Deposit — 5L @ 7.5% quarterly, 3yr
    fd_asset = _find_or_create_asset(
        db, identifier="SBI-FD-001",
        name="SBI Fixed Deposit", asset_type=AssetType.FD,
        asset_class=AssetClass.DEBT, currency="INR",
    )
    if not db.query(FDDetail).filter_by(asset_id=fd_asset.id).first():
        db.add(FDDetail(
            asset_id=fd_asset.id, bank="SBI", fd_type=FDType.FD,
            principal_amount=_paise(500000),
            interest_rate_pct=7.5, compounding=CompoundingType.QUARTERLY,
            start_date=date(2022, 6, 1), maturity_date=date(2025, 6, 1),
            is_matured=False, tds_applicable=True,
        ))
        _add_txn(db, fd_asset.id, "CONTRIBUTION", date(2022, 6, 1), -500000.0,
                 notes="Principal deposit")
        print("  + SBI FD detail")

    # HDFC Recurring Deposit — ₹10k/month @ 7.0% quarterly, 36 months
    rd_asset = _find_or_create_asset(
        db, identifier="HDFC-RD-001",
        name="HDFC Recurring Deposit", asset_type=AssetType.RD,
        asset_class=AssetClass.DEBT, currency="INR",
    )
    if not db.query(FDDetail).filter_by(asset_id=rd_asset.id).first():
        db.add(FDDetail(
            asset_id=rd_asset.id, bank="HDFC Bank", fd_type=FDType.RD,
            principal_amount=_paise(10000),   # monthly instalment
            interest_rate_pct=7.0, compounding=CompoundingType.QUARTERLY,
            start_date=date(2023, 1, 1), maturity_date=date(2026, 1, 1),
            is_matured=False, tds_applicable=False,
        ))
        for m in range(27):   # 27 monthly contributions so far
            from datetime import timedelta
            contrib_date = date(2023, 1, 1).replace(day=1)
            # advance m months
            month = (1 + m - 1) % 12 + 1
            year = 2023 + (m) // 12
            contrib_date = date(year, month, 1)
            _add_txn(db, rd_asset.id, "CONTRIBUTION", contrib_date, -10000.0,
                     notes=f"RD instalment {m+1}")
        print("  + HDFC RD detail + 27 contributions")


# ---------------------------------------------------------------------------
# PPF
# ---------------------------------------------------------------------------

def seed_ppf(db):
    print("\n[PPF]")
    asset = _find_or_create_asset_by_name(
        db, name="PPF Account",
        identifier="PPF-001",
        asset_type=AssetType.PPF, asset_class=AssetClass.DEBT, currency="INR",
    )
    # Annual contributions FY2019 to FY2025
    contribs = [
        (date(2019, 4, 5), -150000.0),
        (date(2020, 4, 6), -150000.0),
        (date(2021, 4, 5), -100000.0),
        (date(2022, 4, 4), -150000.0),
        (date(2023, 4, 3), -150000.0),
        (date(2024, 4, 1), -150000.0),
        (date(2025, 4, 1), -150000.0),
    ]
    for d, amt in contribs:
        _add_txn(db, asset.id, "CONTRIBUTION", d, amt)
    # Latest passbook valuation
    _add_valuation(db, asset.id, date(2025, 3, 31), 1285000.0)
    print("  + PPF contributions + valuation ₹12.85L")


# ---------------------------------------------------------------------------
# EPF
# ---------------------------------------------------------------------------

def seed_epf(db):
    print("\n[EPF]")
    asset = _find_or_create_asset_by_name(
        db, name="EPF Account",
        identifier="EPF-001",
        asset_type=AssetType.EPF, asset_class=AssetClass.DEBT, currency="INR",
    )
    # Monthly contributions (employee + employer share combined) from 2020
    monthly_amount = -12000.0   # ₹6k employee + ₹6k employer
    for year in range(2020, 2026):
        for month in range(1, 13):
            if year == 2025 and month > 3:
                break
            _add_txn(db, asset.id, "CONTRIBUTION", date(year, month, 1), monthly_amount)
    # Annual valuations
    _add_valuation(db, asset.id, date(2022, 3, 31), 486000.0)
    _add_valuation(db, asset.id, date(2023, 3, 31), 642000.0)
    _add_valuation(db, asset.id, date(2024, 3, 31), 812000.0)
    _add_valuation(db, asset.id, date(2025, 3, 31), 995000.0)
    print("  + EPF monthly contributions + valuations")


# ---------------------------------------------------------------------------
# NPS
# ---------------------------------------------------------------------------

def seed_nps(db):
    print("\n[NPS]")
    asset = _find_or_create_asset_by_name(
        db, name="NPS Tier-I (HDFC Pension)",
        identifier="NPS-001",
        asset_type=AssetType.NPS, asset_class=AssetClass.DEBT, currency="INR",
    )
    # Monthly voluntary contributions
    monthly = -5000.0
    for year in range(2021, 2026):
        for month in range(1, 13):
            if year == 2025 and month > 3:
                break
            _add_txn(db, asset.id, "CONTRIBUTION", date(year, month, 1), monthly)
    # NAV-based valuations
    _add_valuation(db, asset.id, date(2023, 3, 31), 178000.0)
    _add_valuation(db, asset.id, date(2024, 3, 31), 248000.0)
    _add_valuation(db, asset.id, date(2025, 3, 31), 325000.0)
    print("  + NPS contributions + valuations")


# ---------------------------------------------------------------------------
# US Stocks
# ---------------------------------------------------------------------------

def seed_us_stocks(db):
    print("\n[US Stocks]")

    # Apple Inc (AAPL)
    aapl = _find_or_create_asset(
        db, identifier="AAPL",
        name="Apple Inc", asset_type=AssetType.STOCK_US,
        asset_class=AssetClass.EQUITY, currency="USD",
    )
    us_buys = [
        (date(2021, 2, 15), 5, 128.50, 53705.0,  74.50),   # units, usd_price, inr_total, forex
        (date(2022, 6, 20), 5, 134.90, 56088.0,  83.12),
        (date(2023, 9, 10), 3, 173.00, 43218.0,  83.62),
    ]
    for d, units, usd_price, inr_amt, forex in us_buys:
        _add_txn(db, aapl.id, "BUY", d, -inr_amt,
                 units=units, price_per_unit=usd_price, forex_rate=forex)
    # Current price — AAPL ~$221, USD/INR ~84
    _add_price_cache(db, aapl.id, 221.0 * 84.0)   # ~₹18,564 per share
    print("  + Apple 13 units across 3 lots")

    # Infosys RSU
    rsu = _find_or_create_asset(
        db, identifier="INFY-RSU",
        name="Infosys RSU", asset_type=AssetType.STOCK_US,
        asset_class=AssetClass.EQUITY, currency="USD",
    )
    rsu_vests = [
        (date(2022, 3, 1),  25, 18.50, 34688.0, 74.94, "25 units vested @ FMV $18.50"),
        (date(2023, 3, 1),  25, 16.80, 34860.0, 83.00, "25 units vested @ FMV $16.80"),
        (date(2024, 3, 1),  25, 17.20, 35994.0, 83.79, "25 units vested @ FMV $17.20"),
    ]
    for d, units, usd_price, inr_amt, forex, note in rsu_vests:
        _add_txn(db, rsu.id, "VEST", d, -inr_amt,
                 units=units, price_per_unit=usd_price, forex_rate=forex, notes=note)
    # Sell 25 units (first vest lot) in FY24
    _add_txn(db, rsu.id, "SELL", date(2024, 8, 15), 37100.0,
             units=25, price_per_unit=17.67, forex_rate=83.79,
             notes="Sold 25 units to cover taxes")
    _add_price_cache(db, rsu.id, 17.50 * 84.0)   # ~₹1,470 per share
    print("  + Infosys RSU 75 vested, 25 sold")


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

def seed_gold(db):
    print("\n[Gold]")

    # Digital Gold (10g over time)
    gold = _find_or_create_asset(
        db, identifier="GOLD-DIGITAL-001",
        name="Digital Gold (Augmont)", asset_type=AssetType.GOLD,
        asset_class=AssetClass.GOLD, currency="INR",
    )
    gold_buys = [
        (date(2020, 10, 15), 2.0,  51800.0, -103600.0),   # units=grams, price/g, total
        (date(2021, 11, 5),  3.0,  47500.0, -142500.0),
        (date(2023, 3, 18),  2.0,  59200.0, -118400.0),
        (date(2024, 6, 10),  3.0,  72500.0, -217500.0),
    ]
    for d, units, price_per_g, amt in gold_buys:
        _add_txn(db, gold.id, "BUY", d, amt, units=units, price_per_unit=price_per_g)
    # Current price ~₹9,200/gram (July 2025)
    _add_price_cache(db, gold.id, 9200.0)
    print("  + Digital Gold 10g across 4 lots")

    # SGB — Sovereign Gold Bond
    sgb = _find_or_create_asset(
        db, identifier="SGB-XI-2021",
        name="SGB Series XI (2021-27)", asset_type=AssetType.SGB,
        asset_class=AssetClass.GOLD, currency="INR",
    )
    _add_txn(db, sgb.id, "BUY", date(2021, 5, 17), -243500.0,
             units=50.0, price_per_unit=4870.0,
             notes="50 units @ ₹4870 issue price (₹50 online discount applied)")
    # Semi-annual interest (2.5% p.a.)
    for yr, mo, amt in [(2021, 11, 6087.5), (2022, 5, 6087.5), (2022, 11, 6087.5),
                        (2023, 5, 6087.5), (2023, 11, 6087.5), (2024, 5, 6087.5),
                        (2024, 11, 6087.5), (2025, 5, 6087.5)]:
        _add_txn(db, sgb.id, "INTEREST", date(yr, mo, 17), amt,
                 notes="SGB semi-annual interest @2.5% p.a.")
    _add_price_cache(db, sgb.id, 9200.0)   # gold price per gram ≈ same basis
    print("  + SGB 50 units + 8 interest payments")


# ---------------------------------------------------------------------------
# Real Estate
# ---------------------------------------------------------------------------

def seed_real_estate(db):
    print("\n[Real Estate]")
    asset = _find_or_create_asset_by_name(
        db, name="Bengaluru Apartment (Whitefield)",
        identifier="RE-BLR-001",
        asset_type=AssetType.REAL_ESTATE, asset_class=AssetClass.REAL_ESTATE, currency="INR",
    )
    # Purchase + stamp duty/registration as a single CONTRIBUTION
    _add_txn(db, asset.id, "CONTRIBUTION", date(2019, 9, 15), -7200000.0,
             notes="Purchase price ₹72L (incl. stamp duty + registration)")
    _add_txn(db, asset.id, "CONTRIBUTION", date(2019, 9, 15), -50000.0,
             notes="Interior & furnishing")
    # Annual valuations (property appreciation)
    _add_valuation(db, asset.id, date(2021, 3, 31), 7800000.0,
                   source="market_estimate")
    _add_valuation(db, asset.id, date(2022, 3, 31), 8400000.0)
    _add_valuation(db, asset.id, date(2023, 3, 31), 9000000.0)
    _add_valuation(db, asset.id, date(2024, 3, 31), 9600000.0)
    _add_valuation(db, asset.id, date(2025, 3, 31), 10200000.0)
    print("  + Bengaluru apartment ₹72L purchase, current value ₹1.02Cr")


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

def seed_goals(db):
    print("\n[Goals]")

    # Find assets for allocation (may not exist if individual seeds skipped)
    epf = db.query(Asset).filter_by(identifier="EPF-001").first()
    nps = db.query(Asset).filter_by(name="NPS Tier-I (HDFC Pension)").first()
    fd  = db.query(Asset).filter_by(identifier="SBI-FD-001").first()
    rd  = db.query(Asset).filter_by(identifier="HDFC-RD-001").first()
    re  = db.query(Asset).filter_by(identifier="RE-BLR-001").first()

    def _find_or_create_goal(name, target_inr, target_date, return_pct, notes=None):
        existing = db.query(Goal).filter_by(name=name).first()
        if existing:
            print(f"  skip goal '{name}'")
            return existing
        g = Goal(
            name=name,
            target_amount_inr=_paise(target_inr),
            target_date=target_date,
            assumed_return_pct=return_pct,
            notes=notes,
        )
        db.add(g)
        db.flush()
        print(f"  + goal '{name}'")
        return g

    def _alloc(goal, asset, pct):
        if asset is None:
            return
        existing = db.query(GoalAllocation).filter_by(
            goal_id=goal.id, asset_id=asset.id
        ).first()
        if not existing:
            db.add(GoalAllocation(goal_id=goal.id, asset_id=asset.id, allocation_pct=pct))

    # Retirement Fund
    retirement = _find_or_create_goal(
        "Retirement Fund", 50_000_000.0, date(2048, 3, 31), 11.0,
        notes="Target corpus for retirement at 60"
    )
    if epf: _alloc(retirement, epf, 100)
    if nps: _alloc(retirement, nps, 100)

    # Home Down Payment (already have apartment; this is for upgrade)
    home = _find_or_create_goal(
        "Home Upgrade Fund", 3_000_000.0, date(2027, 12, 31), 7.5,
        notes="Down payment for a bigger property"
    )
    if fd: _alloc(home, fd, 100)

    # Child Education
    edu = _find_or_create_goal(
        "Child Education Fund", 5_000_000.0, date(2036, 6, 30), 12.0,
        notes="Higher education corpus"
    )
    if rd: _alloc(edu, rd, 100)

    # Wealth Goal (real estate exit)
    wealth = _find_or_create_goal(
        "Wealth Corpus", 20_000_000.0, date(2035, 3, 31), 12.0,
        notes="General wealth building"
    )
    if re: _alloc(wealth, re, 100)

    db.commit()


# ---------------------------------------------------------------------------
# Personal Info (ImportantData)
# ---------------------------------------------------------------------------

def seed_personal_info(db):
    print("\n[Personal Info]")

    entries = [
        ("BANK", "SBI Savings Account", {
            "account_number": "XXXX XXXX 4521",
            "ifsc": "SBIN0001234",
            "branch": "MG Road, Bengaluru",
            "type": "Savings",
            "nominee": "Spouse",
        }),
        ("BANK", "HDFC Salary Account", {
            "account_number": "XXXX XXXX 8830",
            "ifsc": "HDFC0002345",
            "branch": "Whitefield, Bengaluru",
            "type": "Salary",
        }),
        ("MF_FOLIO", "Zerodha MF Folio", {
            "folio_number": "123456789",
            "amc": "Multiple",
            "platform": "Zerodha Coin",
            "pan": "XXXXX0000X",
        }),
        ("IDENTITY", "PAN Card", {
            "pan": "XXXXX0000X",
            "name": "Demo User",
            "dob": "1990-01-15",
        }),
        ("IDENTITY", "Passport", {
            "number": "X0000000",
            "expiry": "2030-05-20",
            "issue_place": "Bengaluru",
        }),
        ("INSURANCE", "LIC Term Plan", {
            "policy_number": "LIC-123456789",
            "sum_assured": "₹1,00,00,000",
            "premium": "₹14,500/year",
            "maturity": "2050-01-15",
            "nominee": "Spouse",
        }),
        ("INSURANCE", "Health Insurance (Star)", {
            "policy_number": "STAR-9876543",
            "sum_insured": "₹20,00,000",
            "premium": "₹18,200/year",
            "renewal_date": "2025-08-01",
            "members": "Self + Spouse + 1 Child",
        }),
        ("ACCOUNT", "Zerodha Trading Account", {
            "client_id": "ZZ1234",
            "dp_id": "CDSL-12345678",
            "segment": "Equity, F&O",
        }),
        ("ACCOUNT", "NPS PRAN", {
            "pran": "XXXX XXXX 1234",
            "trustee": "HDFC Pension",
            "tier": "Tier-I and Tier-II",
        }),
    ]

    for category, label, fields in entries:
        existing = db.query(ImportantData).filter_by(label=label).first()
        if existing:
            print(f"  skip '{label}'")
            continue
        db.add(ImportantData(
            category=category,
            label=label,
            fields_json=json.dumps(fields),
        ))
        print(f"  + {category}: {label}")

    db.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    db = SessionLocal()
    try:
        print("Seeding demo data...")
        seed_deposits(db)
        seed_ppf(db)
        seed_epf(db)
        seed_nps(db)
        seed_us_stocks(db)
        seed_gold(db)
        seed_real_estate(db)
        db.commit()
        seed_goals(db)
        seed_personal_info(db)
        print("\nDone. All demo data seeded.")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    main()
