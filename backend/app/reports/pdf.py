"""PDF rendering of the monthly review. Layout only: every number comes from the report document."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.kpi_registry.seed import PILLAR_LABELS

STATUS_BG = {"green": colors.HexColor("#C6EFCE"), "amber": colors.HexColor("#FFEB9C"), "red": colors.HexColor("#FFC7CE")}
ACCENT = colors.HexColor("#0F172A")


def t(x) -> str:
    """Text safe for a PDF paragraph. Escapes markup (names and AI commentary are not trusted) and replaces
    characters the built-in Latin-1 font cannot draw, so no input can break the export."""
    s = "—" if x is None else str(x)
    return escape(s).encode("cp1252", "replace").decode("cp1252")


def n(x, d=1) -> str:
    return "—" if x is None else f"{round(x, d) + 0.0:.{d}f}".rstrip("0").rstrip(".")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontSize=18, alignment=0, spaceAfter=4, textColor=ACCENT),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, textColor=ACCENT),
        "p": ParagraphStyle("p", parent=ss["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#475569")),
        "cell": ParagraphStyle("cell", parent=ss["BodyText"], fontSize=8.5, leading=10.5),
    }


def _table(rows, widths, header=True, status_col=None):
    st = _styles()["cell"]
    data = [[Paragraph(t(c), st) for c in r] for r in rows]
    tb = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0"))]
    if status_col is not None:
        for i, r in enumerate(rows[1:] if header else rows, start=1 if header else 0):
            bg = STATUS_BG.get(str(r[status_col]))
            if bg:
                style.append(("BACKGROUND", (status_col, i), (status_col, i), bg))
    tb.setStyle(TableStyle(style))
    return tb


def render_pdf(r: dict, published: dict | None = None) -> bytes:
    """`published` = {"hash", "by", "at", "snapshot_id"} for an immutable snapshot, shown in the footer."""
    s, m, h = _styles(), r["meta"], r["headline"]
    story = [Paragraph(f"Group HR Scorecard: monthly review, {t(m['period'])}", s["h1"])]
    if m["synthetic_data"]:
        warn = Table([[Paragraph("<b>Synthetic data.</b> This report is built on generated data and must not be used for decisions.", s["p"])]],
                     colWidths=[175 * mm])
        warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#F59E0B")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [warn, Spacer(1, 6)]
    move = "" if h["delta"] is None else f" ({'+' if h['delta'] > 0 else ''}{n(h['delta'])} vs {t(m['previous_period'])})"
    story.append(Paragraph(f"<b>Group score: {n(h['group_score'])}</b> ({t(h['group_status'] or 'no data')}){move}. Based on {h['coverage_pct']}% of "
                           f"scorecard weight; {m['companies_with_data']} of {m['companies_in_scope']} companies have data.", s["p"]))
    c = r.get("commentary")
    if c:
        story += [Paragraph("Commentary", s["h2"]), Paragraph(t(c["text"]), s["p"]),
                  Paragraph("AI-drafted; every number verified against the computed results." if c["method"] == "ai"
                            else "Template generated from the computed results.", s["small"])]
    story += [Paragraph("Pillars", s["h2"]),
              _table([["Pillar", "Score", "Status", "Previous", "Change"]] +
                     [[PILLAR_LABELS.get(p["pillar"], p["pillar"]), n(p["score"]), p["status"] or "—", n(p["previous"]), n(p["delta"])] for p in h["pillars"]],
                     [70 * mm, 25 * mm, 30 * mm, 25 * mm, 25 * mm], status_col=2)]
    d = h["distribution"]
    story.append(Paragraph(f"Companies: {d['green']} on track, {d['amber']} need attention, {d['red']} off track, {d['none']} no data.", s["small"]))
    a = r["attention"]
    if a["red"]:
        story += [Paragraph(f"Off track ({a['red_count']})", s["h2"]),
                  _table([["Company", "Score", "Weakest pillars"]] +
                         [[x["code"], n(x["score"]), ", ".join(f"{PILLAR_LABELS.get(w['pillar'], w['pillar'])} {n(w['score'])}" for w in x["weakest_pillars"])] for x in a["red"]],
                         [30 * mm, 25 * mm, 120 * mm])]
    mv = r["movers"]
    if mv["improved"] or mv["declined"]:
        story += [Paragraph("Movement since last month", s["h2"]),
                  _table([["Improved", "Declined"]] + [[(f"{i['code']} {'+' if i['delta'] > 0 else ''}{n(i['delta'])}" if i else ""),
                                                        (f"{k['code']} {n(k['delta'])}" if k else "")]
                                                       for i, k in zip(mv["improved"] + [None] * 5, mv["declined"] + [None] * 5, strict=False)][:max(len(mv["improved"]), len(mv["declined"]))],
                         [87 * mm, 88 * mm])]
    e = r["exceptions"]
    lines = []
    if e["no_source"]:
        lines.append(f"<b>No source ({len(e['no_source'])} KPIs):</b> " + ", ".join(t(k.replace("_", " ")) for k in e["no_source"]))
    lines += [f"Missing: {t(x['kpi'].replace('_', ' '))} for {x['missing_count']} companies" for x in e["missing"][:10]]
    if e["not_due"]:
        lines.append("Not yet due: " + ", ".join(t(k.replace("_", " ")) for k in e["not_due"]))
    if lines:
        story += [Paragraph("Exceptions", s["h2"])] + [Paragraph("• " + ln, s["p"]) for ln in lines]
    story += [Paragraph("Sources and lineage", s["h2"]),
              _table([["Source", "Mode", "Last run", "OK / failed"]] +
                     [[x["label"], x["mode"], (x["last_run"] or {}).get("status", "never"),
                       f"{x['last_run']['companies_ok']} / {x['last_run']['companies_failed']}" if x["last_run"] else "—"] for x in r["lineage"]["sources"]],
                     [70 * mm, 30 * mm, 35 * mm, 40 * mm]),
              Paragraph("Records by origin: " + ", ".join(f"{t(k)} {v}" for k, v in sorted(r["lineage"]["data_origin"].items())), s["small"])]
    if r["caveats"]:
        story += [Paragraph("Caveats", s["h2"])] + [Paragraph("• " + t(x), s["p"]) for x in r["caveats"]]

    footer = f"Calculation version {t(m['calc_version'])} · generated {t(m['generated_at'])} by {t(m['generated_by'])}"
    if published:
        footer += f" · published snapshot #{published['snapshot_id']} by {t(published['by'])} · sha256 {published['hash'][:16]}"

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(18 * mm, 10 * mm, footer[:150])
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                      title=f"Group HR Scorecard {m['period']}", author="CHRO Copilot").build(story, onFirstPage=draw, onLaterPages=draw)
    return buf.getvalue()

