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
