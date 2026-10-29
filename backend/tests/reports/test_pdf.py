import io

import pytest
from pypdf import PdfReader

from app.reports.pdf import n, render_pdf, t
from tests.api.conftest import client  # noqa: F401
from tests.reports.test_builder_commentary import build, card, company
from tests.reports.test_monthly_review_api import ALICE, VIC, approve, data, db, propose, start  # noqa: F401


def text_of(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def report(**kw):
    now = card(82.4, "amber", [company("IC014", 50.3, "red"), company("IC002", 95.0, "green")], synthetic=kw.pop("synthetic", True))
    prev = card(85.1, "amber", [company("IC014", 92.0, "green"), company("IC002", 90.0, "green")])
    r = build(now, prev)
    r["commentary"] = {"text": kw.pop("commentary", "The Group score is 82.4."), "method": "ai", "grounded": True, "issues": []}
    return r


def test_the_pdf_contains_the_headline_pillars_attention_and_caveats():
    pdf = render_pdf(report())
    assert pdf.startswith(b"%PDF") and len(PdfReader(io.BytesIO(pdf)).pages) >= 1
    txt = text_of(pdf)
    for needle in ("monthly review, 2026-10", "Group score: 82.4", "-2.7 vs 2026-09", "Pillars", "Off track", "IC014", "50.3",
                   "Sources and lineage", "Caveats", "Calculation version 1", "AI-drafted; every number verified"):
        assert needle in txt, needle
    assert "Synthetic data" in txt and "must not be used for decisions" in txt


def test_no_synthetic_warning_when_the_data_is_not_synthetic():
    assert "Synthetic data" not in text_of(render_pdf(report(synthetic=False)))


def test_a_published_snapshot_pdf_states_its_hash_and_who_published_it():
    txt = text_of(render_pdf(report(), {"hash": "ab12cd34ef56ab12cd34ef56", "by": "bob", "at": "2026-10-31T00:00:00+00:00", "snapshot_id": 7}))
    assert "published snapshot #7 by bob" in txt and "sha256 ab12cd34ef56ab12" in txt


@pytest.mark.parametrize("hostile", [
    "Revenue <b>up</b> & <i>strong</i> </para><para>", "AT&T <font color=red>x</font> &amp; &lt;", "unicode: → ≥ ✓ 日本語 😀 “quotes” – dash",
    "<img src='http://evil.example/x.png'/>", "x" * 5000, "line1\nline2\r\n\tTabbed", "\x00null\x01ctrl"])
def test_untrusted_text_can_never_break_the_export_or_inject_markup(hostile):
    r = report(commentary=hostile)
    r["attention"]["red"][0]["code"] = hostile[:40]
    r["caveats"].append(hostile)
    pdf = render_pdf(r)                                                                         # must not raise
    txt = text_of(pdf)
    if "<b>up</b>" in hostile:
        assert "<b>up</b>" in txt                                                              # shown literally, not interpreted as bold
    assert PdfReader(io.BytesIO(pdf)).pages


def test_text_helpers():
    assert t("a < b & c") == "a &lt; b &amp; c" and t(None) == "—" and t("→") == "?"
    assert n(None) == "—" and n(-0.04) == "0" and n(82.34) == "82.3" and n(95.0) == "95"


def test_a_long_report_paginates():
    r = report()
    r["attention"]["red"] = [{"code": f"IC{i:03d}", "score": 50 + i / 10, "weakest_pillars": [{"pillar": "retention", "score": 40.0}]} for i in range(300)]
    r["attention"]["red_count"] = 300
    pdf = render_pdf(r)
    assert len(PdfReader(io.BytesIO(pdf)).pages) > 3 and "IC299" in text_of(pdf) and "Page 2" in text_of(pdf)


# --- API ---

def test_run_pdf_endpoint(client, data, db):
    rid = start(client).json()["id"]
    r = client.get(f"/workflows/runs/{rid}/pdf", headers=VIC)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="monthly-review-2026-10.pdf"'
    txt = text_of(r.content)
    assert "monthly review, 2026-10" in txt and "Synthetic data" in txt
    from app.core.security import Role, make_token
    scoped = {"Authorization": f"Bearer {make_token('sam', Role.EDITOR, [1])}"}
    assert client.get(f"/workflows/runs/{rid}/pdf", headers=scoped).status_code == 403
    assert client.get("/workflows/runs/999/pdf", headers=VIC).status_code == 404


def test_snapshot_pdf_endpoint_carries_the_integrity_hash(client, data, db):
    rid = start(client).json()["id"]
    sid = approve(client, propose(client, rid).json()["approval"]["id"]).json()["result"]["snapshot_id"]
    snap = client.get(f"/reports/snapshots/{sid}", headers=VIC).json()
    r = client.get(f"/reports/snapshots/{sid}/pdf", headers=VIC)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert snap["content_hash"][:16] in text_of(r.content) and f"snapshot #{sid} by bob" in text_of(r.content)
    assert client.get("/reports/snapshots/999/pdf", headers=VIC).status_code == 404
    plain = client.post("/reports/snapshots", params={"period": "2026-10"}, headers=ALICE).json()["id"]      # a scorecard snapshot, not a review
    assert client.get(f"/reports/snapshots/{plain}/pdf", headers=VIC).status_code == 404
