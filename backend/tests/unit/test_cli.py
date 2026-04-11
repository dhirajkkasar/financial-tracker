"""
Unit tests for backend/cli.py — all HTTP calls are mocked via requests_mock.
TDD: write failing tests first, then implement cli.py to make them pass.
"""
import sys
import pytest
import requests_mock as req_mock_module

# Make cli.py importable from backend root
sys.path.insert(0, "/Users/dhirajkasar/Documents/workspace/financial-tracker/backend")

import cli  # noqa: E402 — imported after sys.path patch


# ── helpers ──────────────────────────────────────────────────────────────────

ASSET_LIST = [
    {"id": 1, "name": "Venezia Flat", "asset_type": "REAL_ESTATE", "asset_class": "REAL_ESTATE", "is_active": True},
    {"id": 2, "name": "AMZN RSU",     "asset_type": "STOCK_US",    "asset_class": "EQUITY",      "is_active": True},
    {"id": 3, "name": "Digital Gold", "asset_type": "GOLD",         "asset_class": "GOLD",        "is_active": True},
    {"id": 4, "name": "HDFC FD",      "asset_type": "FD",           "asset_class": "DEBT",        "is_active": True},
]

BASE = "http://localhost:8000/api"


# ── fuzzy asset lookup ────────────────────────────────────────────────────────

