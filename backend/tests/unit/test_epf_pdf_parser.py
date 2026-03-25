"""Unit tests for EPF PDF parser — uses static fixture data, no PDF I/O."""
from tests.fixtures_data import PARSED_EPF


class TestEPFPDFParser:
    def test_parse_returns_import_result(self):
        assert PARSED_EPF.source == "epf_pdf"

    def test_parse_extracts_member_id(self):
        assert PARSED_EPF.member_id == "BGBNG00268580000306940"

    def test_parse_extracts_establishment_name(self):
        assert PARSED_EPF.establishment_name == "AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED"

    def test_parse_extracts_print_date(self):
        from datetime import date
        assert PARSED_EPF.print_date == date(2026, 3, 24)

    def test_parse_has_no_errors(self):
        assert len(PARSED_EPF.errors) == 0

    def test_parse_transactions_not_empty(self):
        assert len(PARSED_EPF.transactions) > 0

    def test_parse_all_transactions_have_epf_identifier(self):
        for txn in PARSED_EPF.transactions:
            assert txn.asset_identifier == "BGBNG00268580000306940"
            assert "AMAZON DEVELOPMENT CENTRE" in txn.asset_name

    def test_parse_all_transactions_have_epf_asset_type(self):
        for txn in PARSED_EPF.transactions:
            assert txn.asset_type == "EPF"

    # --- Contribution tests ---

    def test_parse_has_employee_share_contributions(self):
        emp_txns = [t for t in PARSED_EPF.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Employee Share"]
        assert len(emp_txns) > 0

    def test_parse_has_employer_share_contributions(self):
        er_txns = [t for t in PARSED_EPF.transactions
                   if t.txn_type == "CONTRIBUTION" and t.notes == "Employer Share"]
        assert len(er_txns) > 0

    def test_parse_has_eps_contributions(self):
        eps_txns = [t for t in PARSED_EPF.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Pension Contribution (EPS)"]
        assert len(eps_txns) > 0

    def test_parse_contribution_amounts_are_negative(self):
        contribution_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "CONTRIBUTION"]
        for txn in contribution_txns:
            assert txn.amount_inr <= 0

    # --- Interest tests (3 separate transactions per year) ---

    def test_parse_has_three_interest_types_per_year(self):
        """When an interest row is present, 3 INTEREST transactions are created."""
        interest_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "INTEREST"]
        assert len(interest_txns) > 0
        # Check we have all 3 notes types
        notes = {t.notes for t in interest_txns}
        assert "Employee Interest" in notes
        assert "Employer Interest" in notes
        assert "EPS Interest" in notes

    def test_parse_employee_interest_is_positive(self):
        emp_int = [t for t in PARSED_EPF.transactions
                   if t.txn_type == "INTEREST" and t.notes == "Employee Interest"]
        assert len(emp_int) > 0
        for t in emp_int:
            assert t.amount_inr >= 0

    def test_parse_employer_interest_is_positive(self):
        er_int = [t for t in PARSED_EPF.transactions
                  if t.txn_type == "INTEREST" and t.notes == "Employer Interest"]
        assert len(er_int) > 0
        for t in er_int:
            assert t.amount_inr >= 0

    def test_parse_eps_interest_recorded_even_if_zero(self):
        """EPS interest is always recorded when an Int. Updated upto row is present."""
        eps_int = [t for t in PARSED_EPF.transactions
                   if t.txn_type == "INTEREST" and t.notes == "EPS Interest"]
        assert len(eps_int) > 0  # present even if amount is 0

    # --- txn_id uniqueness ---

    def test_parse_all_txn_ids_unique(self):
        ids = [t.txn_id for t in PARSED_EPF.transactions]
        assert len(ids) == len(set(ids))

    # --- net balance ---

    def test_parse_net_balance_is_zero(self):
        """EPF returns are computed from transactions, not a stored balance."""
        assert PARSED_EPF.net_balance_inr == 0.0
