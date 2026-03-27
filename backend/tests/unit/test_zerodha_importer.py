import pytest
from pathlib import Path
from app.importers.zerodha_importer import ZerodhaImporter

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestZerodhaImporter:
    @pytest.fixture
    def importer(self):
        return ZerodhaImporter()

    @pytest.fixture
    def tradebook_bytes(self):
        return (FIXTURES / "tradebook-EQ-2023.csv").read_bytes()

    def test_parse_returns_correct_transaction_count(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        assert len(result.errors) == 0
        assert len(result.transactions) == 5

    def test_parse_maps_buy_correctly(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        # First row: TCS buy 3 @ 3427
        tcs = result.transactions[0]
        assert tcs.asset_name == "TCS"
        assert tcs.isin == "INE467B01029"
        assert tcs.txn_type == "BUY"
        assert tcs.units == 3.0
        assert tcs.price_per_unit == 3427.0
        assert tcs.amount_inr == -10281.0  # negative = outflow = 3*3427
        assert tcs.asset_type == "STOCK_IN"

    def test_parse_maps_sell_correctly(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        # Row 4 (index 3): ADANIENT sell 1 @ 3213
        sells = [t for t in result.transactions if t.txn_type == "SELL"]
        assert len(sells) > 0
        adani = sells[0]
        assert adani.asset_name == "ADANIENT"
        assert adani.txn_type == "SELL"
        assert adani.amount_inr > 0  # positive = inflow

    def test_uses_native_trade_id_as_txn_id(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        tcs = result.transactions[0]
        assert tcs.txn_id == "zerodha_10000001"  # prefixed with source

    def test_txn_id_stable_across_reparses(self, importer, tradebook_bytes):
        result1 = importer.parse(tradebook_bytes)
        result2 = importer.parse(tradebook_bytes)
        ids1 = [t.txn_id for t in result1.transactions]
        ids2 = [t.txn_id for t in result2.transactions]
        assert ids1 == ids2

    def test_all_txn_ids_unique(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        ids = [t.txn_id for t in result.transactions]
        assert len(ids) == len(set(ids))

    def test_source_is_zerodha(self, importer, tradebook_bytes):
        result = importer.parse(tradebook_bytes)
        assert result.source == "zerodha"
        assert all(t.source == "zerodha" for t in result.transactions)
