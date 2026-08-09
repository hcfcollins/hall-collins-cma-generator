#!/usr/bin/env python3
"""
PDF Builder — Hall Collins CMA Generator
Builds the complete CMA PDF natively using ReportLab (no Word required).
Final document order:
  1. HC Cover Page  (HC - CMA Cover Page Summer Pic.pdf — always fixed)
  2. CMA Content    (generated here with ReportLab)
  3. Supplemental   (uploaded PDF, first 2 pages stripped)
"""

import io
import os
from datetime import date

from pypdf import PdfWriter, PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

# ── Brand Colors ──────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#173348")
PINK   = colors.HexColor("#E91E63")
LGRAY  = colors.HexColor("#F5F5F5")
MGRAY  = colors.HexColor("#999999")
DGRAY  = colors.HexColor("#333333")
WHITE  = colors.white
BLUSH  = colors.HexColor("#FFF8FB")
STEEL  = colors.HexColor("#EEF1F4")

COVER_PDF_PATH = "HC - CMA Cover Page Summer Pic.pdf"


# ── Style Helpers ─────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", fontName="Times-Bold", fontSize=15,
                             textColor=NAVY, spaceAfter=4, spaceBefore=14),
        "h2": ParagraphStyle("h2", fontName="Times-Bold", fontSize=12,
                             textColor=PINK, spaceAfter=4, spaceBefore=10),
        "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=10,
                               textColor=DGRAY, spaceAfter=6, leading=14),
        "body_indent": ParagraphStyle("body_indent", fontName="Times-Roman",
                                      fontSize=10, textColor=DGRAY,
                                      spaceAfter=6, leading=14, leftIndent=18),
        "label": ParagraphStyle("label", fontName="Times-Bold", fontSize=9,
                                textColor=NAVY),
        "caption": ParagraphStyle("caption", fontName="Times-Italic", fontSize=9,
                                  textColor=MGRAY, spaceAfter=4),
        "center": ParagraphStyle("center", fontName="Times-Roman", fontSize=10,
                                 alignment=TA_CENTER, textColor=DGRAY),
        "price_label": ParagraphStyle("pl", fontName="Times-Roman", fontSize=9,
                                      textColor=NAVY, alignment=TA_CENTER),
        "price_big": ParagraphStyle("pb", fontName="Times-Bold", fontSize=18,
                                    textColor=PINK, alignment=TA_CENTER),
        "price_big_white": ParagraphStyle("pbw", fontName="Times-Bold", fontSize=18,
                                          textColor=WHITE, alignment=TA_CENTER),
        "price_label_white": ParagraphStyle("plw", fontName="Times-Roman", fontSize=9,
                                            textColor=WHITE, alignment=TA_CENTER),
    }


def _divider():
    return HRFlowable(width="100%", thickness=1, color=PINK, spaceAfter=8, spaceBefore=8)


def _fmt(val, prefix="", suffix="", fallback="—"):
    if val is None or val == "" or val == 0:
        return fallback
    try:
        if isinstance(val, float) and val == int(val):
            val = int(val)
        return f"{prefix}{val:,}{suffix}" if isinstance(val, (int, float)) else f"{prefix}{val}{suffix}"
    except Exception:
        return str(val)


# ── Section Builders ──────────────────────────────────────────────────────────

def _section_header(text, s):
    elems = [
        Paragraph(text.upper(), s["h1"]),
        HRFlowable(width="100%", thickness=2, color=PINK, spaceAfter=8),
    ]
    return elems


