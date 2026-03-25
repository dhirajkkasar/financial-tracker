"""Unit tests for EPFAutoContribService.backfill_missing_contributions."""
import calendar
import hashlib
from datetime import date

import pytest

from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.services.epf_auto_contrib_service import EPFAutoContribService, _epf_txn_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_epf_asset(db, name="My EPF", identifier="AB/1234/567", is_active=True):
    asset = Asset(
        name=name,
        asset_type=AssetType.EPF,
        asset_class=AssetClass.DEBT,
        currency="INR",
        identifier=identifier,
        is_active=is_active,
    )
    db.add(asset)
    db.flush()
    return asset


def _add_contribution(db, asset_id, year, month, notes, amount_paise):
    last_day = calendar.monthrange(year, month)[1]
    txn_date = date(year, month, last_day)
    mmyyyy = f"{month:02d}{year}"
    member_id = db.query(Asset).filter(Asset.id == asset_id).first().identifier or ""

    note_to_key = {
        "Employee Share": ("CONTRIB_EMP", abs(amount_paise)),
        "Employer Share": ("CONTRIB_ER", abs(amount_paise)),
        "Pension Contribution (EPS)": ("CONTRIB_EPS", abs(amount_paise)),
    }
    key, paise_val = note_to_key[notes]
    txn_id = _epf_txn_id(member_id, key, mmyyyy, paise_val)

    txn = Transaction(
        txn_id=txn_id,
        asset_id=asset_id,
        type=TransactionType.CONTRIBUTION,
        date=txn_date,
        amount_inr=amount_paise,
        charges_inr=0,
        notes=notes,
    )
    db.add(txn)
    db.commit()
    return txn


def _contributions_for_month(db, asset_id, year, month):
    last_day = calendar.monthrange(year, month)[1]
    txn_date = date(year, month, last_day)
    return (
        db.query(Transaction)
        .filter(
            Transaction.asset_id == asset_id,
            Transaction.type == TransactionType.CONTRIBUTION,
            Transaction.date == txn_date,
        )
        .all()
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEPFAutoContribServiceNoAssets:
    def test_no_epf_assets_returns_zero(self, db):
        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )
        assert result == {"assets_checked": 0, "assets_updated": 0, "months_inserted": 0}

    def test_inactive_epf_asset_is_skipped(self, db):
        asset = _make_epf_asset(db, is_active=False)
        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )
        assert result["assets_checked"] == 0


class TestEPFAutoContribServiceUpToDate:
    def test_last_contribution_is_previous_month_no_fill(self, db):
        """Last contribution = Feb 2026, today = Mar 2026 → nothing to fill."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 2, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 2, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 2, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )
        assert result["months_inserted"] == 0

    def test_last_contribution_is_current_month_no_fill(self, db):
        """Last contribution = Mar 2026, today = Mar 2026 → nothing to fill."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 3, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 3, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 3, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )
        assert result["months_inserted"] == 0

    def test_no_contributions_at_all_skips_asset(self, db):
        """EPF asset with no prior contributions → skip."""
        _make_epf_asset(db)
        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )
        assert result["months_inserted"] == 0
        assert result["assets_updated"] == 0


class TestEPFAutoContribServiceFillsMissingMonths:
    def test_fills_one_missing_month(self, db):
        """Last = Jan 2026, today = Mar 2026 → fills Feb 2026."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )

        assert result["months_inserted"] == 1
        assert result["assets_updated"] == 1
        feb_txns = _contributions_for_month(db, asset.id, 2026, 2)
        assert len(feb_txns) == 3

    def test_fills_multiple_missing_months(self, db):
        """Last = Nov 2025, today = Mar 2026 → fills Dec 2025, Jan, Feb 2026."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2025, 11, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2025, 11, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2025, 11, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )

        assert result["months_inserted"] == 3
        for year, month in [(2025, 12), (2026, 1), (2026, 2)]:
            assert len(_contributions_for_month(db, asset.id, year, month)) == 3

    def test_fills_across_year_boundary(self, db):
        """Last = Dec 2025, today = Feb 2026 → fills Jan 2026."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2025, 12, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2025, 12, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2025, 12, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 2, 15)
        )

        assert result["months_inserted"] == 1
        jan_txns = _contributions_for_month(db, asset.id, 2026, 1)
        assert len(jan_txns) == 3

    def test_today_is_january_fills_correctly(self, db):
        """Today = Jan 15 2026 → fill_up_to = Dec 2025. Last = Nov 2025 → fills Dec 2025."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2025, 11, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2025, 11, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2025, 11, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 1, 15)
        )

        assert result["months_inserted"] == 1
        dec_txns = _contributions_for_month(db, asset.id, 2025, 12)
        assert len(dec_txns) == 3


