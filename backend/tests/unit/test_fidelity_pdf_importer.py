import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_sample_pdf_bytes() -> bytes:
    """Return the real Fidelity PDF fixture bytes for testing."""
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if path.exists():
        return path.read_bytes()
    pytest.skip("fidelity_sale_sample.pdf fixture not available")


class TestFidelityPDFImporter:
    RATES = {"2025-03": 86.0, "2025-09": 84.5}

    def _parse(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        return FidelityPDFImporter(exchange_rates=self.RATES).parse(data, "fidelity_sale.pdf")

    def test_parse_returns_two_transactions(self):
        result = self._parse()
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_parse_sell_transaction_type(self):
        txn = self._parse().transactions[0]
        assert txn.txn_type == "SELL"
        assert txn.asset_type == "STOCK_US"

    def test_parse_ticker_is_amzn(self):
        txn = self._parse().transactions[0]
        assert txn.asset_name == "AMZN"
        assert txn.asset_identifier == "AMZN"

    def test_parse_first_sale_date(self):
        txn = self._parse().transactions[0]
        assert txn.date == date(2025, 3, 17)

    def test_parse_first_sale_units(self):
        txn = self._parse().transactions[0]
        assert txn.units == pytest.approx(36.0)

    def test_parse_first_sale_amount_inr_positive_inflow(self):
        # proceeds = $7,070.24, rate = 86.0 → +608,040.64 INR
        txn = self._parse().transactions[0]
        assert txn.amount_inr == pytest.approx(7070.24 * 86.0, rel=1e-4)
        assert txn.amount_inr > 0  # SELL = inflow

    def test_parse_forex_rate_stored(self):
        txn = self._parse().transactions[0]
        assert txn.forex_rate == pytest.approx(86.0)

    def test_parse_notes_tag_tax_cover(self):
        txn = self._parse().transactions[0]
        assert "Tax cover sale" in (txn.notes or "")

    def test_parse_txn_id_is_stable(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        imp = FidelityPDFImporter(exchange_rates=self.RATES)
        id1 = imp.parse(data, "f.pdf").transactions[0].txn_id
        id2 = imp.parse(data, "f.pdf").transactions[0].txn_id
        assert id1 == id2
        assert id1.startswith("fidelity_sale_")

    def test_parse_txn_ids_are_unique(self):
        txns = self._parse().transactions
        ids = [t.txn_id for t in txns]
        assert len(ids) == len(set(ids))

    def test_extract_required_month_years(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        months = FidelityPDFImporter.extract_required_month_years(data)
        assert "2025-03" in months
        assert "2025-09" in months

    def test_missing_rate_adds_error(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        result = FidelityPDFImporter(exchange_rates={"2025-03": 86.0}).parse(data, "f.pdf")
        # 2025-09 row should error
        assert any("2025-09" in e for e in result.errors)

class TestFidelityPDFImporterValidation:
    """Test post-parse validation of Fidelity PDF importer."""

    def _load_data(self):
        path = FIXTURES / "fidelity_sale_sample.pdf"
        if path.exists():
            return path.read_bytes()
        pytest.skip("fidelity_sale_sample.pdf fixture not available")

    def test_validate_with_valid_exchange_rates(self):
        """Validation passes when exchange_rates JSON is valid and complete."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data, "fidelity_sale.pdf")
        
        # Valid exchange_rates JSON string
        user_inputs = '{"2025-03": 86.0, "2025-09": 84.5}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_invalid_json(self):
        """Validation fails when exchange_rates is not valid JSON."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data, "fidelity_sale.pdf")
        
        # Invalid JSON
        user_inputs = '{invalid json}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "valid JSON" in validation_result.errors[0]

    def test_validate_with_non_numeric_values(self):
        """Validation fails when exchange_rates values are not numeric."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data, "fidelity_sale.pdf")
        
        # Non-numeric values
        user_inputs = '{"2025-03": "not_a_number"}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "numbers" in validation_result.errors[0]

    def test_validate_with_missing_months(self):
        """Validation fails when required months are missing from exchange_rates."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data, "fidelity_sale.pdf")
        
        # Missing 2025-09
        user_inputs = '{"2025-03": 86.0}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "Missing exchange_rates" in validation_result.errors[0]
        assert "2025-09" in validation_result.errors[0]
        assert "2025-03" in validation_result.required_inputs.get("required_months", [])
        assert "2025-09" in validation_result.required_inputs.get("required_months", [])

    def test_validate_with_no_transactions(self):
        """Validation passes when there are no transactions and no exchange_rates."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        from app.importers.base import ImportResult
        result = ImportResult(source="fidelity_sale", transactions=[])
        
        validation_result = FidelityPDFImporter().validate(result, user_inputs=None)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_no_user_inputs_but_transactions(self):
        """Validation fails when there are transactions but no exchange_rates provided."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data, "fidelity_sale.pdf")
        
        # No user_inputs provided
        validation_result = FidelityPDFImporter().validate(result, user_inputs=None)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "exchange_rates is required" in validation_result.errors[0]