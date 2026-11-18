"""Phase 14: downloadable PDF report for a single analysis.

Pure-Python via reportlab (no system deps), so it works on the free deployment tier.
build_report() never trusts every key to exist: anything missing is skipped, so a slightly
different result shape can't crash the download. The medical disclaimer (Phase 18) is always
included, whatever else is present.
"""
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

INK = colors.HexColor("#1f2a44")
ACCENT = colors.HexColor("#5b7cfa")
MUTED = colors.HexColor("#6b7280")
WARN_BG = colors.HexColor("#fff4e5")

DISCLAIMER = (
    "This report is produced by AuraCry, an experimental study project and NOT a medical device. "
    "It cannot diagnose and does not replace a paediatrician. A high confidence score is a statistical "
    "estimate, not medical certainty, and the result may be wrong. If your baby seems unwell, is not "
    "feeding, is unusually drowsy, has a fever, or you are worried for any reason, contact a doctor or "
    "emergency services. Never delay medical care because of anything shown here."
)


def _styles():
    ss = getSampleStyleSheet()
    s = {
        "h1": ParagraphStyle("h1", parent=ss["Title"], textColor=INK, fontSize=22, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], textColor=MUTED, fontSize=9, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=ACCENT, fontSize=12,
                             spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], textColor=INK, fontSize=10, leading=14),
        "small": ParagraphStyle("small", parent=ss["Normal"], textColor=MUTED, fontSize=8, leading=11),
        "disc": ParagraphStyle("disc", parent=ss["Normal"], textColor=INK, fontSize=8.5, leading=12),
    }
    return s


def build_report(analysis, spectrogram_path=None):
    """analysis: the dict from analysis_dict(..., full=True). Returns PDF bytes."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="AuraCry analysis report",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    flow = []

    res = analysis.get("result", {}) or {}
    code = analysis.get("code", "AC-?????")
    label = analysis.get("predicted_label") or res.get("label") or analysis.get("predicted_category", "—")
    conf = analysis.get("confidence")
    uncertain = analysis.get("uncertain") or res.get("uncertain")
    created = analysis.get("created_at", "")
    fname = analysis.get("audio_filename", "")
    dur = analysis.get("duration_sec")

    flow.append(Paragraph("AuraCry", s["h1"]))
    flow.append(Paragraph("Infant Cry Analysis — experimental study report", s["sub"]))

    meta = [["Report", code], ["Generated", created.replace("T", " ").replace("Z", " UTC")],
            ["Audio file", fname], ["Duration", f"{dur:g} s" if isinstance(dur, (int, float)) else "—"]]
    t = Table(meta, colWidths=[35 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED), ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(t)

    # --- Result ---
    flow.append(Paragraph("Most likely reason", s["h2"]))
    conf_txt = f"{conf:g}%" if isinstance(conf, (int, float)) else "—"
    flow.append(Paragraph(f"<b><font size=15>{label}</font></b>&nbsp;&nbsp;"
                          f"<font color='#6b7280'>confidence {conf_txt}</font>", s["body"]))
    if uncertain:
        flow.append(Spacer(1, 4))
        box = Table([[Paragraph("Low-confidence result — the signal was ambiguous. Treat this as a weak hint only.",
                                s["small"])]], colWidths=[155 * mm])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
                                 ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#f0c489")),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        flow.append(box)

    # --- Probability breakdown ---
    probs = analysis.get("probabilities") or {}
    if probs:
        flow.append(Paragraph("All categories", s["h2"]))
        rows = [["Category", "Probability"]]
        for k, v in sorted(probs.items(), key=lambda kv: kv[1], reverse=True):
            vv = f"{v:g}%" if isinstance(v, (int, float)) else str(v)
            rows.append([k, vv])
        pt = Table(rows, colWidths=[110 * mm, 45 * mm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7ff")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        flow.append(pt)

    # --- Quality warnings ---
    qw = res.get("quality_warnings") or []
    if qw:
        flow.append(Paragraph("Recording quality notes", s["h2"]))
        for w in qw[:5]:
            msg = w.get("detail") or w.get("message") or str(w) if isinstance(w, dict) else str(w)
            flow.append(Paragraph(f"• {msg}", s["small"]))

    # --- Suggestions ---
    adv = res.get("advice") or {}
    steps = adv.get("steps") or []
    if steps:
        flow.append(Paragraph("What you can try", s["h2"]))
        for st in steps[:4]:
            title = st.get("title", "") if isinstance(st, dict) else str(st)
            detail = st.get("detail", "") if isinstance(st, dict) else ""
            flow.append(Paragraph(f"<b>{title}.</b> {detail}", s["body"]))
            flow.append(Spacer(1, 2))

    # --- Spectrogram ---
    if spectrogram_path and Path(spectrogram_path).exists():
        try:
            flow.append(Paragraph("Spectrogram", s["h2"]))
            flow.append(Image(str(spectrogram_path), width=150 * mm, height=55 * mm))
        except Exception:
            pass

    # --- Disclaimer (always) ---
    flow.append(Spacer(1, 10))
    disc = Table([[Paragraph("<b>Important — please read</b><br/>" + DISCLAIMER, s["disc"])]],
                 colWidths=[155 * mm])
    disc.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                              ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    flow.append(disc)
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("AuraCry · experimental infant cry analysis · not for medical use", s["small"]))

    doc.build(flow)
    buf.seek(0)
    return buf.read()
