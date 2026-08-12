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
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
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
                               textColor=DGRAY, spaceAfter=6, leading=14,
                               alignment=TA_JUSTIFY),
        "body_indent": ParagraphStyle("body_indent", fontName="Times-Roman",
                                      fontSize=10, textColor=DGRAY,
                                      spaceAfter=6, leading=14, leftIndent=18,
                                      alignment=TA_JUSTIFY),
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
        rows.append(_row("Year Built", str(int(subject["year_built"]))))
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


def _build_price_recommendation(subject, comps, price_low, price_high, price_rec, price_notes, s):
    elems = [PageBreak()]
    elems += _section_header("Price Recommendation", s)

    # ── Visual price scale ────────────────────────────────────────────────────
    from reportlab.graphics.shapes import Drawing, Rect, Polygon, String
    from reportlab.graphics import renderPDF

    bar_w = 7.0 * inch
    bar_h = 32
    draw_h = bar_h + 20   # a little breathing room above bar
    d = Drawing(bar_w, draw_h)

    bar_y = 10  # bar sits above bottom of drawing

    # Gradient bar segments (low=steel → mid=pink → high=navy)
    segments = 80
    seg_w = bar_w / segments
    for i in range(segments):
        t = i / segments
        if t < 0.5:
            t2 = t * 2
            r = int(0xEE + (0xE9 - 0xEE) * t2)
            g = int(0xF1 + (0x1E - 0xF1) * t2)
            b = int(0xF4 + (0x63 - 0xF4) * t2)
        else:
            t2 = (t - 0.5) * 2
            r = int(0xE9 + (0x17 - 0xE9) * t2)
            g = int(0x1E + (0x33 - 0x1E) * t2)
            b = int(0x63 + (0x48 - 0x63) * t2)
        seg_color = colors.Color(r/255, g/255, b/255)
        d.add(Rect(i * seg_w, bar_y, seg_w + 0.5, bar_h,
                   fillColor=seg_color, strokeColor=None))

    # Arrow marker pointing down from above the bar at recommended price
    if price_high > price_low:
        ratio = (price_rec - price_low) / (price_high - price_low)
    else:
        ratio = 0.5
    ratio = max(0.02, min(0.98, ratio))
    arrow_x = ratio * bar_w
    arrow_top = bar_y + bar_h + 14   # tip of triangle points down to top of bar
    arrow_base = bar_y + bar_h + 1
    d.add(Polygon(
        [arrow_x - 7, arrow_top,
         arrow_x + 7, arrow_top,
         arrow_x, arrow_base],
        fillColor=colors.HexColor("#173348"),
        strokeColor=None,
    ))

    elems.append(Spacer(1, 8))
    elems.append(d)
    elems.append(Spacer(1, 4))

    # ── Price range labels below bar ─────────────────────────────────────────
    range_data = [[
        Paragraph(f"<b>${price_low:,}</b>",
                  ParagraphStyle("pr_left", fontName="Times-Bold", fontSize=11,
                                 textColor=colors.HexColor("#555555"))),
        Paragraph(f"<b>${price_high:,}</b>",
                  ParagraphStyle("pr_right", fontName="Times-Bold", fontSize=11,
                                 textColor=colors.HexColor("#555555"), alignment=TA_RIGHT)),
    ]]
    range_tbl = Table(range_data, colWidths=[3.5*inch, 3.5*inch])
    range_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(range_tbl)
    elems.append(Spacer(1, 8))

    # ── "Why is there a range?" explanation ──────────────────────────────────
    why_header_style = ParagraphStyle(
        "why_h", fontName="Times-Bold", fontSize=11,
        textColor=NAVY, spaceAfter=4, spaceBefore=2,
    )
    why_body_style = ParagraphStyle(
        "why_body", fontName="Times-Roman", fontSize=10,
        textColor=DGRAY, leading=14, alignment=TA_JUSTIFY, spaceAfter=6,
    )
    elems.append(Paragraph("Why is there a range?", why_header_style))
    elems.append(Paragraph(
        "Pricing is an art, not a science. We believe any sale is a team effort between us as your "
        "agents and you as the seller. The more prepared you are, the higher the price you can generate "
        "and vice versa. If you would prefer to sell it without the hassle, we need to price it "
        "accordingly to keep those projects in mind.",
        why_body_style))

    # ── Condition notes stacked ───────────────────────────────────────────────
    condition_style = ParagraphStyle(
        "cond", fontName="Times-Roman", fontSize=9,
        textColor=colors.HexColor("#444444"), leading=13,
        alignment=TA_JUSTIFY, leftIndent=8, spaceAfter=4,
    )
    elems.append(Paragraph(
        f"<b>${price_low:,} — As-Is:</b>  <i>Property sold in current condition, "
        "not cleaned out, not in photo-ready condition.</i>",
        condition_style))
    elems.append(Paragraph(
        f"<b>${price_high:,} — Instagram-Worthy:</b>  <i>Top-notch condition, full inspection "
        "reports on hand, smoke detectors up to date, exceptionally clean, no smell of animals.</i>",
        condition_style))
    elems.append(Spacer(1, 18))

    # ── Prominent recommended price display ───────────────────────────────────
    rec_style = ParagraphStyle(
        "rec_price", fontName="Times-Bold", fontSize=17,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=4,
    )
    rec_sub_style = ParagraphStyle(
        "rec_sub", fontName="Times-Italic", fontSize=9,
        textColor=MGRAY, alignment=TA_CENTER, spaceAfter=10,
    )
    elems.append(Paragraph(f"Our Recommended List Price: ${price_rec:,}", rec_style))
    elems.append(HRFlowable(width="60%", thickness=0.5, color=PINK, spaceAfter=6, spaceBefore=6, hAlign="CENTER"))
    elems.append(Paragraph("Based on current market conditions", rec_sub_style))
    elems.append(Spacer(1, 14))

    # ── Agent pricing notes ───────────────────────────────────────────────────
    if price_notes and price_notes.strip():
        elems.append(Paragraph(
            f"<b>Agent Pricing Notes:</b>  <i>{price_notes.strip()}</i>", s["body"]))
        elems.append(Spacer(1, 8))

    # ── Firm philosophy note ──────────────────────────────────────────────────
    philosophy_style = ParagraphStyle(
        "philosophy", fontName="Times-Italic", fontSize=9,
        textColor=NAVY,
        leftIndent=0, rightIndent=0,
        spaceBefore=4, spaceAfter=4, leading=14,
        alignment=TA_JUSTIFY,
    )
    elems.append(Paragraph(
        "We pride ourselves in our firm that we don't attempt to inflate the value to win the listing. "
        "This is where we earnestly feel as though the property will settle on the market. We are not "
        "perfect and this is not an exact science, but we want to work together with you as a team. "
        "We love what we do and we want you to have as seamless of an experience as possible!",
        philosophy_style,
    ))
    elems.append(Spacer(1, 12))
    return elems


