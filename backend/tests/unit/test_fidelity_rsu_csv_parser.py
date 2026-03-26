import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestFidelityRSUImporter:
    RATES = {"2025-03": 86.5, "2024-09": 83.8}

    def test_parse_returns_correct_transaction_count(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_parse_vest_transaction_fields(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]

        assert txn.asset_name == "AMZN"
        assert txn.asset_identifier == "AMZN"
        assert txn.asset_type == "STOCK_US"
        assert txn.txn_type == "VEST"
        assert txn.date == date(2025, 3, 17)
        assert txn.units == pytest.approx(68.0)
        assert txn.price_per_unit == pytest.approx(196.40)
        assert txn.forex_rate == pytest.approx(86.5)

    def test_parse_amount_inr_is_negative_outflow(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        # cost_basis=13355.28, rate=86.5 → -1_155_231.72
        assert txn.amount_inr == pytest.approx(-(13355.28 * 86.5), rel=1e-4)

    def test_parse_txn_id_is_stable(self):
        """Same row imported twice produces the same txn_id."""
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        imp = FidelityRSUImporter(exchange_rates=self.RATES)
        id1 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        id2 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        assert id1 == id2
        assert id1.startswith("fidelity_rsu_")

    def test_parse_txn_id_differs_by_row(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txns = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions
        assert txns[0].txn_id != txns[1].txn_id

    def test_extract_required_month_years(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        months = FidelityRSUImporter.extract_required_month_years(data)
        assert months == ["2024-09", "2025-03"]

    def test_missing_exchange_rate_adds_error(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        # Only provide one rate — second row should error
        result = FidelityRSUImporter(exchange_rates={"2025-03": 86.5}).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 1
        assert len(result.errors) == 1
        assert "2024-09" in result.errors[0]

    def test_parse_ticker_from_filename(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        market, ticker = FidelityRSUImporter._parse_ticker_from_filename("NASDAQ_AMZN.csv")
        assert market == "NASDAQ"
        assert ticker == "AMZN"

    def test_parse_ticker_uppercase(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        _, ticker = FidelityRSUImporter._parse_ticker_from_filename("NYSE_MSFT.csv")
        assert ticker == "MSFT"

    def test_parse_notes_includes_market(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        assert "NASDAQ" in (txn.notes or "")