class TestEPFAutoContribServiceAmounts:
    def test_inserted_amounts_match_last_contribution(self, db):
        """Filled months use the same paise amounts as the reference month."""
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        EPFAutoContribService(db).backfill_missing_contributions(today=date(2026, 3, 25))

        feb_txns = {t.notes: t for t in _contributions_for_month(db, asset.id, 2026, 2)}
        assert feb_txns["Employee Share"].amount_inr == -500000
        assert feb_txns["Employer Share"].amount_inr == -375000
        assert feb_txns["Pension Contribution (EPS)"].amount_inr == -125000

    def test_inserted_txn_date_is_last_day_of_month(self, db):
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        EPFAutoContribService(db).backfill_missing_contributions(today=date(2026, 3, 25))

        feb_txns = _contributions_for_month(db, asset.id, 2026, 2)
        for txn in feb_txns:
            assert txn.date == date(2026, 2, 28)  # Feb 2026 has 28 days

    def test_inserted_txn_ids_are_stable_and_match_cli_format(self, db):
        """txn_ids must match CLI/parser convention to prevent cross-source duplicates."""
        asset = _make_epf_asset(db, identifier="AB/1234/567")
        _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        EPFAutoContribService(db).backfill_missing_contributions(today=date(2026, 3, 25))

        expected_emp = _epf_txn_id("AB/1234/567", "CONTRIB_EMP", "022026", 500000)
        expected_er = _epf_txn_id("AB/1234/567", "CONTRIB_ER", "022026", 375000)
        expected_eps = _epf_txn_id("AB/1234/567", "CONTRIB_EPS", "022026", 125000)

        from app.repositories.transaction_repo import TransactionRepository
        txn_repo = TransactionRepository(db)
        assert txn_repo.get_by_txn_id(expected_emp) is not None
        assert txn_repo.get_by_txn_id(expected_er) is not None
        assert txn_repo.get_by_txn_id(expected_eps) is not None


class TestEPFAutoContribServiceIdempotency:
    def test_running_twice_does_not_create_duplicates(self, db):
        asset = _make_epf_asset(db)
        _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
        _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
        _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        svc = EPFAutoContribService(db)
        svc.backfill_missing_contributions(today=date(2026, 3, 25))
        result2 = svc.backfill_missing_contributions(today=date(2026, 3, 25))

        assert result2["months_inserted"] == 0
        # Feb 2026 should have exactly 3 transactions
        feb_txns = _contributions_for_month(db, asset.id, 2026, 2)
        assert len(feb_txns) == 3


class TestEPFAutoContribServiceMultipleAssets:
    def test_fills_all_epf_assets_independently(self, db):
        asset1 = _make_epf_asset(db, "EPF A", identifier="AA/0001/111")
        asset2 = _make_epf_asset(db, "EPF B", identifier="BB/0002/222")

        for asset in [asset1, asset2]:
            _add_contribution(db, asset.id, 2026, 1, "Employee Share", -500000)
            _add_contribution(db, asset.id, 2026, 1, "Employer Share", -375000)
            _add_contribution(db, asset.id, 2026, 1, "Pension Contribution (EPS)", -125000)

        result = EPFAutoContribService(db).backfill_missing_contributions(
            today=date(2026, 3, 25)
        )

        assert result["assets_checked"] == 2
        assert result["assets_updated"] == 2
        assert result["months_inserted"] == 2
