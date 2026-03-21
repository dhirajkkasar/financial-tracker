import pytest
from pathlib import Path
from app.importers.cas_parser import CASImporter

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestCASImporter:
    @pytest.fixture
    def importer(self):
        return CASImporter()

    @pytest.fixture
    def cas_bytes(self):
        return (FIXTURES / "test_cas.pdf").read_bytes()

    def test_parse_extracts_transactions(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        assert len(result.errors) == 0
        assert len(result.transactions) > 0

    def test_parse_extracts_isin(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        # At least some transactions should have ISIN
        with_isin = [t for t in result.transactions if t.isin]
        assert len(with_isin) > 0
        # Verify ISIN format (starts with INF for Indian MF)
        assert all(t.isin.startswith("INF") for t in with_isin)

    def test_parse_maps_sip_purchase(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        sips = [t for t in result.transactions if t.txn_type == "SIP"]
        assert len(sips) > 0
        for s in sips:
            assert s.amount_inr < 0  # outflow

    def test_parse_maps_purchase_to_buy(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        buys = [t for t in result.transactions if t.txn_type == "BUY"]
        # The Kotak Small Cap fund has "Purchase (Continuous Offer)" rows
        assert len(buys) > 0

    def test_parse_skips_stamp_duty_rows(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        stamp = [t for t in result.transactions if "Stamp Duty" in (t.notes or "")]
        assert len(stamp) == 0

    def test_parse_skips_no_transaction_schemes(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        # Schemes with "No transactions during this statement period" should produce 0 txns
        scheme_names = set(t.asset_name for t in result.transactions)
        # At minimum, we should NOT have Aditya Birla entries
        assert not any("Aditya Birla" in name for name in scheme_names)

    def test_txn_id_uses_folio_isin_not_db_id(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        for t in result.transactions:
            assert t.txn_id.startswith("cas_")
            # Should be hash-based, not integer DB ID
            assert len(t.txn_id) > 10

    def test_txn_id_stable_across_reparses(self, importer, cas_bytes):
        result1 = importer.parse(cas_bytes)
        result2 = importer.parse(cas_bytes)
        ids1 = sorted(t.txn_id for t in result1.transactions)
        ids2 = sorted(t.txn_id for t in result2.transactions)
        assert ids1 == ids2

    def test_all_txn_ids_unique(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        ids = [t.txn_id for t in result.transactions]
        assert len(ids) == len(set(ids))

    def test_asset_type_is_mf(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        assert all(t.asset_type == "MF" for t in result.transactions)

    def test_source_is_cas(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        assert result.source == "cas"
        assert all(t.source == "cas" for t in result.transactions)

    # --- Snapshot extraction tests ---

    def test_parse_extracts_snapshots(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        assert len(result.snapshots) > 0

    def test_all_snapshots_have_isin(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        assert all(s.isin for s in result.snapshots)

    def test_snapshot_fields_for_active_fund(self, importer, cas_bytes):
        # HDFC Multi Cap: Closing Unit Balance: 17,292.257 NAV on 18-Mar-2026: INR 18.505
        # Total Cost Value: 340,000.00  Market Value on 18-Mar-2026: INR 319,993.22
        result = importer.parse(cas_bytes)
        hdfc = next((s for s in result.snapshots if "HDFC Multi Cap" in s.asset_name), None)
        assert hdfc is not None
        assert abs(hdfc.closing_units - 17292.257) < 0.001
        assert abs(hdfc.nav_price_inr - 18.505) < 0.001
        assert abs(hdfc.market_value_inr - 319993.22) < 0.01
        assert abs(hdfc.total_cost_inr - 340000.00) < 0.01

    def test_snapshot_fields_for_parag_parikh(self, importer, cas_bytes):
        # Parag Parikh Flexi Cap: 26,580.939 units, NAV 89.3756, cost 1,655,390.87, mktval 2,375,687.37
        result = importer.parse(cas_bytes)
        pp = next((s for s in result.snapshots if "Parag Parikh Flexi Cap" in s.asset_name), None)
        assert pp is not None
        assert abs(pp.closing_units - 26580.939) < 0.001
        assert abs(pp.nav_price_inr - 89.3756) < 0.0001
        assert abs(pp.market_value_inr - 2375687.37) < 0.01
        assert abs(pp.total_cost_inr - 1655390.87) < 0.01

    def test_snapshot_zero_units_for_redeemed_fund(self, importer, cas_bytes):
        # Aditya Birla, HDFC ELSS, etc. all have closing_units = 0
        result = importer.parse(cas_bytes)
        redeemed = [s for s in result.snapshots if s.closing_units == 0.0]
        assert len(redeemed) > 0

    def test_snapshot_isin_matches_fund_isin(self, importer, cas_bytes):
        result = importer.parse(cas_bytes)
        # Parag Parikh Flexi Cap ISIN
        pp = next((s for s in result.snapshots if "Parag Parikh Flexi Cap" in s.asset_name), None)
        assert pp is not None
        assert pp.isin == "INF879O01027"

    def test_snapshot_date_parsed(self, importer, cas_bytes):
        from datetime import date
        result = importer.parse(cas_bytes)
        # Most snapshots in this CAS are dated 18-Mar-2026
        dates = {s.date for s in result.snapshots if s.closing_units > 0}
        assert date(2026, 3, 18) in dates