class TestFindAsset:
    def test_exact_match(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        asset = cli.find_asset("Venezia Flat")
        assert asset["id"] == 1

    def test_fuzzy_match(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        asset = cli.find_asset("venezia")   # lowercase partial
        assert asset["id"] == 1

    def test_fuzzy_match_rsu(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        asset = cli.find_asset("Amazon RSU")
        assert asset["id"] == 2

    def test_no_match_exits(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        with pytest.raises(SystemExit):
            cli.find_asset("nonexistent xyz abc")


# ── import ppf ────────────────────────────────────────────────────────────────

class TestImportPPF:
    def test_calls_correct_endpoint(self, requests_mock, tmp_path):
        csv = tmp_path / "ppf.csv"
        csv.write_bytes(b"fake,csv,data")
        requests_mock.post(f"{BASE}/import/preview-file?source=ppf&format=csv&member_id=1", json={
            "preview_id": "p1", "new_count": 5, "duplicate_count": 0,
        })
        requests_mock.post(f"{BASE}/import/commit-file/p1", json={
            "inserted": 5, "skipped": 1, "valuation_created": True,
            "valuation_value": 150000.0, "valuation_date": "2026-03-25",
            "account_number": "32256576916", "errors": []
        })
        result = cli.cmd_import_ppf(str(csv), member_id=1)
        assert requests_mock.request_history[0].path == "/api/import/preview-file"
        assert result["inserted"] == 5

    def test_prints_summary(self, requests_mock, tmp_path, capsys):
        csv = tmp_path / "ppf.csv"
        csv.write_bytes(b"fake,csv,data")
        requests_mock.post(f"{BASE}/import/preview-file?source=ppf&format=csv&member_id=1", json={"preview_id": "p2", "new_count": 3, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/p2", json={
            "inserted": 3, "skipped": 0, "valuation_created": True,
            "valuation_value": 200000.0, "valuation_date": "2026-03-25",
            "account_number": "32256576916", "errors": []
        })
        cli.cmd_import_ppf(str(csv), member_id=1)
        out = capsys.readouterr().out
        assert "3 inserted" in out
        assert "0 skipped" in out

    def test_file_not_found_exits(self):
        with pytest.raises(SystemExit):
            cli.cmd_import_ppf("/nonexistent/path/ppf.csv", member_id=1)


# ── import epf ────────────────────────────────────────────────────────────────

class TestImportEPF:
    def test_calls_correct_endpoint(self, requests_mock, tmp_path):
        pdf = tmp_path / "epf.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        requests_mock.post(f"{BASE}/import/preview-file?source=epf&format=pdf&member_id=1", json={
            "preview_id": "e1", "new_count": 10, "duplicate_count": 0,
        })
        requests_mock.post(f"{BASE}/import/commit-file/e1", json={
            "inserted": 10, "skipped": 2,
            "eps_inserted": 5,  "eps_skipped": 1,
            "eps_asset_id": 7,  "asset_created": False,
            "epf_valuation_created": True, "epf_valuation_value": 500000.0,
            "errors": []
        })
        result = cli.cmd_import_epf(str(pdf), member_id=1)
        assert requests_mock.request_history[0].path == "/api/import/preview-file"
        assert result["inserted"] == 10

    def test_prints_summary(self, requests_mock, tmp_path, capsys):
        pdf = tmp_path / "epf.pdf"
        pdf.write_bytes(b"%PDF fake")
        requests_mock.post(f"{BASE}/import/preview-file?source=epf&format=pdf&member_id=1", json={"preview_id": "e2", "new_count": 8, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/e2", json={
            "inserted": 8, "skipped": 0,
            "eps_inserted": 4, "eps_skipped": 0,
            "eps_asset_id": 7, "asset_created": True,
            "epf_valuation_created": True, "epf_valuation_value": 300000.0,
            "errors": []
        })
        cli.cmd_import_epf(str(pdf), member_id=1)
        out = capsys.readouterr().out
        assert "8 inserted" in out


# ── import cas ────────────────────────────────────────────────────────────────

class TestImportCAS:
    def test_preview_then_commit(self, requests_mock, tmp_path):
        pdf = tmp_path / "cas.pdf"
        pdf.write_bytes(b"%PDF fake")
        requests_mock.post(f"{BASE}/import/preview-file?source=cas&format=pdf&member_id=1", json={"preview_id": "abc123", "transactions": [], "new_count": 12, "duplicate_count": 3})
        requests_mock.post(f"{BASE}/import/commit-file/abc123", json={"inserted": 12, "skipped": 3, "snapshot_count": 5})
        result = cli.cmd_import_cas(str(pdf), member_id=1)
        assert result["inserted"] == 12
        # ensure commit was called with correct preview_id
        assert requests_mock.request_history[-1].path == "/api/import/commit-file/abc123"

    def test_prints_summary(self, requests_mock, tmp_path, capsys):
        pdf = tmp_path / "cas.pdf"
        pdf.write_bytes(b"%PDF fake")
        requests_mock.post(f"{BASE}/import/preview-file?source=cas&format=pdf&member_id=1", json={"preview_id": "xyz", "transactions": [], "new_count": 7, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/xyz", json={"inserted": 7, "skipped": 0, "snapshot_count": 3})
        cli.cmd_import_cas(str(pdf), member_id=1)
        out = capsys.readouterr().out
        assert "7 inserted" in out


# ── import zerodha / groww / nps ─────────────────────────────────────────────

class TestImportBrokerCSV:
    def test_zerodha_calls_correct_broker_param(self, requests_mock, tmp_path):
        csv = tmp_path / "zerodha.csv"
        csv.write_text("header\n")
        requests_mock.post(f"{BASE}/import/preview-file?source=zerodha&format=csv&member_id=1", json={"preview_id": "z1", "transactions": [], "new_count": 5, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/z1", json={"inserted": 5, "skipped": 0, "snapshot_count": 0})
        cli.cmd_import_broker_csv(str(csv), broker="zerodha", member_id=1)
        assert requests_mock.request_history[0].qs["source"] == ["zerodha"]

    def test_groww_calls_correct_broker_param(self, requests_mock, tmp_path):
        csv = tmp_path / "groww.csv"
        csv.write_text("header\n")
        requests_mock.post(f"{BASE}/import/preview-file?source=groww&format=csv&member_id=1", json={"preview_id": "g1", "transactions": [], "new_count": 3, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/g1", json={"inserted": 3, "skipped": 0, "snapshot_count": 0})
        cli.cmd_import_broker_csv(str(csv), broker="groww", member_id=1)
        assert requests_mock.request_history[0].qs["source"] == ["groww"]

    def test_nps_calls_nps_csv_endpoint(self, requests_mock, tmp_path):
        csv = tmp_path / "nps.csv"
        csv.write_text("header\n")
        requests_mock.post(f"{BASE}/import/preview-file?source=nps&format=csv&member_id=1", json={"preview_id": "n1", "transactions": [], "new_count": 4, "duplicate_count": 0})
        requests_mock.post(f"{BASE}/import/commit-file/n1", json={"inserted": 4, "skipped": 0, "snapshot_count": 0})
        requests_mock.post(f"{BASE}/prices/refresh-all", json={"status": "ok"})
        cli.cmd_import_nps(str(csv), member_id=1)
        assert requests_mock.request_history[0].path == "/api/import/preview-file"


# ── add fd ────────────────────────────────────────────────────────────────────

class TestAddFD:
    def test_creates_asset_fd_detail_and_transaction(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 10, "name": "HDFC FD", "asset_type": "FD"})
        requests_mock.post(f"{BASE}/assets/10/fd-detail", json={"id": 1, "asset_id": 10})
        requests_mock.post(f"{BASE}/assets/10/transactions", json={"id": 1, "asset_id": 10, "type": "CONTRIBUTION"})

        cli.cmd_add_fd(
            name="HDFC FD", bank="HDFC",
            principal=500000.0, rate=7.1,
            start="2024-01-15", maturity="2025-01-15",
            compounding="QUARTERLY", member_id=1,
        )

        assert requests_mock.request_history[0].path == "/api/assets"
        assert requests_mock.request_history[1].path == "/api/assets/10/fd-detail"
        assert requests_mock.request_history[2].path == "/api/assets/10/transactions"

    def test_asset_payload(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 10, "name": "SBI FD", "asset_type": "FD"})
        requests_mock.post(f"{BASE}/assets/10/fd-detail", json={"id": 1, "asset_id": 10})
        requests_mock.post(f"{BASE}/assets/10/transactions", json={"id": 1, "asset_id": 10, "type": "CONTRIBUTION"})

        cli.cmd_add_fd("SBI FD", "SBI", 200000.0, 6.8, "2024-06-01", "2025-06-01", "MONTHLY", member_id=1)

        body = requests_mock.request_history[0].json()
        assert body["asset_type"] == "FD"
        assert body["asset_class"] == "DEBT"

    def test_fd_detail_payload(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 11, "name": "ICICI FD", "asset_type": "FD"})
        requests_mock.post(f"{BASE}/assets/11/fd-detail", json={"id": 2, "asset_id": 11})
        requests_mock.post(f"{BASE}/assets/11/transactions", json={"id": 2, "asset_id": 11, "type": "CONTRIBUTION"})

        cli.cmd_add_fd("ICICI FD", "ICICI", 300000.0, 7.5, "2024-03-01", "2025-03-01", "QUARTERLY", member_id=1)

        body = requests_mock.request_history[1].json()
        assert body["bank"] == "ICICI"
        assert body["principal_amount"] == 300000.0
        assert body["interest_rate_pct"] == 7.5
        assert body["compounding"] == "QUARTERLY"
        assert body["fd_type"] == "FD"

    def test_contribution_is_negative(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 12, "name": "Test FD", "asset_type": "FD"})
        requests_mock.post(f"{BASE}/assets/12/fd-detail", json={"id": 3, "asset_id": 12})
        requests_mock.post(f"{BASE}/assets/12/transactions", json={"id": 3, "asset_id": 12, "type": "CONTRIBUTION"})

        cli.cmd_add_fd("Test FD", "HDFC", 100000.0, 7.0, "2024-01-01", "2025-01-01", "QUARTERLY", member_id=1)

        body = requests_mock.request_history[2].json()
        assert body["amount_inr"] == -100000.0
        assert body["type"] == "CONTRIBUTION"


# ── add rd ────────────────────────────────────────────────────────────────────

class TestAddRD:
    def test_rd_fd_type_is_rd(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 20, "name": "SBI RD", "asset_type": "RD"})
        requests_mock.post(f"{BASE}/assets/20/fd-detail", json={"id": 5, "asset_id": 20})
        requests_mock.post(f"{BASE}/assets/20/transactions", json={"id": 5, "asset_id": 20, "type": "CONTRIBUTION"})

        cli.cmd_add_rd("SBI RD", "SBI", installment=10000.0, rate=6.5,
                       start="2024-01-01", maturity="2026-01-01", compounding="QUARTERLY", member_id=1)

        body = requests_mock.request_history[1].json()
        assert body["fd_type"] == "RD"
        assert body["principal_amount"] == 10000.0   # monthly installment

    def test_asset_type_is_rd(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 21, "name": "Post RD", "asset_type": "RD"})
        requests_mock.post(f"{BASE}/assets/21/fd-detail", json={"id": 6, "asset_id": 21})
        requests_mock.post(f"{BASE}/assets/21/transactions", json={"id": 6, "asset_id": 21, "type": "CONTRIBUTION"})

        cli.cmd_add_rd("Post RD", "India Post", 5000.0, 7.0, "2024-06-01", "2026-06-01", "QUARTERLY", member_id=1)

        body = requests_mock.request_history[0].json()
        assert body["asset_type"] == "RD"


# ── add real-estate ───────────────────────────────────────────────────────────

class TestAddRealEstate:
    def test_creates_asset_txn_and_valuation(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 30, "name": "Venezia Flat", "asset_type": "REAL_ESTATE"})
        requests_mock.post(f"{BASE}/assets/30/transactions", json={"id": 1, "asset_id": 30, "type": "CONTRIBUTION"})
        requests_mock.post(f"{BASE}/assets/30/valuations", json={"id": 1, "asset_id": 30})

        cli.cmd_add_real_estate(
            name="Venezia Flat",
            purchase_amount=7500000.0, purchase_date="2020-11-09",
            current_value=12000000.0, value_date="2024-01-01", member_id=1,
        )

        assert requests_mock.request_history[0].path == "/api/assets"
        assert requests_mock.request_history[1].path == "/api/assets/30/transactions"
        assert requests_mock.request_history[2].path == "/api/assets/30/valuations"

    def test_purchase_txn_is_negative(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 31, "name": "VTP Office", "asset_type": "REAL_ESTATE"})
        requests_mock.post(f"{BASE}/assets/31/transactions", json={"id": 2, "asset_id": 31, "type": "CONTRIBUTION"})
        requests_mock.post(f"{BASE}/assets/31/valuations", json={"id": 2, "asset_id": 31})

        cli.cmd_add_real_estate("VTP Office", 3000000.0, "2024-06-27", 3200000.0, "2025-01-01", member_id=1)

        txn_body = requests_mock.request_history[1].json()
        assert txn_body["amount_inr"] == -3000000.0
        assert txn_body["type"] == "CONTRIBUTION"

    def test_valuation_payload(self, requests_mock):
        requests_mock.post(f"{BASE}/assets", json={"id": 32, "name": "Land", "asset_type": "REAL_ESTATE"})
        requests_mock.post(f"{BASE}/assets/32/transactions", json={"id": 3, "asset_id": 32, "type": "CONTRIBUTION"})
        requests_mock.post(f"{BASE}/assets/32/valuations", json={"id": 3, "asset_id": 32})

        cli.cmd_add_real_estate("Land", 5000000.0, "2021-01-01", 6000000.0, "2025-01-01", member_id=1)

        val_body = requests_mock.request_history[2].json()
        assert val_body["value_inr"] == 6000000.0
        assert val_body["date"] == "2025-01-01"
        assert val_body["source"] == "manual"


