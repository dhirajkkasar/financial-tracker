"""
Unit tests for EPF PDF parser (TDD — written first, must be RED before implementation).
"""
import pytest
from pathlib import Path
from app.importers.epf_pdf_parser import EPFPDFParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestEPFPDFParser:
    @pytest.fixture
    def parser(self):
        return EPFPDFParser()

    @pytest.fixture
    def epf_pdf_bytes(self):
        return (FIXTURES / "PYKRP00192140000152747.pdf").read_bytes()

    def test_parse_returns_import_result(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        assert result.source == "epf_pdf"

    def test_parse_extracts_member_id(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        assert result.member_id == "PYKRP00192140000152747"

    def test_parse_extracts_establishment_name(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        assert result.establishment_name == "IBM INDIA PVT LTD"

    def test_parse_extracts_print_date(self, parser, epf_pdf_bytes):
        from datetime import date
        result = parser.parse(epf_pdf_bytes)
        assert result.print_date == date(2018, 11, 27)

    def test_parse_has_no_errors(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        assert len(result.errors) == 0

    def test_parse_transactions_not_empty(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        assert len(result.transactions) > 0

    def test_parse_epf_transactions_have_member_id_as_identifier(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        epf_txns = [t for t in result.transactions if t.asset_identifier == "PYKRP00192140000152747"]
        assert len(epf_txns) > 0

    def test_parse_eps_transactions_have_eps_identifier(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        eps_txns = [t for t in result.transactions if t.asset_identifier == "PYKRP00192140000152747_EPS"]
        assert len(eps_txns) > 0

    def test_parse_epf_asset_type(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        for txn in result.transactions:
            assert txn.asset_type == "EPF"

    def test_parse_contribution_types(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        contribution_txns = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        assert len(contribution_txns) > 0

    def test_parse_interest_transactions(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        interest_txns = [t for t in result.transactions if t.txn_type == "INTEREST"]
        assert len(interest_txns) > 0

    def test_parse_transfer_transaction(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        transfer_txns = [t for t in result.transactions if t.txn_type == "TRANSFER"]
        # The "Claim: Against PARA 57(1)" row should be a TRANSFER
        assert len(transfer_txns) >= 1

    def test_parse_employee_share_notes(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        emp_txns = [t for t in result.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Employee Share"
                    and t.asset_identifier == "PYKRP00192140000152747"]
        assert len(emp_txns) > 0

    def test_parse_employer_share_notes(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        er_txns = [t for t in result.transactions
                   if t.txn_type == "CONTRIBUTION" and t.notes == "Employer Share"
                   and t.asset_identifier == "PYKRP00192140000152747"]
        assert len(er_txns) > 0

    def test_parse_pension_contribution_notes(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        eps_txns = [t for t in result.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Pension Contribution"
                    and t.asset_identifier == "PYKRP00192140000152747_EPS"]
        assert len(eps_txns) > 0

    def test_parse_contribution_amounts_are_negative(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        contribution_txns = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
        for txn in contribution_txns:
            assert txn.amount_inr < 0, f"Expected negative amount for CONTRIBUTION, got {txn.amount_inr}"

    def test_parse_interest_amounts_are_positive(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        interest_txns = [t for t in result.transactions if t.txn_type == "INTEREST"]
        for txn in interest_txns:
            assert txn.amount_inr > 0, f"Expected positive amount for INTEREST, got {txn.amount_inr}"

    def test_parse_transfer_amount_is_positive(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        transfer_txns = [t for t in result.transactions if t.txn_type == "TRANSFER"]
        for txn in transfer_txns:
            assert txn.amount_inr > 0, f"Expected positive amount for TRANSFER, got {txn.amount_inr}"

    def test_parse_all_txn_ids_unique(self, parser, epf_pdf_bytes):
        result = parser.parse(epf_pdf_bytes)
        ids = [t.txn_id for t in result.transactions]
        assert len(ids) == len(set(ids))

    def test_parse_txn_ids_stable_across_reparses(self, parser, epf_pdf_bytes):
        result1 = parser.parse(epf_pdf_bytes)
        result2 = parser.parse(epf_pdf_bytes)
        ids1 = sorted(t.txn_id for t in result1.transactions)
        ids2 = sorted(t.txn_id for t in result2.transactions)
        assert ids1 == ids2

    def test_parse_net_balance_is_zero(self, parser, epf_pdf_bytes):
        """Grand Total deposits == Grand Total withdrawals → net balance = 0."""
        result = parser.parse(epf_pdf_bytes)
        assert result.net_balance_inr == 0.0

    def test_parse_grand_total_deposits(self, parser, epf_pdf_bytes):
        """Grand Total employee deposit = 198371, employer deposit = 140204 (INR)."""
        result = parser.parse(epf_pdf_bytes)
        # Employee deposit total (in INR, from Grand Total row)
        assert result.grand_total_emp_deposit == 198371.0
        assert result.grand_total_er_deposit == 140204.0

    def test_parse_eps_identifier_in_transactions(self, parser, epf_pdf_bytes):
        """EPS transactions should have asset name containing establishment name."""
        result = parser.parse(epf_pdf_bytes)
        eps_txns = [t for t in result.transactions if t.asset_identifier == "PYKRP00192140000152747_EPS"]
        for txn in eps_txns:
            assert "IBM INDIA PVT LTD" in txn.asset_name