def _build_subject_overview(subject, s):
    elems = _section_header("Subject Property Overview", s)

    # ── Core fields — only include if non-zero / non-empty ───────────────────
    def _row(label, val):
        return [Paragraph(label, s["label"]), Paragraph(str(val), s["body"])]

    rows = []
    if subject.get("street_address"):
        rows.append(_row("Street Address", subject["street_address"]))
    if subject.get("city_state"):
        rows.append(_row("City / State", subject["city_state"]))
    if subject.get("property_type"):
        rows.append(_row("Property Type", subject["property_type"]))
    if subject.get("beds"):
        rows.append(_row("Bedrooms", _fmt(subject["beds"])))
    if subject.get("baths"):
        rows.append(_row("Bathrooms", _fmt(subject["baths"])))
    if subject.get("sqft"):
        rows.append(_row("Living Area", _fmt(subject["sqft"], suffix=" sq ft")))
    if subject.get("lot_acres"):
        rows.append(_row("Lot Size", _fmt(subject["lot_acres"], suffix=" acres")))
    if subject.get("year_built"):
        rows.append(_row("Year Built", _fmt(subject["year_built"])))
    if subject.get("garage"):
        rows.append(_row("Garage Spaces", _fmt(subject["garage"])))

    # ── New characteristic fields — only if set ───────────────────────────────
    fuel = subject.get("fuel_types", [])
    if fuel:
        rows.append(_row("Fuel Type(s)", ", ".join(fuel)))

    septic = subject.get("private_septic", "")
    if septic and septic != "— not specified —":
        rows.append(_row("Private Septic", septic))

    well = subject.get("private_well", "")
    if well and well != "— not specified —":
        rows.append(_row("Private Well", well))

    view = subject.get("view", "")
    if view and view != "— not specified —":
        rows.append(_row("View", view))

    solar = subject.get("solar", "")
    if solar and solar not in ("— not specified —", "No"):
        rows.append(_row("Solar", solar))
    elif solar == "No":
        rows.append(_row("Solar", "No"))

    if not rows:
        elems.append(Paragraph("No subject property details entered.", s["caption"]))
        return elems

    tbl = Table(rows, colWidths=[2.1 * inch, 4.4 * inch])
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [STEEL, LGRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 0), (0, -1), STEEL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(tbl)

    # ── Boundary notes (text block, not a table row) ──────────────────────────
    boundary = subject.get("boundary_notes", "").strip()
    if boundary:
        elems.append(Spacer(1, 8))
        elems.append(Paragraph("<b>Boundary Notes:</b>", s["label"]))
        elems.append(Paragraph(boundary, s["body_indent"]))

    # ── Features / Finishes ───────────────────────────────────────────────────
    features = subject.get("features_notes", "").strip()
    finishes = subject.get("finishes_note", "").strip()
    if features:
        elems.append(Spacer(1, 8))
        elems.append(Paragraph("<b>Notable Features:</b>", s["label"]))
        elems.append(Paragraph(features, s["body"]))
    if finishes:
        elems.append(Paragraph("<b>Quality of Finishes:</b>", s["label"]))
        elems.append(Paragraph(finishes, s["body"]))

    elems.append(Spacer(1, 12))
    return elems


def _build_price_recommendation(subject, comps, price_low, price_high, price_notes, s):
    elems = _section_header("Price Recommendation", s)

    mid = int((price_low + price_high) / 2)

    price_data = [[
        [Paragraph("Recommended Low", s["price_label"]),
         Paragraph(f"${price_low:,}", s["price_big"])],
        [Paragraph("Target List Price", s["price_label_white"]),
         Paragraph(f"${mid:,}", s["price_big_white"])],
        [Paragraph("Recommended High", s["price_label"]),
         Paragraph(f"${price_high:,}", s["price_big"])],
    ]]

    flat_data = [[
        Table([[Paragraph("Recommended Low", s["price_label"])],
               [Paragraph(f"${price_low:,}", s["price_big"])]], colWidths=[2.1*inch]),
        Table([[Paragraph("Target List Price", s["price_label_white"])],
               [Paragraph(f"${mid:,}", s["price_big_white"])]], colWidths=[2.1*inch]),
        Table([[Paragraph("Recommended High", s["price_label"])],
               [Paragraph(f"${price_high:,}", s["price_big"])]], colWidths=[2.1*inch]),
    ]]

    price_tbl = Table(flat_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    price_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), STEEL),
        ("BACKGROUND", (1, 0), (1, 0), NAVY),
        ("BACKGROUND", (2, 0), (2, 0), STEEL),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    elems.append(price_tbl)
    elems.append(Spacer(1, 12))

    # Comp analysis
    comp_prices = [c.get("sale_price") for c in comps[:3] if c.get("sale_price")]
    if comp_prices:
        avg = int(sum(comp_prices) / len(comp_prices))
        lo = min(comp_prices)
        hi = max(comp_prices)
        elems.append(Paragraph(
            f"<b>Comparable Sales Summary:</b>  Based on {len(comp_prices)} comparable sale(s), "
            f"the range was ${lo:,} – ${hi:,} with an average of ${avg:,}.",
            s["body"]))

    subj_sqft = subject.get("sqft")
    if subj_sqft and comp_prices:
        ppsf_list = [c["sale_price"] / c["sqft"] for c in comps[:3]
                     if c.get("sqft") and c.get("sale_price")]
        if ppsf_list:
            avg_ppsf = sum(ppsf_list) / len(ppsf_list)
            implied = int(avg_ppsf * subj_sqft)
            elems.append(Paragraph(
                f"<b>Price Per Sq Ft Analysis:</b>  Avg comp: ${avg_ppsf:.0f}/sq ft — "
                f"applied to {int(subj_sqft):,} sq ft implies ~${implied:,}.",
                s["body"]))

    if price_notes and price_notes.strip():
        elems.append(Paragraph(
            f"<b>Agent Pricing Notes:</b>  <i>{price_notes.strip()}</i>", s["body"]))

    elems.append(Spacer(1, 12))
    return elems


