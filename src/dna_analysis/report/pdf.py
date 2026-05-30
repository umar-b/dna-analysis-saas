"""Render a ReportObject to a human-readable PDF (ADR-0009/0011 output format).

Pure and deterministic — no LLM call. The same typed ReportObject that drives
report.md is laid out for a lay reader:

  page 1   "Your results in plain language" — headline counts, one friendly
           card per actionable finding (gene purpose + medicines affected +
           a talk-to-your-doctor note), plus plain lifestyle/lab flags. No
           citation accessions or diplotype jargon.
  middle   lifestyle & lab snapshot (the readable prose already in the object)
  end      technical detail — full recommendation paragraphs, diplotype labels,
           citation accessions, caveats, the full unremarkable-screen table,
           and the ADR-0011 disclaimer.

The lay first page is built only from structured fields, so it never invents a
claim the synthesis step did not make.
"""

from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from dna_analysis.models import ReportObject
from dna_analysis.report.render import DISCLAIMER

# Plain-language, one-line purpose for each V1 PGx gene. This is general gene
# biology (not a patient-specific claim), used only to make the lay summary
# readable; genes outside the map fall back to a generic line.
_GENE_PLAIN = {
    "CYP2C19": "affects how your body processes some blood thinners, antidepressants, and stomach-acid drugs",
    "CYP2C9": "affects how your body processes some blood thinners and anti-inflammatory drugs",
    "CYP2D6": "affects how your body processes many common medicines, including some painkillers",
    "CYP3A5": "affects how your body processes certain anti-rejection (transplant) medicines",
    "CYP4F2": "fine-tunes how much of certain blood thinners you need",
    "DPYD": "affects how your body breaks down some chemotherapy drugs",
    "NUDT15": "affects how your body handles certain immune-suppressing drugs",
    "SLCO1B1": "affects your risk of muscle side-effects from cholesterol (statin) drugs",
    "TPMT": "affects how your body handles certain immune-suppressing and chemotherapy drugs",
    "UGT1A1": "affects how your body clears certain cancer and HIV medicines",
    "VKORC1": "affects how sensitive you are to the blood thinner warfarin",
}

# A small canonical PGx-drug lexicon, supplemented at render time with the drug
# names already present in the unremarkable screen, so the lay page can name
# "medicines affected" by scanning each recommendation paragraph.
_CANON_DRUGS = {
    "clopidogrel", "voriconazole", "omeprazole", "escitalopram", "warfarin",
    "phenytoin", "celecoxib", "fluvastatin", "tacrolimus", "simvastatin",
    "atorvastatin", "pravastatin", "rosuvastatin", "pitavastatin", "lovastatin",
    "fluorouracil", "capecitabine", "tegafur", "mercaptopurine", "azathioprine",
    "thioguanine", "atazanavir", "irinotecan",
}


def _drug_lexicon(report: ReportObject) -> set[str]:
    drugs = set(_CANON_DRUGS)
    for f in report.unremarkable_screen:
        if f.drug:
            drugs.add(f.drug.lower())
    return drugs


def _drugs_in(paragraph: str, lexicon: set[str]) -> list[str]:
    text = paragraph.lower()
    found = [d for d in lexicon if re.search(rf"\b{re.escape(d)}\b", text)]
    return sorted(found)


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=ss["Title"], fontSize=22, spaceAfter=4, textColor=colors.HexColor("#1a3c5e")
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=ss["Normal"], fontSize=11, textColor=colors.HexColor("#5a6b7b"), spaceAfter=10
        ),
        "h2": ParagraphStyle(
            "h2", parent=ss["Heading2"], fontSize=15, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1a3c5e")
        ),
        "card_gene": ParagraphStyle(
            "card_gene", parent=ss["Heading3"], fontSize=12.5, spaceAfter=1, textColor=colors.HexColor("#9c4221")
        ),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontSize=10.5, leading=15, spaceAfter=6, alignment=TA_LEFT),
        "plain": ParagraphStyle("plain", parent=ss["Normal"], fontSize=11, leading=16, spaceAfter=3),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#5a6b7b")),
        "meds": ParagraphStyle("meds", parent=ss["Normal"], fontSize=10, leading=14, spaceAfter=8, textColor=colors.HexColor("#2b3a48")),
        "disclaimer": ParagraphStyle("disclaimer", parent=ss["Italic"], fontSize=8.5, leading=12, textColor=colors.HexColor("#777777")),
    }
    return styles


