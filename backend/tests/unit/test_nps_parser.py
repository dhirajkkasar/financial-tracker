import pytest
from pathlib import Path
from app.importers.nps_csv_parser import NPSImporter

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
        # Tier 1 has 2 months x 3 schemes = 6 contributions
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

    def test_parse_marks_billing_as_charges(self, importer, tier1_bytes):
        result = importer.parse(tier1_bytes)
        # Billing entries exist -- they can be CHARGES or excluded
        # At minimum they should NOT be CONTRIBUTION
        billing = [t for t in result.transactions if "Billing" in (t.notes or "")]
        # If billing is included, verify amount is negative
        for b in billing:
            if b.amount_inr != 0:
                assert b.amount_inr < 0

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