def _build_research_notes(subject, recommendations, s):
    elems = _section_header("Agent Recommendations", s)

    rec_map = {
        "wait_spring": ("🌸 Wait for Spring",
            "We will support you whenever you choose to list, but in this case we would recommend "
            "waiting until April/May depending on the weather. Historically homes sell for a little "
            "more and more buyers are shopping to get in for the summer and prior to the new school "
            "year. Any time April–October is a strong time."),
        "septic_inspection": ("🔍 Septic Inspection Recommended in Advance",
            "Because a septic system is hidden underground, it's naturally one of those big mystery "
            "areas that makes buyers extra cautious. If they don't know what they are getting into, "
            "they will inspect it the majority of the time and if there are any problems it can derail "
            "the whole sale. Coming in to the transaction knowing what condition it is in can make you, "
            "as the seller, look extremely thoughtful and prepared as well as relieve any anxiety the "
            "buyer may have. It's actually one of the top reasons deals fall through or homes end up "
            "back on the market. By inspecting it early, you take all the guesswork off the table so "
            "you can price with confidence and avoid last-minute negotiation surprises. We can easily "
            "connect you with a few local inspectors. This is one of the best ways to set yourself up "
            "for a smooth, stress-free sale!"),
        "home_inspection": ("🏠 Home Inspection Recommended in Advance",
            "A pre-listing home inspection allows you to identify and address issues on your "
            "own timeline and budget — rather than during contract negotiations. This builds "
            "buyer confidence and can help support your asking price."),
        "staging": ("🛋️ Staging Instructions",
            "First impressions are everything. Declutter all living spaces, depersonalize the "
            "home, ensure all rooms have adequate lighting, and add fresh flowers or plants to "
            "key areas. At a minimum all surfaces should be cleared, plastic hidden away, any "
            "excess clutter gone. We almost want to make a space look boring so people can start "
            "to envision where they would place their own items."),
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
        for key in recommendations:
            if key in rec_map:
                title, body = rec_map[key]
                # Strip leading emoji (everything up to and including first space after emoji)
                import re as _re
                clean_title = _re.sub(r'^[\U00010000-\U0010ffff\u2000-\u3300\u00a9-\u00ae]\S*\s*', '', title).strip()
                bullet_title_style = ParagraphStyle(
                    "rec_title", fontName="Times-Bold", fontSize=11,
                    textColor=PINK, leading=15, leftIndent=0,
                    spaceAfter=1, spaceBefore=6,
                )
                body_style = ParagraphStyle(
                    "rec_body", fontName="Times-Roman", fontSize=10,
                    textColor=DGRAY, leading=14, leftIndent=12,
                    alignment=TA_JUSTIFY, spaceAfter=2,
                )
                elems.append(KeepTogether([
                    Paragraph(f"\u2022  <b>{clean_title}</b>", bullet_title_style),
                    Paragraph(body, body_style),
                    Spacer(1, 2),
                ]))

    elems.append(Spacer(1, 12))
    return elems


def _build_agent_notes(subject, s):
    notes = subject.get("agent_notes", "").strip()
    if not notes:
        return []
    elems = _section_header("Agent Notes", s)
    # Split on blank lines to preserve paragraph breaks
    paragraphs = [p.strip() for p in notes.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [notes]
    for para in paragraphs:
        # Within each paragraph, replace single newlines with a space
        text = para.replace("\n", " ")
        elems.append(Paragraph(text, s["body_indent"]))
        elems.append(Spacer(1, 6))
    elems.append(Spacer(1, 6))
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

    # Logo in footer (left side)
    if logo_path and os.path.exists(logo_path):
        try:
            logo_h = 0.45 * inch
            logo_w = logo_h * 3.5  # approximate aspect ratio
            canvas.drawImage(logo_path, 0.75 * inch, 0.18 * inch,
                             width=logo_w, height=logo_h,
                             preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    # Footer rule
    canvas.setStrokeColor(PINK)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.72 * inch, w - 0.75 * inch, 0.72 * inch)

    # Footer — main line
    canvas.setFont("Times-Italic", 9)
    canvas.setFillColor(MGRAY)
    footer_text = (
        f"Comparative Market Analysis  |  "
        f"Confidential  |  {date.today().strftime('%B %Y')}"
    )
    canvas.drawCentredString(w / 2, 0.5 * inch, footer_text)

    # Page number
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColor(MGRAY)
    canvas.drawRightString(w - 0.75 * inch, 0.27 * inch, f"Page {doc.page}")

    canvas.restoreState()


# ── Master Build ──────────────────────────────────────────────────────────────

def _build_cma_pdf_bytes(subject, comps, recommendations,
                          price_low, price_high, price_rec,
                          price_notes, logo_path, anr_url=None) -> bytes:
    """Render the CMA content pages as a PDF and return bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=1.0 * inch,
    )

    s = _styles()
    story = []

    # Property overview
    story += _build_subject_overview(subject, s)
    story.append(_divider())

    # Recommendations
    story += _build_research_notes(subject, recommendations, s)
    story.append(_divider())

    # ANR Map section
    anr_elems = _build_anr_section(anr_url, s)
    if anr_elems:
        story += anr_elems
        story.append(_divider())

    # Price recommendation (starts on new page)
    story += _build_price_recommendation(subject, comps, price_low, price_high, price_rec, price_notes, s)

    # Agent notes — after pricing
    agent_notes_elems = _build_agent_notes(subject, s)
    if agent_notes_elems:
        story.append(_divider())
        story += agent_notes_elems

    def _footer(canvas, doc):
        _make_page_template(canvas, doc, logo_path)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf.read()


def merge_cma_pdf(subject, comps, recommendations,
                   price_low, price_high, price_rec,
                   price_notes,
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
        price_low, price_high, price_rec,
        price_notes, logo_path, anr_url=None,
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