def _cover(report: ReportObject, st, lexicon) -> list:
    flow: list = []
    flow.append(Paragraph("Your DNA &amp; Health Report", st["title"]))
    flow.append(Paragraph("A plain-language summary of what your results mean", st["subtitle"]))
    flow.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d0d7de"), spaceAfter=10))

    n_act = len(report.actionable_findings)
    n_screen = len(report.unremarkable_screen)
    if n_act:
        lead = (
            f"We looked at how your genes affect a range of medicines. "
            f"<b>{n_act} finding{'s' if n_act != 1 else ''} need{'s' if n_act == 1 else ''} "
            f"your attention</b>, and {n_screen} other gene–drug checks looked unremarkable."
        )
    else:
        lead = (
            f"We looked at how your genes affect a range of medicines. Nothing needed "
            f"special attention across {n_screen} gene–drug checks."
        )
    flow.append(Paragraph(lead, st["plain"]))
    flow.append(Paragraph(
        "These are <b>not instructions to change any medicine</b>. Share this report "
        "with your doctor or pharmacist before making any decision.", st["plain"]
    ))
    flow.append(Spacer(1, 6))

    if report.actionable_findings:
        flow.append(Paragraph("What stood out", st["h2"]))
        for a in report.actionable_findings:
            gene = (a.gene or "").upper()
            purpose = _GENE_PLAIN.get(gene, "affects how your body responds to certain medicines")
            flow.append(Paragraph(f"{gene} — {purpose}", st["card_gene"]))
            meds = _drugs_in(a.recommendation_paragraph, lexicon)
            if meds:
                shown = ", ".join(meds[:8]) + ("…" if len(meds) > 8 else "")
                flow.append(Paragraph(f"<b>Medicines that may be affected:</b> {shown}", st["meds"]))
            else:
                flow.append(Paragraph(
                    "<b>What to do:</b> mention this gene to your doctor before starting new medicines.",
                    st["meds"],
                ))

    # Plain lifestyle / lab flags (only the lines a layperson cares about)
    flags = _plain_flags(report)
    if flags:
        flow.append(Paragraph("Other things worth a look", st["h2"]))
        for line in flags:
            flow.append(Paragraph(f"• {line}", st["plain"]))

    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d0d7de"), spaceAfter=6))
    flow.append(Paragraph(
        "Full technical detail — diplotypes, guideline citations, and every gene–drug "
        "pair we screened — follows in the later pages.", st["small"]
    ))
    return flow


def _plain_flags(report: ReportObject) -> list[str]:
    """Clean, lay-readable lifestyle/lab takeaways for the first page.

    The lab prose is dense German clinical text full of decimals and
    semicolons, so we summarise rather than slice it (the full verbatim prose
    stays in the technical detail section). Sentence splitting is done only on
    a period followed by a capital, so values like ``40.2 ms`` stay intact.
    """
    out: list[str] = []
    if report.lifestyle_observations:
        first = report.lifestyle_observations[0].observation_paragraph.strip()
        snippet = re.split(r"(?<=\.)\s+(?=[A-Z])", first)[0].strip()
        if snippet:
            out.append(snippet)

    lab_text = " ".join(o.observation_paragraph for o in report.lab_observations).lower()
    if lab_text:
        if re.search(r"vitamin d.{0,40}low", lab_text):
            out.append("Your vitamin D looked low — worth asking your doctor about.")
        n_flags = len(re.findall(r"\((?:flagged\s+)?(?:low|high)\b", lab_text))
        if n_flags:
            out.append(
                f"{n_flags} blood-test value{'s' if n_flags != 1 else ''} were flagged "
                "outside the usual range — the lab section lists each one."
            )
        else:
            out.append("Your blood-test results are summarised in the lab section.")
    return out[:4]


def _detail(report: ReportObject, st) -> list:
    flow: list = [Paragraph("Technical detail", st["title"]),
                  Paragraph("For your doctor or pharmacist", st["subtitle"]),
                  HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d0d7de"), spaceAfter=8)]

    if report.actionable_findings:
        flow.append(Paragraph("Actionable findings", st["h2"]))
        for a in report.actionable_findings:
            flow.append(Paragraph(a.diplotype_label or a.gene, st["card_gene"]))
            flow.append(Paragraph(a.recommendation_paragraph, st["body"]))
            cite = a.citation_id or "—"
            refs = ", ".join(a.related_finding_rsids)
            tail = f"Citation: {cite}" + (f"  ·  Variants: {refs}" if refs else "")
            flow.append(Paragraph(tail, st["small"]))
            flow.append(Spacer(1, 6))

    if report.lifestyle_observations:
        flow.append(Paragraph("Lifestyle observations", st["h2"]))
        for o in report.lifestyle_observations:
            flow.append(Paragraph(o.observation_paragraph, st["body"]))

    if report.lab_observations:
        flow.append(Paragraph("Lab observations", st["h2"]))
        for o in report.lab_observations:
            flow.append(Paragraph(o.observation_paragraph, st["body"]))

    if report.caveats:
        flow.append(Paragraph("Caveats", st["h2"]))
        for c in report.caveats:
            flow.append(Paragraph(f"• {c}", st["body"]))

    if report.unremarkable_screen:
        flow.append(Paragraph("Screened, unremarkable", st["h2"]))
        rows = [["RSID", "Gene", "Drug", "Note"]]
        for f in report.unremarkable_screen:
            rows.append([f.rsid, f.gene, f.drug, f.recommendation_gist])
        table = Table(rows, colWidths=[28 * mm, 22 * mm, 28 * mm, 92 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3c5e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f8")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        flow.append(table)

    flow.append(Spacer(1, 12))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d0d7de"), spaceAfter=6))
    flow.append(Paragraph(DISCLAIMER, st["disclaimer"]))
    return flow


def render_pdf(report_object: ReportObject) -> bytes:
    """Render ``report_object`` to a lay-friendly PDF and return the bytes."""
    st = _styles()
    lexicon = _drug_lexicon(report_object)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
        title="DNA Analysis Report",
    )
    story = _cover(report_object, st, lexicon)
    story.append(PageBreak())
    story.extend(_detail(report_object, st))
    doc.build(story)
    return buf.getvalue()