# ── add gold / sgb ────────────────────────────────────────────────────────────

class TestAddGold:
    def test_creates_new_asset_and_buy_txn(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])   # no existing assets
        requests_mock.post(f"{BASE}/assets", json={"id": 40, "name": "Digital Gold", "asset_type": "GOLD"})
        requests_mock.post(f"{BASE}/assets/40/transactions", json={"id": 1, "asset_id": 40, "type": "BUY"})

        cli.cmd_add_gold("Digital Gold", date="2023-06-01", units=10.0, price=5800.0, member_id=1)

        assert requests_mock.request_history[1].path == "/api/assets"
        assert requests_mock.request_history[2].path == "/api/assets/40/transactions"

    def test_reuses_existing_asset(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[{"id": 3, "name": "Digital Gold", "asset_type": "GOLD", "asset_class": "GOLD", "is_active": True}])
        requests_mock.post(f"{BASE}/assets/3/transactions", json={"id": 2, "asset_id": 3, "type": "BUY"})

        cli.cmd_add_gold("Digital Gold", date="2024-01-01", units=5.0, price=6100.0, member_id=1)

        # No asset creation call
        post_paths = [r.path for r in requests_mock.request_history if r.method == "POST"]
        assert "/api/assets" not in post_paths
        assert "/api/assets/3/transactions" in post_paths

    def test_buy_amount_is_negative(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])
        requests_mock.post(f"{BASE}/assets", json={"id": 41, "name": "Gold", "asset_type": "GOLD"})
        requests_mock.post(f"{BASE}/assets/41/transactions", json={"id": 3, "asset_id": 41, "type": "BUY"})

        cli.cmd_add_gold("Gold", "2023-01-01", units=8.0, price=5500.0, member_id=1)

        body = requests_mock.request_history[-1].json()
        assert body["amount_inr"] == -(8.0 * 5500.0)
        assert body["type"] == "BUY"

    def test_sgb_asset_type(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])
        requests_mock.post(f"{BASE}/assets", json={"id": 42, "name": "SGB 2023-24 S3", "asset_type": "SGB"})
        requests_mock.post(f"{BASE}/assets/42/transactions", json={"id": 4, "asset_id": 42, "type": "BUY"})

        cli.cmd_add_sgb("SGB 2023-24 S3", date="2023-12-01", units=50.0, price=6200.0, member_id=1)

        body = requests_mock.request_history[1].json()
        assert body["asset_type"] == "SGB"


