"""ITR API — prepare, list, detail, input update."""
from pathlib import Path

from fpdf import FPDF


def _member(client, pan="ABCDE1234F", name="Dhiraj"):
    return client.post("/members", json={"pan": pan, "name": name}).json()


def test_fiscal_years_returns_list(client):
    resp = client.get("/itr/fiscal-years")
    assert resp.status_code == 200
    fys = resp.json()["fiscal_years"]
    assert isinstance(fys, list) and fys == sorted(fys) and len(fys) > 0


def test_list_returns_empty(client):
    m = _member(client)
    resp = client.get(f"/itr/returns?member_id={m['id']}")
    assert resp.status_code == 200
    assert resp.json()["returns"] == []


def test_prepare_creates_and_lists(client):
    m = _member(client)
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ay_label"] == "2026-27"
    assert body["form_type"] == "ITR2"
    assert body["status"] == "draft"

    listed = client.get(f"/itr/returns?member_id={m['id']}").json()["returns"]
    assert [r["id"] for r in listed] == [body["id"]]


def test_prepare_is_idempotent(client):
    m = _member(client)
    a = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    b = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    assert a["id"] == b["id"]


def test_prepare_rejects_bad_fy(client):
    m = _member(client)
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025/26"})
    assert resp.status_code == 422


def test_prepare_unknown_member_is_404(client):
    resp = client.post("/itr/returns", json={"member_id": 999, "fy": "2025-26"})
    assert resp.status_code == 404


def test_detail_includes_input_document(client):
    m = _member(client)
    r = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    resp = client.get(f"/itr/returns/{r['id']}")
    assert resp.status_code == 200
    assert resp.json()["input"]["pan"] == "ABCDE1234F"


def test_detail_unknown_is_404(client):
    resp = client.get("/itr/returns/12345")
    assert resp.status_code == 404


def test_update_input_persists(client):
    m = _member(client)
    r = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    resp = client.put(
        f"/itr/returns/{r['id']}/input",
        json={"other_income": {"savings_interest": 4200.0}},
    )
    assert resp.status_code == 200
    assert resp.json()["input"]["other_income"]["savings_interest"] == 4200.0

    detail = client.get(f"/itr/returns/{r['id']}").json()
    assert detail["input"]["other_income"]["savings_interest"] == 4200.0


def test_returns_are_isolated_per_member(client):
    a = _member(client, pan="ABCDE1234F", name="A")
    b = _member(client, pan="ZYXWV9876Q", name="B")
    client.post("/itr/returns", json={"member_id": a["id"], "fy": "2025-26"})
    assert client.get(f"/itr/returns?member_id={b['id']}").json()["returns"] == []


# ── Form 16 upload ────────────────────────────────────────────────────────────

_F16 = Path(__file__).parent.parent / "fixtures" / "form16_sample.txt"


def _pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _prepared(client, **member_kw):
    m = _member(client, **member_kw)
    return client.post(
        "/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}
    ).json()


def test_form16_upload_merges_into_input(client):
    r = _prepared(client)
    pdf = _pdf_bytes(_F16.read_text())
    resp = client.post(
        f"/itr/returns/{r['id']}/form16",
        files={"file": ("f16.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["warnings"] == []
    salary = body["input"]["salary"]
    assert len(salary) == 1
    assert salary[0]["gross_salary"] == 2000000.0
    assert salary[0]["employer_tan"] == "ZZZZ00000Z"
    assert salary[0]["tds"] == 250000.0


def test_form16_upload_is_idempotent(client):
    r = _prepared(client)
    pdf = _pdf_bytes(_F16.read_text())
    for _ in range(2):
        client.post(
            f"/itr/returns/{r['id']}/form16",
            files={"file": ("f16.pdf", pdf, "application/pdf")},
        )
    detail = client.get(f"/itr/returns/{r['id']}").json()
    assert len(detail["input"]["salary"]) == 1


def test_form16_upload_persists(client):
    r = _prepared(client)
    pdf = _pdf_bytes(_F16.read_text())
    client.post(
        f"/itr/returns/{r['id']}/form16",
        files={"file": ("f16.pdf", pdf, "application/pdf")},
    )
    detail = client.get(f"/itr/returns/{r['id']}").json()
    assert detail["input"]["salary"][0]["employee_pan"] == "ABCDE1234F"


def test_form16_upload_reports_missing_fields(client):
    r = _prepared(client)
    pdf = _pdf_bytes("Random text with no Form 16 labels\n")
    resp = client.post(
        f"/itr/returns/{r['id']}/form16",
        files={"file": ("f16.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    assert resp.json()["warnings"]


def test_form16_upload_rejects_non_pdf(client):
    r = _prepared(client)
    resp = client.post(
        f"/itr/returns/{r['id']}/form16",
        files={"file": ("f16.pdf", b"not a pdf", "application/pdf")},
    )
    assert resp.status_code == 422


def test_form16_upload_unknown_return_is_404(client):
    resp = client.post(
        "/itr/returns/99999/form16",
        files={"file": ("f16.pdf", b"x", "application/pdf")},
    )
    assert resp.status_code == 404

