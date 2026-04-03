import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestFidelityRSUImporter:
    RATES = {"2025-03": 86.5, "2024-09": 83.8}

    def test_parse_returns_correct_transaction_count(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_parse_vest_transaction_fields(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]

        assert txn.asset_name == "AMZN"
        assert txn.asset_identifier == "AMZN"
        assert txn.asset_type == "STOCK_US"
        assert txn.txn_type == "VEST"
        assert txn.date == date(2025, 3, 17)
        assert txn.units == pytest.approx(50.0)
        assert txn.price_per_unit == pytest.approx(200.00)
        assert txn.forex_rate == pytest.approx(86.5)

    def test_parse_amount_inr_is_negative_outflow(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        # cost_basis=10000.00, rate=86.5 → -865_000.00
        assert txn.amount_inr == pytest.approx(-(10000.00 * 86.5), rel=1e-4)

    def test_parse_txn_id_is_stable(self):
        """Same row imported twice produces the same txn_id."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        imp = FidelityRSUImporter(exchange_rates=self.RATES)
        id1 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        id2 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        assert id1 == id2
        assert id1.startswith("fidelity_rsu_")

    def test_parse_txn_id_differs_by_row(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txns = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions
        assert txns[0].txn_id != txns[1].txn_id

    def test_extract_required_month_years(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        months = FidelityRSUImporter.extract_required_month_years(data)
        assert months == ["2024-09", "2025-03"]

    def test_missing_exchange_rate_adds_error(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        # Only provide one rate — second row should error
        result = FidelityRSUImporter(exchange_rates={"2025-03": 86.5}).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 1
        assert len(result.errors) == 1
        assert "2024-09" in result.errors[0]

    def test_parse_ticker_from_filename(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        market, ticker = FidelityRSUImporter._parse_ticker_from_filename("NASDAQ_AMZN.csv")
        assert market == "NASDAQ"
        assert ticker == "AMZN"

    def test_parse_ticker_uppercase(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        _, ticker = FidelityRSUImporter._parse_ticker_from_filename("NYSE_MSFT.csv")
        assert ticker == "MSFT"

    def test_parse_notes_includes_market(self):
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        assert "NASDAQ" in (txn.notes or "")


class TestFidelityRSUImporterValidation:
    """Test post-parse validation of Fidelity RSU importer."""

    def test_validate_with_valid_exchange_rates(self):
        """Validation passes when exchange_rates JSON is valid and complete."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter().parse(data, "NASDAQ_AMZN.csv")
        
        # Valid exchange_rates JSON string
        user_inputs = '{"2025-03": 86.5, "2024-09": 83.8}'
        validation_result = FidelityRSUImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_invalid_json(self):
        """Validation fails when exchange_rates is not valid JSON."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter().parse(data, "NASDAQ_AMZN.csv")
        
        # Invalid JSON
        user_inputs = '{invalid json}'
        validation_result = FidelityRSUImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "valid JSON" in validation_result.errors[0]

    def test_validate_with_non_numeric_values(self):
        """Validation fails when exchange_rates values are not numeric."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter().parse(data, "NASDAQ_AMZN.csv")
        
        # Non-numeric values
        user_inputs = '{"2025-03": "abc"}'
        validation_result = FidelityRSUImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "numbers" in validation_result.errors[0]

    def test_validate_with_missing_months(self):
        """Validation fails when required months are missing from exchange_rates."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter().parse(data, "NASDAQ_AMZN.csv")
        
        # Missing 2024-09
        user_inputs = '{"2025-03": 86.5}'
        validation_result = FidelityRSUImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "Missing exchange_rates" in validation_result.errors[0]
        assert "2024-09" in validation_result.errors[0]
        assert validation_result.required_inputs["required_months"] == ["2024-09", "2025-03"]

    def test_validate_with_no_transactions(self):
        """Validation passes when there are no transactions and no exchange_rates."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        from app.importers.base import ImportResult
        result = ImportResult(source="fidelity_rsu", transactions=[])
        
        validation_result = FidelityRSUImporter().validate(result, user_inputs=None)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_no_user_inputs_but_transactions(self):
        """Validation fails when there are transactions but no exchange_rates provided."""
        from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter().parse(data, "NASDAQ_AMZN.csv")
        
        # No user_inputs provided
        validation_result = FidelityRSUImporter().validate(result, user_inputs=None)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "exchange_rates is required" in validation_result.errors[0]