# ── add rsu ───────────────────────────────────────────────────────────────────

class TestAddRSU:
    def test_creates_asset_and_vest_txn(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])
        requests_mock.post(f"{BASE}/assets", json={"id": 50, "name": "AMZN RSU", "asset_type": "STOCK_US"})
        requests_mock.post(f"{BASE}/assets/50/transactions", json={"id": 1, "asset_id": 50, "type": "VEST"})

        cli.cmd_add_rsu("AMZN RSU", date="2024-03-01", units=10.0, price=180.50, forex=83.5, member_id=1, notes="Q1 vest")

        txn_body = requests_mock.request_history[-1].json()
        assert txn_body["type"] == "VEST"
        assert txn_body["units"] == 10.0
        assert txn_body["price_per_unit"] == 180.50
        assert txn_body["forex_rate"] == 83.5

    def test_vest_amount_is_negative(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])
        requests_mock.post(f"{BASE}/assets", json={"id": 51, "name": "GOOG RSU", "asset_type": "STOCK_US"})
        requests_mock.post(f"{BASE}/assets/51/transactions", json={"id": 2, "asset_id": 51, "type": "VEST"})

        cli.cmd_add_rsu("GOOG RSU", "2024-06-01", units=5.0, price=170.0, forex=84.0, member_id=1)

        body = requests_mock.request_history[-1].json()
        assert body["amount_inr"] == -(5.0 * 170.0 * 84.0)

    def test_notes_passed_through(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[])
        requests_mock.post(f"{BASE}/assets", json={"id": 52, "name": "META RSU", "asset_type": "STOCK_US"})
        requests_mock.post(f"{BASE}/assets/52/transactions", json={"id": 3, "asset_id": 52, "type": "VEST"})

        cli.cmd_add_rsu("META RSU", "2024-09-01", 4.0, 500.0, 84.0, member_id=1, notes="Perquisite tax: ₹80,000")

        body = requests_mock.request_history[-1].json()
        assert "Perquisite tax" in body["notes"]