def _build_research_notes(subject, recommendations, s):
    elems = _section_header("Research Notes & Property Overview", s)

    beds  = subject.get("beds", "")
    baths = subject.get("baths", "")
    sqft  = subject.get("sqft", "")
    year  = subject.get("year_built", "")
    lot   = subject.get("lot_acres", "")
    prop_type = subject.get("property_type", "home")
    features = subject.get("features_notes", "")
    description = subject.get("description", "")

    parts = [p for p in [
        f"{int(beds)}-bedroom" if beds else "",
        f"{int(baths) if baths and float(baths)==int(float(baths)) else baths}-bathroom" if baths else "",
        f"{int(sqft):,} square foot" if sqft else "",
    ] if p]
    loc_parts = [p for p in [
        f"built in {int(year)}" if year else "",
        f"set on {lot} acres" if lot else "",
    ] if p]

    narrative = (
        f"This lovely {', '.join(parts)} {str(prop_type).lower()} "
        + (f"is {' and '.join(loc_parts)}" if loc_parts else "")
        + " and offers a wonderful opportunity in today's market."
    )
    if features:
        narrative += f" {features}"
    if description:
        sentences = description.replace("\n", " ").split(". ")
        excerpt = ". ".join(sentences[:2]).strip()
        if excerpt and len(excerpt) > 20:
            narrative += f" {excerpt}."

    elems.append(Paragraph(narrative, s["body"]))
    elems.append(Spacer(1, 8))

    rec_map = {
        "wait_spring": ("🌸 Wait for Spring",
            "Given current market conditions and the seasonal nature of Vermont real estate, "
            "we recommend waiting for spring to list. Inventory is lower and buyer activity "
            "is significantly higher between April and June, which typically supports stronger "
            "offers and shorter days on market."),
        "septic_inspection": ("🔍 Septic Inspection Recommended in Advance",
            "Vermont buyers frequently request septic inspections, and an unexpected failure "
            "can delay or derail a closing. We strongly recommend having the septic system "
            "professionally inspected prior to listing. A clean report is a powerful marketing "
            "tool and removes a major point of buyer uncertainty."),
        "home_inspection": ("🏠 Home Inspection Recommended in Advance",
            "A pre-listing home inspection allows you to identify and address issues on your "
            "own timeline and budget — rather than during contract negotiations. This builds "
            "buyer confidence and can help support your asking price."),
        "staging": ("🛋️ Staging Instructions",
            "First impressions are everything. Declutter all living spaces, depersonalize the "
            "home, ensure all rooms have adequate lighting, and add fresh flowers or plants to "
            "key areas. Consider a professional stager consultation for the main living areas."),
        "deep_clean": ("🧹 Deep Clean & Clear Out Recommended",
            "We recommend a professional deep clean prior to listing photography and showings. "
            "Pay particular attention to kitchens, bathrooms, windows, and floors. Clearing "
            "out attics, basements, and garages signals to buyers that the home has been well "
            "cared for and makes spaces appear larger."),
        "land_subdivision": ("📐 Land Subdivision Opportunity",
            "The lot size and configuration may present an opportunity for subdivision, which "
            "could significantly increase the overall value. We recommend consulting with a "
            "local surveyor and the town planning department before listing."),
        "painting_projects": ("🎨 Painting / Complete A Few Projects",
            "A fresh coat of neutral paint is one of the highest-return investments before "
            "listing. Address any visible deferred maintenance — peeling paint, cracked trim, "
            "or incomplete renovations — prior to going to market."),
    }

    if recommendations:
        elems.append(Paragraph("Agent Recommendations", s["h2"]))
        for key in recommendations:
            if key in rec_map:
                title, body = rec_map[key]
                elems.append(KeepTogether([
                    Paragraph(f"<b>{title}</b>", s["body"]),
                    Paragraph(body, s["body_indent"]),
                    Spacer(1, 4),
                ]))

    elems.append(Spacer(1, 12))
    return elems


def _build_agent_notes(subject, s):
    notes = subject.get("agent_notes", "").strip()
    if not notes:
        return []
    elems = _section_header("Agent Notes", s)
    elems.append(Paragraph(notes, s["body_indent"]))
    elems.append(Spacer(1, 12))
    return elems


