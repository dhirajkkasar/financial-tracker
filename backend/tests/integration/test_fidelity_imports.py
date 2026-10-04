"""Integration tests for the Fidelity lots importers (open + closed, USD exports).

Fixtures use fake tickers/numbers in the exact shape of the real NetBenefits
exports. End-to-end: preview-file → commit-file, idempotent re-imports, and
the open-snapshot prune (shrunken remainder replaces, never duplicates).
"""
import json
from datetime import date
from pathlib import Path

import pytest

from app.importers.base import ParsedTransaction

FIXTURES = Path(__file__).parent.parent / "fixtures"

RATES = {"2025-03": 86.5, "2025-06": 84.0, "2025-10": 85.0}


def _inputs(**overrides):
    payload = {"ticker": "FAKE", "exchange_rates": dict(RATES)}
    payload.update(overrides)
    return json.dumps(payload)


def _open_bytes():
    return (FIXTURES / "fidelity_open_lots_sample.csv").read_bytes()


def _closed_bytes():
    return (FIXTURES / "fidelity_closed_lots_sample.csv").read_bytes()


def _preview(client, source, file_bytes, filename, user_inputs):
    resp = client.post(
        f"/import/preview-file?source={source}&format=csv",
        data={"user_inputs": user_inputs},
        files={"file": (filename, file_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _commit(client, preview_id):
    resp = client.post(f"/import/commit-file/{preview_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _db_rows(db, ticker="FAKE"):
    from app.repositories.unit_of_work import UnitOfWork
    from app.models.asset import Asset
    asset = db.query(Asset).filter(Asset.identifier == ticker).one()
    uow = UnitOfWork(db)
    return uow.transactions.list_by_asset(asset.id)


def test_parsed_transaction_has_forex_rate_field():
    txn = ParsedTransaction(
        source="test", asset_name="AMZN", asset_identifier="AMZN",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=68.0, price_per_unit=196.40, amount_inr=-1_380_605.0,
        txn_id="test_001", forex_rate=84.5,
    )
    assert txn.forex_rate == 84.5


# ---------------------------------------------------------------------------
# open lots endpoint
# ---------------------------------------------------------------------------

def test_fidelity_open_endpoint_preview(client):
    body = _preview(client, "fidelity_open", _open_bytes(), "open.csv", _inputs())
    assert body["new_count"] == 2
    assert body["duplicate_count"] == 0
    types = {t["txn_type"] for t in body["transactions"]}
    assert types == {"VEST", "BUY"}  # RS remainder + SP remainder


def test_fidelity_open_missing_ticker_returns_422(client):
    resp = client.post(
        "/import/preview-file?source=fidelity_open&format=csv",
        data={"user_inputs": json.dumps({"exchange_rates": RATES})},
        files={"file": ("open.csv", _open_bytes(), "text/csv")},
    )
    assert resp.status_code == 422
    assert "ticker" in resp.text


def test_fidelity_open_missing_rate_returns_422(client):
    resp = client.post(
        "/import/preview-file?source=fidelity_open&format=csv",
        data={"user_inputs": _inputs(exchange_rates={"2025-03": 86.5})},
        files={"file": ("open.csv", _open_bytes(), "text/csv")},
    )
    assert resp.status_code == 422
    assert "2025-06" in resp.text


def test_fidelity_open_idempotent(client):
    first = _commit(client, _preview(client, "fidelity_open", _open_bytes(), "open.csv", _inputs())["preview_id"])
    assert first["inserted"] == 2
    second = _commit(client, _preview(client, "fidelity_open", _open_bytes(), "open.csv", _inputs())["preview_id"])
    assert second["inserted"] == 0
    assert second["skipped"] == 2
    assert second.get("pruned", 0) == 0


# ---------------------------------------------------------------------------
# closed lots endpoint
# ---------------------------------------------------------------------------

def test_fidelity_closed_endpoint_preview(client):
    body = _preview(client, "fidelity_closed", _closed_bytes(), "closed.csv", _inputs())
    assert body["new_count"] == 6  # 3 rows × (acquisition leg + SELL)
    assert body["duplicate_count"] == 0
    assert any("defaulted to RS" in w for w in body["warnings"])


def test_fidelity_closed_missing_rate_returns_422(client):
    resp = client.post(
        "/import/preview-file?source=fidelity_closed&format=csv",
        data={"user_inputs": _inputs(exchange_rates={"2025-03": 86.5})},
        files={"file": ("closed.csv", _closed_bytes(), "text/csv")},
    )
    assert resp.status_code == 422


def test_fidelity_closed_idempotent(client):
    first = _commit(client, _preview(client, "fidelity_closed", _closed_bytes(), "closed.csv", _inputs())["preview_id"])
    assert first["inserted"] == 6
    second = _commit(client, _preview(client, "fidelity_closed", _closed_bytes(), "closed.csv", _inputs())["preview_id"])
    assert second["inserted"] == 0
    assert second["skipped"] == 6


# ---------------------------------------------------------------------------
# lots link open remainders to closed sales; prune replaces shrunken snapshot
# ---------------------------------------------------------------------------

def _ttype(t) -> str:
    return t.type.value if hasattr(t.type, "value") else str(t.type)


def test_open_and_closed_share_lot_ids(client, db):
    _commit(client, _preview(client, "fidelity_open", _open_bytes(), "open.csv", _inputs())["preview_id"])
    sources = {"2025-03-10": "RS", "2025-06-20": "SP"}
    _commit(client, _preview(
        client, "fidelity_closed", _closed_bytes(), "closed.csv", _inputs(sources=sources))["preview_id"])

    rows = _db_rows(db)
    assert len(rows) == 8  # 2 open + 6 closed
    sells = [t for t in rows if _ttype(t) == "SELL"]
    assert len(sells) == 3
    lots = {t.lot_id for t in rows}
    # One economic lot per (acquired date, unit cost): Mar-10 and Jun-20
    assert len(lots) == 2
    for sell in sells:
        siblings = [t for t in rows if t.lot_id == sell.lot_id and _ttype(t) != "SELL"]
        assert siblings, "every SELL shares its lot with an acquisition leg"
    # SP legs are BUY (open remainder + closed STC acquisition leg)
    jun_lot = next(t.lot_id for t in rows if t.date == date(2025, 6, 20))
    jun_types = {_ttype(t) for t in rows if t.lot_id == jun_lot}
    assert jun_types == {"BUY", "SELL"}


def test_open_snapshot_prune_replaces_shrunken_remainder(client, db):
    _commit(client, _preview(client, "fidelity_open", _open_bytes(), "open.csv", _inputs())["preview_id"])

    shrunk = _open_bytes().replace(b"Mar-10-2025,40.0000,5080.00,127.00",
                                    b"Mar-10-2025,30.0000,3810.00,127.00")
    preview = _preview(client, "fidelity_open", shrunk, "open.csv", _inputs())
    assert any("will be removed" in w for w in preview["warnings"])
    result = _commit(client, preview["preview_id"])
    assert result["inserted"] == 1   # the 30u remainder
    assert result.get("pruned", 0) == 1  # the stale 40u remainder

    rows = _db_rows(db)
    mar = [t for t in rows if t.date == date(2025, 3, 10)]
    assert len(mar) == 1
    assert mar[0].units == pytest.approx(30.0)
    assert _ttype(mar[0]) == "VEST"
    # Jun lot untouched
    jun = [t for t in rows if t.date == date(2025, 6, 20)]
    assert len(jun) == 1 and jun[0].units == pytest.approx(25.0)

    # Re-importing the same shrunk snapshot is a clean no-op
    again_preview = _preview(client, "fidelity_open", shrunk, "open.csv", _inputs())
    assert not any("will be removed" in w for w in again_preview["warnings"])
    again = _commit(client, again_preview["preview_id"])
    assert again["inserted"] == 0
    assert again.get("pruned", 0) == 0
