import pytest
from pathlib import Path
from app.importers.nps_csv_importer import NPSImporter

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestNPSImporter:
    @pytest.fixture
    def importer(self):
        return NPSImporter()

    @pytest.fixture
    def tier1_bytes(self):
        return (FIXTURES / "nps_tier_1.csv").read_bytes()

    @pytest.fixture
    def tier2_bytes(self):
        return (FIXTURES / "nps_tier2.csv").read_bytes()

    def test_parse_tier1_extracts_contributions(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        assert len(result.errors) == 0
        contributions = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        # Tier 1 has 2 months x 3 schemes = 6 contributions (billing row is not CONTRIBUTION)
        assert len(contributions) == 6

    def test_parse_creates_asset_per_scheme(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        scheme_names = set(t.asset_name for t in result.transactions)
        # 3 schemes in tier 1
        assert len(scheme_names) == 3

    def test_parse_extracts_tier_label(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        # All transactions should reference Tier I
        assert all("TIER I" in t.asset_name or "Tier I" in (t.notes or "") for t in result.transactions)

    def test_billing_transactions_are_included(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        billing = [t for t in result.transactions if t.txn_type == "BILLING"]
        # Billing row exists in the fixture
        assert len(billing) >= 1
        # Billing amounts are negative (charges)
        for b in billing:
            assert b.amount_inr < 0

    def test_billing_not_skipped(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        billing = [t for t in result.transactions if t.txn_type == "BILLING"]
        assert len(billing) >= 1, "Billing transactions should appear in result.transactions"

    def test_parse_skips_opening_closing_balance(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        descriptions = [t.notes for t in result.transactions if t.notes]
        assert not any("Opening balance" in d for d in descriptions)
        assert not any("Closing Balance" in d for d in descriptions)

    def test_txn_id_is_hash_based(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        # No native txn ref -- all txn_ids should be sha256 hashes prefixed with nps_
        assert all(t.txn_id.startswith("nps_") for t in result.transactions)
        # SHA-256 hex = 64 chars + "nps_" prefix = 68
        assert all(len(t.txn_id) >= 68 for t in result.transactions)

    def test_txn_id_stable_across_reparses(self, importer, tier1_bytes):
        result1 = importer.parse(tier1_bytes)
        result2 = importer.parse(tier1_bytes)
        ids1 = [t.txn_id for t in result1.transactions]
        ids2 = [t.txn_id for t in result2.transactions]
        assert ids1 == ids2

    def test_parse_tier2_with_no_transactions(self, importer, tier2_bytes):
        result = importer.parse(tier2_bytes)
        # Tier 2 has only opening/closing balances, no actual contributions
        contributions = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        assert len(contributions) == 0

    def test_contribution_amount_is_negative(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        contributions = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        for c in contributions:
            assert c.amount_inr < 0  # outflow

    def test_all_txn_ids_unique(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        ids = [t.txn_id for t in result.transactions]
        assert len(ids) == len(set(ids))

    def test_notes_contain_tier_label(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        for txn in result.transactions:
            assert txn.notes is not None
            assert txn.notes.startswith("Tier I") or txn.notes.startswith("Tier II")

    def test_contribution_notes_contain_month_year(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        contributions = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        # e.g. "Tier I | Mar 2025"
        for c in contributions:
            assert "|" in c.notes, f"Notes should contain '|' separator, got: {c.notes}"
            # Should contain a month abbreviation or year
            assert any(
                month in c.notes
                for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            ), f"Notes should contain month abbreviation, got: {c.notes}"

    def test_voluntary_contribution_notes(self, importer):
        """Voluntary contributions should have 'Voluntary Contribution' in notes."""
        csv_content = b"""NPS Transaction Statement for Tier I Account

Subscriber Details

PRAN,'330333338391

Transaction Details


SBI PENSION FUND SCHEME C - TIER I
Date,Description,Amount (in Rs),NAV,Units
01-Jan-2022,Opening balance,,,100.0000
15-Jan-2022,By Voluntary Contributions,5000.00,40.0000,125.0000
31-Dec-2022,Closing Balance,,,225.0000
"""
        result = importer.parse(csv_content)
        voluntary = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        assert len(voluntary) == 1
        assert "Voluntary Contribution" in voluntary[0].notes
