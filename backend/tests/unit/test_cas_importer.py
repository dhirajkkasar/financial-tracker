"""Unit tests for CAS importer — uses static fixture data, no PDF I/O."""
from tests.fixtures_data import PARSED_CAS


class TestCASImporter:
    def test_parse_extracts_transactions(self):
        assert len(PARSED_CAS.errors) == 0
        assert len(PARSED_CAS.transactions) > 0

    def test_parse_extracts_isin(self):
        with_isin = [t for t in PARSED_CAS.transactions if t.isin]
        assert len(with_isin) > 0
        assert all(t.isin.startswith("INF") for t in with_isin)

    def test_parse_maps_sip_purchase(self):
        sips = [t for t in PARSED_CAS.transactions if t.txn_type == "SIP"]
        assert len(sips) > 0
        for s in sips:
            assert s.amount_inr < 0

    def test_parse_maps_purchase_to_buy(self):
        buys = [t for t in PARSED_CAS.transactions if t.txn_type == "BUY"]
        assert len(buys) > 0

    def test_parse_skips_stamp_duty_rows(self):
        stamp = [t for t in PARSED_CAS.transactions if "Stamp Duty" in (t.notes or "")]
        assert len(stamp) == 0

    def test_parse_skips_no_transaction_schemes(self):
        scheme_names = set(t.asset_name for t in PARSED_CAS.transactions)
        assert not any("Aditya Birla" in name for name in scheme_names)

    def test_txn_id_uses_folio_isin_not_db_id(self):
        for t in PARSED_CAS.transactions:
            assert t.txn_id.startswith("cas_")
            assert len(t.txn_id) > 10

    # test_txn_id_stable_across_reparses removed: covered by tests/smoke/test_cas_smoke.py

    def test_all_txn_ids_unique(self):
        ids = [t.txn_id for t in PARSED_CAS.transactions]
        assert len(ids) == len(set(ids))

    def test_asset_type_is_mf(self):
        assert all(t.asset_type == "MF" for t in PARSED_CAS.transactions)

    def test_source_is_cas(self):
        assert PARSED_CAS.source == "cas"
        assert all(t.source == "cas" for t in PARSED_CAS.transactions)

    def test_parse_extracts_snapshots(self):
        assert len(PARSED_CAS.snapshots) > 0

    def test_all_snapshots_have_isin(self):
        assert all(s.isin for s in PARSED_CAS.snapshots)

    def test_snapshot_fields_for_active_fund(self):
        hdfc = next((s for s in PARSED_CAS.snapshots if "HDFC Multi Cap" in s.asset_name), None)
        assert hdfc is not None
        assert abs(hdfc.closing_units - 17292.257) < 0.001
        assert abs(hdfc.nav_price_inr - 18.505) < 0.001
        assert abs(hdfc.market_value_inr - 319993.22) < 0.01
        assert abs(hdfc.total_cost_inr - 340000.00) < 0.01

    def test_snapshot_fields_for_parag_parikh(self):
        pp = next((s for s in PARSED_CAS.snapshots if "Parag Parikh Flexi Cap" in s.asset_name), None)
        assert pp is not None
        assert abs(pp.closing_units - 26580.939) < 0.001
        assert abs(pp.nav_price_inr - 89.3756) < 0.0001
        assert abs(pp.market_value_inr - 2375687.37) < 0.01
        assert abs(pp.total_cost_inr - 1655390.87) < 0.01

    def test_snapshot_zero_units_for_redeemed_fund(self):
        redeemed = [s for s in PARSED_CAS.snapshots if s.closing_units == 0.0]
        assert len(redeemed) > 0

    def test_snapshot_isin_matches_fund_isin(self):
        pp = next((s for s in PARSED_CAS.snapshots if "Parag Parikh Flexi Cap" in s.asset_name), None)
        assert pp is not None
        assert pp.isin == "INF879O01027"

    def test_snapshot_date_parsed(self):
        from datetime import date
        dates = {s.date for s in PARSED_CAS.snapshots if s.closing_units > 0}
        assert date(2026, 3, 18) in dates