def _build_anr_section(anr_url, s):
    """Build the ANR map reference section."""
    if not anr_url:
        return []
    elems = _section_header("Vermont ANR Natural Resource Map", s)
    elems.append(Paragraph(
        "The Vermont Agency of Natural Resources (ANR) Natural Resource Atlas provides detailed "
        "GIS mapping of wetlands, floodplains, soil types, conserved lands, Act 250 districts, "
        "and other environmental data relevant to this property.",
        s["body"],
    ))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph("<b>ANR Atlas Link for this property:</b>", s["label"]))
    elems.append(Spacer(1, 4))

    # Render URL in a shaded box so it stands out
    url_style = ParagraphStyle(
        "anr_url", fontName="Courier", fontSize=8, textColor=NAVY,
        backColor=STEEL, leftIndent=10, rightIndent=10,
        spaceBefore=4, spaceAfter=4, leading=12,
        borderPad=6,
    )
    elems.append(Paragraph(anr_url, url_style))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "<i>Open this link in any web browser to view the interactive ANR map for the subject property.</i>",
        s["caption"],
    ))
    elems.append(Spacer(1, 12))
    return elems


# ── Page Template (header/footer on every page) ───────────────────────────────

def _make_page_template(canvas, doc, logo_path):
    canvas.saveState()
    w, h = letter

    # Footer
    canvas.setFont("Times-Italic", 8)
    canvas.setFillColor(MGRAY)
    footer_text = (
        f"Hall Collins Real Estate Group  |  Comparative Market Analysis  |  "
        f"Confidential  |  {date.today().strftime('%B %Y')}"
    )
    canvas.drawCentredString(w / 2, 0.45 * inch, footer_text)

    # Footer rule
    canvas.setStrokeColor(PINK)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.6 * inch, w - 0.75 * inch, 0.6 * inch)

    # Page number
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColor(MGRAY)
    canvas.drawRightString(w - 0.75 * inch, 0.3 * inch, f"Page {doc.page}")

    canvas.restoreState()


# ── Master Build ──────────────────────────────────────────────────────────────

def _build_cma_pdf_bytes(subject, comps, recommendations,
                          price_low, price_high, price_notes,
                          logo_path, anr_url=None) -> bytes:
    """Render the CMA content pages as a PDF and return bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch,
    )

    s = _styles()
    story = []

    # Property overview
    story += _build_subject_overview(subject, s)
    story.append(_divider())

    # Research notes + recommendations
    story += _build_research_notes(subject, recommendations, s)
    story.append(_divider())

    # Agent notes
    agent_notes_elems = _build_agent_notes(subject, s)
    if agent_notes_elems:
        story += agent_notes_elems
        story.append(_divider())

    # ANR Map section
    anr_elems = _build_anr_section(anr_url, s)
    if anr_elems:
        story += anr_elems
        story.append(_divider())

    # Price recommendation
    story += _build_price_recommendation(subject, comps, price_low, price_high, price_notes, s)

    def _footer(canvas, doc):
        _make_page_template(canvas, doc, logo_path)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf.read()


def merge_cma_pdf(subject, comps, recommendations,
                   price_low, price_high, price_notes,
                   logo_path="hall_collins_logo.png",
                   anr_url=None,
                   supplemental_pdf_bytes=None,
                   anr_pdf_bytes=None) -> bytes:
    """
    Build and merge the final CMA PDF:
      1. HC Cover Page         (always fixed)
      2. CMA Content           (built with ReportLab)
      3. Other CMA PDF         (pages 1–2 stripped), if provided
      4. ANR Map PDF           (appended as-is), if provided

    Returns merged PDF as bytes.
    """
    writer = PdfWriter()

    # ── 1. HC Cover Page ──────────────────────────────────────────────────────
    if not os.path.exists(COVER_PDF_PATH):
        raise FileNotFoundError(
            f"Cover PDF not found: '{COVER_PDF_PATH}'\n"
            "Make sure it is in the same folder as the app."
        )
    cover_reader = PdfReader(COVER_PDF_PATH)
    for page in cover_reader.pages:
        writer.add_page(page)

    # ── 2. CMA Content ────────────────────────────────────────────────────────
    cma_bytes = _build_cma_pdf_bytes(
        subject, comps, recommendations,
        price_low, price_high, price_notes,
        logo_path, anr_url=None,
    )
    cma_reader = PdfReader(io.BytesIO(cma_bytes))
    for page in cma_reader.pages:
        writer.add_page(page)

    # ── 3. Other CMA PDF (strip pages 1 & 2) ─────────────────────────────────
    if supplemental_pdf_bytes:
        supp_reader = PdfReader(io.BytesIO(supplemental_pdf_bytes))
        for page in list(supp_reader.pages)[2:]:
            writer.add_page(page)

    # ── 4. ANR Map PDF (append as-is) ────────────────────────────────────────
    if anr_pdf_bytes:
        anr_reader = PdfReader(io.BytesIO(anr_pdf_bytes))
        for page in anr_reader.pages:
            writer.add_page(page)

    # ── Output ────────────────────────────────────────────────────────────────
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()