# ── add valuation ─────────────────────────────────────────────────────────────

class TestAddValuation:
    def test_posts_to_correct_asset(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        requests_mock.post(f"{BASE}/assets/1/valuations", json={"id": 1, "asset_id": 1})

        cli.cmd_add_valuation("Venezia Flat", value=13000000.0, date="2025-01-01")

        assert requests_mock.last_request.path == "/api/assets/1/valuations"

    def test_valuation_payload(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        requests_mock.post(f"{BASE}/assets/1/valuations", json={"id": 2, "asset_id": 1})

        cli.cmd_add_valuation("Venezia", value=14000000.0, date="2025-06-01")

        body = requests_mock.last_request.json()
        assert body["value_inr"] == 14000000.0
        assert body["date"] == "2025-06-01"
        assert body["source"] == "manual"


# ── add txn (generic) ─────────────────────────────────────────────────────────

class TestAddTxn:
    def test_posts_transaction_to_matched_asset(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        requests_mock.post(f"{BASE}/assets/2/transactions", json={"id": 1, "asset_id": 2, "type": "VEST"})

        cli.cmd_add_txn(
            asset="AMZN RSU", txn_type="VEST",
            date="2024-09-01", amount=-150850.0,
            units=10.0, price=180.5, forex=83.5,
        )

        assert requests_mock.last_request.path == "/api/assets/2/transactions"

    def test_payload_passed_correctly(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        requests_mock.post(f"{BASE}/assets/2/transactions", json={"id": 2, "asset_id": 2})

        cli.cmd_add_txn("AMZN RSU", "VEST", "2024-12-01", -90425.0, units=5.0, price=215.0, forex=84.0, notes="Q4")

        body = requests_mock.last_request.json()
        assert body["type"] == "VEST"
        assert body["amount_inr"] == -90425.0
        assert body["notes"] == "Q4"


# ── add epf-contribution ──────────────────────────────────────────────────────

EPF_ASSET = {"id": 5, "name": "My EPF", "asset_type": "EPF", "asset_class": "DEBT",
             "is_active": True, "identifier": "MHBAN00123456789"}

TXN_RESP = {"id": 99, "asset_id": 5, "type": "CONTRIBUTION"}


class TestAddEPFContribution:
    def test_creates_three_contribution_txns(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution(
            asset_name="My EPF",
            month_year="03/2026",
            employee_share=5000.0,
        )

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        assert len(post_calls) == 3

    def test_contribution_notes_are_correct(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        notes = [c.json()["notes"] for c in post_calls]
        assert "Employee Share" in notes
        assert "Employer Share" in notes
        assert "Pension Contribution (EPS)" in notes

    def test_contribution_amounts_are_negative(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0, eps_share=1250.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        amounts = [c.json()["amount_inr"] for c in post_calls]
        assert all(a < 0 for a in amounts)

    def test_employer_share_defaults_to_employee_minus_eps(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=6000.0, eps_share=1250.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        bodies = {c.json()["notes"]: c.json()["amount_inr"] for c in post_calls}
        assert bodies["Employer Share"] == -4750.0  # 6000 - 1250

    def test_employer_share_explicit(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0,
                                     eps_share=1250.0, employer_share=2000.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        bodies = {c.json()["notes"]: c.json()["amount_inr"] for c in post_calls}
        assert bodies["Employer Share"] == -2000.0

    def test_eps_share_defaults_to_1250(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        bodies = {c.json()["notes"]: c.json()["amount_inr"] for c in post_calls}
        assert bodies["Pension Contribution (EPS)"] == -1250.0

    def test_transaction_date_is_last_day_of_month(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "02/2024", employee_share=5000.0)  # Feb 2024 (leap year)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        assert post_calls[0].json()["date"] == "2024-02-29"

    def test_interest_txns_created_when_provided(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution(
            "My EPF", "03/2026", employee_share=5000.0,
            employee_interest=300.0, employer_interest=200.0, eps_interest=50.0,
        )

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        assert len(post_calls) == 6  # 3 contribution + 3 interest

    def test_interest_notes_are_correct(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution(
            "My EPF", "03/2026", employee_share=5000.0,
            employee_interest=300.0, employer_interest=200.0, eps_interest=50.0,
        )

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        notes = [c.json()["notes"] for c in post_calls]
        assert "Employee Interest" in notes
        assert "Employer Interest" in notes
        assert "EPS Interest" in notes

    def test_interest_amounts_are_positive(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution(
            "My EPF", "03/2026", employee_share=5000.0,
            employee_interest=300.0, employer_interest=200.0, eps_interest=50.0,
        )

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        interest_calls = [c for c in post_calls if c.json()["notes"].endswith("Interest")]
        assert all(c.json()["amount_inr"] > 0 for c in interest_calls)

    def test_no_interest_txns_when_not_provided(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        assert len(post_calls) == 3  # only contributions

    def test_txn_id_is_stable_and_present(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        requests_mock.post(f"{BASE}/assets/5/transactions", json=TXN_RESP)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0)

        post_calls = [r for r in requests_mock.request_history if r.method == "POST"]
        for call in post_calls:
            assert call.json().get("txn_id") is not None
            assert call.json()["txn_id"].startswith("epf_")

    def test_duplicate_txn_is_skipped(self, requests_mock, capsys):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        # First contribution succeeds, second returns 409, third succeeds
        responses = [
            {"json": TXN_RESP, "status_code": 201},
            {"json": {"detail": "Transaction with txn_id already exists"}, "status_code": 409},
            {"json": TXN_RESP, "status_code": 201},
        ]
        requests_mock.post(f"{BASE}/assets/5/transactions", responses)

        cli.cmd_add_epf_contribution("My EPF", "03/2026", employee_share=5000.0)

        out = capsys.readouterr().out
        assert "skipped" in out

    def test_invalid_month_year_format_exits(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=[EPF_ASSET])
        with pytest.raises(SystemExit):
            cli.cmd_add_epf_contribution("My EPF", "2026-03", employee_share=5000.0)

    def test_parser_epf_contribution_defaults(self):
        args = cli.build_parser().parse_args([
            "add", "epf-contribution",
            "--asset", "My EPF",
            "--month-year", "03/2026",
            "--employee-share", "5000",
        ])
        assert args.kind == "epf-contribution"
        assert args.employee_share == 5000.0
        assert args.eps_share == 1250.0
        assert args.employer_share is None
        assert args.employee_interest is None

    def test_parser_epf_contribution_all_args(self):
        args = cli.build_parser().parse_args([
            "add", "epf-contribution",
            "--asset", "My EPF",
            "--month-year", "03/2026",
            "--employee-share", "5000",
            "--eps-share", "1500",
            "--employer-share", "3500",
            "--employee-interest", "300",
            "--employer-interest", "200",
            "--eps-interest", "50",
        ])
        assert args.eps_share == 1500.0
        assert args.employer_share == 3500.0
        assert args.employee_interest == 300.0
        assert args.employer_interest == 200.0
        assert args.eps_interest == 50.0


# ── list assets ───────────────────────────────────────────────────────────────

class TestListAssets:
    def test_calls_assets_endpoint(self, requests_mock):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        cli.cmd_list_assets()
        assert requests_mock.last_request.path == "/api/assets"

    def test_prints_asset_names(self, requests_mock, capsys):
        requests_mock.get(f"{BASE}/assets", json=ASSET_LIST)
        cli.cmd_list_assets()
        out = capsys.readouterr().out
        assert "Venezia Flat" in out
        assert "AMZN RSU" in out
        assert "HDFC FD" in out


# ── refresh-prices ────────────────────────────────────────────────────────────

class TestRefreshPrices:
    def test_calls_refresh_all_endpoint(self, requests_mock):
        requests_mock.post(f"{BASE}/prices/refresh-all", json={"status": "ok"})
        cli.cmd_refresh_prices()
        assert requests_mock.last_request.path == "/api/prices/refresh-all"


# ── snapshot ──────────────────────────────────────────────────────────────────

class TestSnapshot:
    def test_calls_snapshot_endpoint(self, requests_mock):
        requests_mock.post(f"{BASE}/snapshots/take", json={"date": "2025-03-20", "total_value_inr": 5000000.0})
        cli.cmd_snapshot()
        assert requests_mock.last_request.path == "/api/snapshots/take"


# ── fetch-corp-actions ────────────────────────────────────────────────────────

CORP_RESULT = {"bonus_created": 0, "bonus_skipped": 0, "split_applied": 0,
               "split_skipped": 0, "dividend_created": 0, "dividend_skipped": 0}


class TestFetchCorpActions:
    def test_calls_fetch_all_when_no_asset_id(self, requests_mock):
        requests_mock.post(f"{BASE}/corp-actions/fetch-all", json=CORP_RESULT)
        cli.cmd_fetch_corp_actions(asset_id=None)
        assert requests_mock.last_request.path == "/api/corp-actions/fetch-all"

    def test_calls_fetch_asset_when_asset_id_given(self, requests_mock):
        requests_mock.post(f"{BASE}/corp-actions/fetch-asset/5", json=CORP_RESULT)
        cli.cmd_fetch_corp_actions(asset_id=5)
        assert requests_mock.last_request.path == "/api/corp-actions/fetch-asset/5"

    def test_parser_no_asset_id(self):
        args = cli.build_parser().parse_args(["fetch-corp-actions"])
        assert args.command == "fetch-corp-actions"
        assert args.asset_id is None

    def test_parser_with_asset_id(self):
        args = cli.build_parser().parse_args(["fetch-corp-actions", "--asset-id", "42"])
        assert args.asset_id == 42
