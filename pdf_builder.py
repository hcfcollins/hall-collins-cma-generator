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
        "organize_leases": ("Organize Leases & Tenant Documents",
            "Buyers and their attorneys will want to review all existing leases, rent rolls, "
            "and any written agreements with tenants before closing. We recommend gathering "
            "all signed lease agreements, security deposit records, and any written notices "
            "into a single folder now. Being organized and transparent with this documentation "
            "builds buyer confidence, speeds up due diligence, and can prevent deal-killing "
            "surprises during the contract period."),
        "evict_tenants": ("Consider Evicting Tenants Before Listing",
            "In some cases, the strongest move before listing is to start with a clean slate. "
            "This is especially true when current rents are significantly below market — "
            "a buyer inheriting a long-term tenant at $800/month on a unit worth $1,400/month "
            "is effectively buying a discounted income stream with limited near-term upside. "
            "Listing the unit vacant allows a new owner to set market rents immediately, "
            "which can meaningfully increase the property's value and the buyer pool. "
            "It may also apply when there are lease violations, non-payment history, or "
            "month-to-month situations where a clean transition serves everyone's interests. "
            "We recommend consulting with a local attorney about notice requirements and "
            "timing before proceeding."),
        "system_repairs": ("Make Repairs to Major Systems",
            "Buyers of investment properties pay close attention to the condition and age of "
            "major systems — heating, plumbing, electrical, and roofing. Known deferred "
            "maintenance on these items will be flagged in inspections and used as negotiating "
            "leverage. We recommend addressing any urgent repairs — particularly to heating "
            "systems, water heaters, and roofing — before listing. Even partial repairs or "
            "documented service records go a long way toward supporting your asking price and "
            "reducing buyer hesitation."),
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

def _build_cap_rate_analysis(subject, price_rec, s):
    """Build a cap rate analysis section for multi-family properties."""
    elems = []
    elems += _section_header("Multi-Family Income & Cap Rate Analysis", s)

    units        = subject.get("mf_units", 0)
    unit_rents   = subject.get("mf_unit_rents", [])   # list of {label, current, market}
    rent_pu      = subject.get("mf_rent_per_unit", 0)      # avg fallback
    mkt_rent_pu  = subject.get("mf_market_rent_per_unit", rent_pu)
    vacancy      = subject.get("mf_vacancy_pct", 5.0)
    taxes        = subject.get("mf_taxes", 0)
    insurance    = subject.get("mf_insurance", 0)
    maintenance  = subject.get("mf_maintenance", 0)
    reserve_pct  = float(subject.get("mf_reserve_pct", 5.0))
    base_expenses = subject.get("mf_base_expenses", taxes + insurance + maintenance)

    gross_cur   = subject.get("mf_gross_income", 0)
    eff_cur     = subject.get("mf_eff_gross", gross_cur * (1 - vacancy / 100))

    gross_mkt   = subject.get("mf_gross_income_mkt", 0)
    eff_mkt     = subject.get("mf_eff_gross_mkt", gross_mkt * (1 - vacancy / 100))

    reserve_cur  = subject.get("mf_reserve_cur", round(gross_cur * reserve_pct / 100))
    reserve_mkt  = subject.get("mf_reserve_mkt", round(gross_mkt * reserve_pct / 100))
    expenses     = subject.get("mf_total_expenses", base_expenses + reserve_cur)

    noi_cur     = subject.get("mf_noi", eff_cur - expenses)
    cap_cur     = subject.get("mf_cap_rate", (noi_cur / price_rec * 100) if price_rec else 0)

    noi_mkt     = subject.get("mf_noi_mkt", eff_mkt - (base_expenses + reserve_mkt))
    cap_mkt     = subject.get("mf_cap_rate_mkt", (noi_mkt / price_rec * 100) if price_rec else 0)
    has_market  = gross_mkt != gross_cur and gross_mkt > 0

    def _money(v):
        try:
            return f"${v:,.0f}"
        except Exception:
            return str(v)

    def _rp(text, align=TA_RIGHT, bold=False, color=DGRAY, size=10):
        fn = "Times-Bold" if bold else "Times-Roman"
        return Paragraph(text, ParagraphStyle("_rp", fontName=fn, fontSize=size,
                                              textColor=color, alignment=align))

    # ── Per-unit rent table ───────────────────────────────────────────────────
    if unit_rents:
        elems.append(Paragraph("Rent by Unit", ParagraphStyle(
            "unit_hdr", fontName="Times-Bold", fontSize=10, textColor=NAVY,
            spaceAfter=4, spaceBefore=4)))

        if has_market:
            u_col_w = [0.5*inch, 2.4*inch, 1.5*inch, 1.5*inch, 0.7*inch]
            u_header = [
                Paragraph("<b>#</b>", s["label"]),
                Paragraph("<b>Unit Description</b>", s["label"]),
                _rp("<b>Current Rent/mo</b>", bold=True, color=WHITE, align=TA_CENTER),
                _rp("<b>Market Rent/mo</b>", bold=True, color=WHITE, align=TA_CENTER),
                _rp("<b>Δ/mo</b>", bold=True, color=WHITE, align=TA_CENTER),
            ]
        else:
            u_col_w = [0.5*inch, 3.0*inch, 2.5*inch]
            u_header = [
                Paragraph("<b>#</b>", s["label"]),
                Paragraph("<b>Unit Description</b>", s["label"]),
                _rp("<b>Current Rent/mo</b>", bold=True, color=WHITE, align=TA_CENTER),
            ]

        u_rows = [u_header]
        for i, u in enumerate(unit_rents):
            cur = u.get("current", 0)
            mkt = u.get("market", 0)
            diff = mkt - cur
            diff_color = PINK if diff > 0 else (colors.HexColor("#2e7d32") if diff == 0 else colors.HexColor("#c62828"))
            lbl = u.get("label", f"Unit {i+1}")
            if has_market:
                u_rows.append([
                    _rp(str(i+1), align=TA_CENTER, color=NAVY),
                    Paragraph(lbl, s["body"]),
                    _rp(_money(cur), align=TA_CENTER, color=DGRAY),
                    _rp(_money(mkt), align=TA_CENTER, color=PINK if diff > 0 else DGRAY),
                    _rp(f"{diff:+,.0f}", align=TA_CENTER, bold=True, color=diff_color),
                ])
            else:
                u_rows.append([
                    _rp(str(i+1), align=TA_CENTER, color=NAVY),
                    Paragraph(lbl, s["body"]),
                    _rp(_money(cur), align=TA_CENTER, color=DGRAY),
                ])

        # Totals row
        total_cur = sum(u.get("current", 0) for u in unit_rents)
        total_mkt = sum(u.get("market", 0) for u in unit_rents)
        total_diff = total_mkt - total_cur
        if has_market:
            u_rows.append([
                Paragraph("", s["body"]),
                _rp("<b>Total Monthly</b>", bold=True, color=NAVY, align=TA_RIGHT),
                _rp(f"<b>{_money(total_cur)}</b>", bold=True, color=NAVY, align=TA_CENTER),
                _rp(f"<b>{_money(total_mkt)}</b>", bold=True, color=PINK, align=TA_CENTER),
                _rp(f"<b>{total_diff:+,.0f}</b>", bold=True,
                    color=PINK if total_diff > 0 else DGRAY, align=TA_CENTER),
            ])
        else:
            u_rows.append([
                Paragraph("", s["body"]),
                _rp("<b>Total Monthly</b>", bold=True, color=NAVY, align=TA_RIGHT),
                _rp(f"<b>{_money(total_cur)}</b>", bold=True, color=NAVY, align=TA_CENTER),
            ])

        u_tbl = Table(u_rows, colWidths=u_col_w)
        u_style = [
            ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [WHITE, LGRAY]),
            ("BACKGROUND",    (0, -1), (-1, -1), BLUSH),
            ("LINEABOVE",     (0, -1), (-1, -1), 1, PINK),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]
        if has_market:
            u_style += [("BACKGROUND", (3, 1), (3, -2), colors.HexColor("#FFF0F5"))]
        u_tbl.setStyle(TableStyle(u_style))
        elems.append(u_tbl)

        # ── Included-in-rent utilities ────────────────────────────────────
        _util_icons = {
            "Electric": "Electric", "Heat": "Heat", "Plowing": "Plowing",
            "Mowing": "Mowing", "Trash": "Trash", "Internet": "Internet",
        }
        _included = subject.get("mf_included_utilities", [])
        if _included:
            _badge_text = "  ·  ".join(_util_icons.get(u, u) for u in _included)
            elems.append(Paragraph(
                f"<b>Included in rent:</b>  {_badge_text}",
                ParagraphStyle("_util", fontName="Times-Roman", fontSize=9,
                               textColor=colors.HexColor("#2e7d32"),
                               backColor=colors.HexColor("#F1F8E9"),
                               borderPadding=(4, 8, 4, 8), spaceAfter=6,
                               leftIndent=2, rightIndent=2)
            ))
        else:
            elems.append(Paragraph(
                "<i>No utilities included in rent.</i>",
                ParagraphStyle("_util_none", fontName="Times-Italic", fontSize=9,
                               textColor=DGRAY, spaceAfter=6)
            ))
        elems.append(Spacer(1, 6))

    # ── Income/expense summary table ──────────────────────────────────────────
    if has_market:
        col_w = [2.9 * inch, 1.7 * inch, 1.7 * inch]
        header = [
            Paragraph("<b>Income &amp; Expense Summary</b>", s["label"]),
            _rp("<b>Current Rents</b>", bold=True, color=WHITE),
            _rp("<b>Market Rents</b>", bold=True, color=WHITE),
        ]
        def _row(label, cur_val, mkt_val, bold=False):
            return [
                Paragraph(f"<b>{label}</b>" if bold else label, s["body"]),
                _rp(f"<b>{cur_val}</b>" if bold else cur_val, bold=bold,
                    color=NAVY if bold else DGRAY),
                _rp(f"<b>{mkt_val}</b>" if bold else mkt_val, bold=bold,
                    color=PINK if bold else colors.HexColor("#C2185B")),
            ]
    else:
        col_w = [3.5 * inch, 2.5 * inch]
        header = [
            Paragraph("<b>Income &amp; Expense Summary</b>", s["label"]),
            _rp("<b>Annual Amount</b>", bold=True, color=WHITE),
        ]
        def _row(label, cur_val, mkt_val=None, bold=False):
            return [
                Paragraph(f"<b>{label}</b>" if bold else label, s["body"]),
                _rp(f"<b>{cur_val}</b>" if bold else cur_val, bold=bold,
                    color=NAVY if bold else DGRAY),
            ]

    table_data = [
        header,
        _row("Gross Annual Rent",
             _money(gross_cur), _money(gross_mkt)),
        _row(f"Less Vacancy ({vacancy:.1f}%)",
             f"({_money(gross_cur - eff_cur)})", f"({_money(gross_mkt - eff_mkt)})"),
        _row("Effective Gross Income",
             _money(eff_cur), _money(eff_mkt), bold=True),
        _row("Property Taxes",
             _money(taxes), _money(taxes)),
        _row("Insurance",
             _money(insurance), _money(insurance)),
        _row("Maintenance &amp; Other",
             _money(maintenance), _money(maintenance)),
        _row(f"Capital Reserve ({reserve_pct:.0f}% of gross — roof/HVAC/appliances)",
             f"({_money(reserve_cur)})", f"({_money(reserve_mkt)})"),
        _row("Total Operating Expenses",
             f"({_money(expenses)})", f"({_money(base_expenses + reserve_mkt)})", bold=True),
        _row("Net Operating Income (NOI)",
             _money(noi_cur), _money(noi_mkt), bold=True),
    ]

    n_cols = 3 if has_market else 2
    tbl = Table(table_data, colWidths=col_w)
    tbl_style = [
        ("BACKGROUND",    (0, 0), (-1, 0),   NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),   WHITE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),  [WHITE, LGRAY]),
        ("BACKGROUND",    (0, -1), (-1, -1), BLUSH),
        ("LINEBELOW",     (0, -1), (-1, -1), 1.5, PINK),
        ("LINEABOVE",     (0, -1), (-1, -1), 1.5, PINK),
        ("TOPPADDING",    (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
        ("LEFTPADDING",   (0, 0), (-1, -1),  8),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  8),
    ]
    if has_market:
        # Soft pink tint on market rent column
        tbl_style += [
            ("BACKGROUND", (2, 1), (2, -2), colors.HexColor("#FFF0F5")),
            ("BACKGROUND", (2, -1), (2, -1), colors.HexColor("#FCE4EC")),
        ]
    tbl.setStyle(TableStyle(tbl_style))
    elems.append(tbl)
    elems.append(Spacer(1, 14))

    # ── Cap rate callout box ──────────────────────────────────────────────────
    if has_market:
        # Two cap rates side by side
        diff = cap_mkt - cap_cur
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
        cap_data = [
            [_rp("Recommended Price", align=TA_CENTER, color=NAVY),
             _rp("Cap Rate — Current Rents", align=TA_CENTER, color=WHITE),
             _rp("Cap Rate — Market Rents", align=TA_CENTER, color=WHITE),
             _rp("Upside", align=TA_CENTER, color=WHITE)],
            [_rp(f"<b>{_money(price_rec)}</b>", align=TA_CENTER, bold=True, color=NAVY, size=14),
             _rp(f"<b>{cap_cur:.2f}%</b>", align=TA_CENTER, bold=True, color=WHITE, size=16),
             _rp(f"<b>{cap_mkt:.2f}%</b>", align=TA_CENTER, bold=True, color=WHITE, size=16),
             _rp(f"<b>{diff_str}</b>", align=TA_CENTER, bold=True, color=WHITE, size=14)],
        ]
        cap_tbl = Table(cap_data, colWidths=[1.8*inch, 1.7*inch, 1.7*inch, 1.0*inch])
        cap_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), BLUSH),
            ("BACKGROUND",    (1, 0), (1, -1), NAVY),
            ("BACKGROUND",    (2, 0), (2, -1), PINK),
            ("BACKGROUND",    (3, 0), (3, -1), colors.HexColor("#C2185B")),
            ("LINEBELOW",     (0, 0), (-1, 0), 0.5, colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("BOX",           (0, 0), (-1, -1), 1.5, PINK),
            ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.white),
        ]))
        elems.append(KeepTogether([cap_tbl]))
        elems.append(Spacer(1, 6))
        elems.append(Paragraph(
            f"<i>At market rents totaling {_money(gross_mkt / 12)}/month, the projected cap rate "
            f"would be <b>{cap_mkt:.2f}%</b> — an increase of {diff_str} over the current "
            f"cap rate of <b>{cap_cur:.2f}%</b>.</i>",
            s["body"]
        ))
    else:
        # Single cap rate callout
        cap_data = [
            [_rp("Recommended Price", align=TA_CENTER, color=NAVY),
             _rp("Net Operating Income", align=TA_CENTER, color=NAVY),
             _rp("Cap Rate", align=TA_CENTER, color=WHITE)],
            [_rp(f"<b>{_money(price_rec)}</b>", align=TA_CENTER, bold=True, color=NAVY, size=15),
             _rp(f"<b>{_money(noi_cur)}</b>", align=TA_CENTER, bold=True, color=NAVY, size=15),
             _rp(f"<b>{cap_cur:.2f}%</b>", align=TA_CENTER, bold=True, color=WHITE, size=18)],
        ]
        cap_tbl = Table(cap_data, colWidths=[2.2*inch, 2.2*inch, 1.6*inch])
        cap_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (1, -1), BLUSH),
            ("BACKGROUND",    (2, 0), (2, -1), PINK),
            ("LINEBELOW",     (0, 0), (-1, 0), 0.5, PINK),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("BOX",           (0, 0), (-1, -1), 1.5, PINK),
            ("INNERGRID",     (0, 0), (-1, -1), 0.5, PINK),
        ]))
        elems.append(KeepTogether([cap_tbl]))

    elems.append(Spacer(1, 8))
    elems.append(Paragraph(
        "<i>Cap rate = NOI ÷ Recommended Price. This is an estimate based on provided figures "
        "and should not substitute a full investment analysis or professional appraisal.</i>",
        s["caption"]
    ))

    # ── Financing section (optional) ──────────────────────────────────────────
    show_financing = subject.get("mf_show_financing", False)
    if show_financing:
        down_pct   = float(subject.get("mf_down_pct", 25.0))
        rate       = float(subject.get("mf_interest_rate", 7.0))
        term_yrs   = int(subject.get("mf_loan_term_yrs", 30))
        down_amt   = subject.get("mf_down_amt", 0)
        loan_amt   = subject.get("mf_loan_amt", 0)
        monthly_pmt= subject.get("mf_monthly_payment", 0)
        annual_ds  = subject.get("mf_annual_debt_service", 0)
        cf_cur     = subject.get("mf_cf_cur", 0)
        cf_mkt     = subject.get("mf_cf_mkt", 0)
        coc_cur    = subject.get("mf_coc_cur", 0)
        coc_mkt    = subject.get("mf_coc_mkt", 0)

        GREEN = colors.HexColor("#2e7d32")
        RED   = colors.HexColor("#c62828")

        def _cf_color(val):
            return GREEN if val >= 0 else RED

        elems.append(Spacer(1, 10))
        elems.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=6))
        elems.append(Paragraph(
            f"FINANCING SCENARIO — {down_pct:.0f}% Down @ {rate:.3f}% Interest, {term_yrs}-Year Term",
            ParagraphStyle("fin_hdr", fontName="Times-Bold", fontSize=11,
                           textColor=NAVY, spaceAfter=4)
        ))

        # Financing summary table
        if has_market:
            fin_col_w = [2.9*inch, 1.7*inch, 1.7*inch]
            fin_header = [
                Paragraph("<b>Item</b>", s["label"]),
                _rp("<b>Current Rents</b>", bold=True, color=WHITE),
                _rp("<b>Market Rents</b>", bold=True, color=WHITE),
            ]
            def _fin_row(label, cur_val, mkt_val, bold=False, cur_color=DGRAY, mkt_color=None):
                mkt_color = mkt_color or cur_color
                return [
                    Paragraph(f"<b>{label}</b>" if bold else label, s["body"]),
                    _rp(f"<b>{cur_val}</b>" if bold else cur_val, bold=bold, color=cur_color),
                    _rp(f"<b>{mkt_val}</b>" if bold else mkt_val, bold=bold, color=mkt_color),
                ]
        else:
            fin_col_w = [3.5*inch, 2.5*inch]
            fin_header = [
                Paragraph("<b>Item</b>", s["label"]),
                _rp("<b>Amount</b>", bold=True, color=WHITE),
            ]
            def _fin_row(label, cur_val, mkt_val=None, bold=False, cur_color=DGRAY, mkt_color=None):
                return [
                    Paragraph(f"<b>{label}</b>" if bold else label, s["body"]),
                    _rp(f"<b>{cur_val}</b>" if bold else cur_val, bold=bold, color=cur_color),
                ]

        fin_data = [
            fin_header,
            _fin_row("Purchase Price",       _money(price_rec),  _money(price_rec)),
            _fin_row(f"Down Payment ({down_pct:.0f}%)", _money(down_amt), _money(down_amt)),
            _fin_row("Loan Amount",          _money(loan_amt),   _money(loan_amt),  bold=True, cur_color=NAVY),
            _fin_row(f"Monthly Payment ({rate:.3f}%, {term_yrs} yrs)",
                                             _money(monthly_pmt), _money(monthly_pmt)),
            _fin_row("Annual Debt Service",  f"({_money(annual_ds)})", f"({_money(annual_ds)})",
                     bold=True, cur_color=NAVY),
            _fin_row("NOI",                  _money(noi_cur),    _money(noi_mkt),
                     cur_color=NAVY, mkt_color=PINK if has_market else NAVY),
            _fin_row("Cash Flow After Financing",
                     _money(cf_cur), _money(cf_mkt),
                     bold=True,
                     cur_color=_cf_color(cf_cur),
                     mkt_color=_cf_color(cf_mkt)),
            _fin_row(f"Cash-on-Cash Return (on {_money(down_amt)} down)",
                     f"{coc_cur:.2f}%", f"{coc_mkt:.2f}%",
                     bold=True,
                     cur_color=_cf_color(coc_cur),
                     mkt_color=_cf_color(coc_mkt)),
        ]

        fin_tbl = Table(fin_data, colWidths=fin_col_w)
        fin_style = [
            ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LGRAY]),
            ("BACKGROUND",    (0, -2), (-1, -1), BLUSH),
            ("LINEABOVE",     (0, -2), (-1, -2), 1.5, NAVY),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ]
        if has_market:
            fin_style += [
                ("BACKGROUND", (2, 1), (2, -3), colors.HexColor("#FFF0F5")),
                ("BACKGROUND", (2, -2), (2, -1), colors.HexColor("#FCE4EC")),
            ]
        fin_tbl.setStyle(TableStyle(fin_style))
        elems.append(fin_tbl)
        elems.append(Spacer(1, 10))

        # ── Bank financing callout note ────────────────────────────────────
        note_tbl = Table(
            [[Paragraph(
                "<b>Important Note on Bank Financing</b><br/>"
                "Commercial lenders typically require <b>a minimum of two years of documented "
                "operating history</b> (rent rolls, tax returns, profit &amp; loss statements) "
                "before approving a loan on a multi-family investment property. "
                "A buyer without that track record will likely need to purchase in cash or "
                "through a private/bridge lender at a higher rate until that history is established. "
                "This financing scenario is illustrative and assumes the buyer qualifies for "
                f"conventional commercial financing at {rate:.3f}%.",
                s["body"]
            )]],
            colWidths=[6.0*inch]
        )
        note_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFF8E1")),
            ("BOX",           (0, 0), (-1, -1), 1.5, colors.HexColor("#F9A825")),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        elems.append(KeepTogether([note_tbl]))

    # ── Income-Based Price Recommendation ────────────────────────────────────
    pr_at_7_cur  = subject.get("mf_pr_at_7_cur", 0)
    pr_at_11_cur = subject.get("mf_pr_at_11_cur", 0)
    pr_at_7_mkt  = subject.get("mf_pr_at_7_mkt", 0)
    pr_at_11_mkt = subject.get("mf_pr_at_11_mkt", 0)
    cap_lo       = subject.get("mf_cap_low", 7.0)
    cap_hi       = subject.get("mf_cap_high", 11.0)
    pr_coc8_cur  = subject.get("mf_pr_coc8_cur", 0)
    pr_coc12_cur = subject.get("mf_pr_coc12_cur", 0)
    pr_coc8_mkt  = subject.get("mf_pr_coc8_mkt", 0)
    pr_coc12_mkt = subject.get("mf_pr_coc12_mkt", 0)
    coc_lo       = subject.get("mf_coc_low", 8.0)
    coc_hi       = subject.get("mf_coc_high", 12.0)
    show_fin     = subject.get("mf_show_financing", False)
    down_pct_v   = float(subject.get("mf_down_pct", 25.0))
    rate_v       = float(subject.get("mf_interest_rate", 7.0))
    term_v       = int(subject.get("mf_loan_term_yrs", 30))

    if pr_at_7_cur > 0:
        elems.append(Spacer(1, 14))
        elems.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=6))
        elems.append(Paragraph(
            "INCOME-BASED PRICE RECOMMENDATION",
            ParagraphStyle("rec_hdr", fontName="Times-Bold", fontSize=11,
                           textColor=NAVY, spaceAfter=4)
        ))
        elems.append(Spacer(1, 6))

        LBLUE  = colors.HexColor("#EEF3F8")
        LLBLUE = colors.HexColor("#F7FAFD")
        LPINK  = colors.HexColor("#FFF0F5")
        DHDR   = colors.HexColor("#D8E4F0")
        PHDR   = colors.HexColor("#FCE4EC")
        BLURB  = colors.HexColor("#EEF3F8")

        _blurb_style = ParagraphStyle(
            "_blurb", fontName="Times-Roman", fontSize=9, textColor=colors.HexColor("#333333"),
            leading=13, leftIndent=6, rightIndent=6, spaceAfter=4,
            backColor=BLURB, borderPadding=(5, 8, 5, 8),
        )

        def _rec_row_pdf(label, price, ret_pct, pink=False):
            c  = PINK if pink else NAVY
            fn = "Times-Bold" if pink else "Times-Roman"
            return [
                Paragraph(label, ParagraphStyle("_rl", fontName=fn, fontSize=9, textColor=c)),
                _rp(f"<b>{_money(price)}</b>", bold=True, color=c, size=10),
                _rp(f"{ret_pct:.1f}%", color=c),
            ]

        def _shdr_row(text, pink=False):
            c  = PINK if pink else NAVY
            bg = PHDR  if pink else DHDR
            return ([
                Paragraph(f"<b>{text}</b>",
                          ParagraphStyle("_sh", fontName="Times-Bold", fontSize=9, textColor=c)),
                Paragraph("", s["body"]), Paragraph("", s["body"]),
            ], bg)

        rec_rows = [[
            Paragraph("<b>Price Scenario</b>", s["label"]),
            _rp("<b>Implied Price</b>", bold=True, color=WHITE),
            _rp("<b>Return %</b>", bold=True, color=WHITE),
        ]]
        row_colors = [NAVY]

        def _add_shdr(text, pink=False):
            row, bg = _shdr_row(text, pink=pink)
            rec_rows.append(row)
            row_colors.append(bg)

        def _add_data(label, price, ret_pct, pink=False):
            rec_rows.append(_rec_row_pdf(label, price, ret_pct, pink=pink))
            row_colors.append(LPINK if pink else LBLUE)

        # ── Cap Rate blurb + rows ──────────────────────────────────────────
        elems.append(Paragraph(
            "<b>Cap Rate</b> — return on an all-cash purchase (NOI \u00f7 Price, no debt). "
            "A 7% cap rate means the property generates <b>$7 of annual income for every $100 of purchase price</b>. "
            f"Investors targeting {cap_lo:.0f}\u2013{cap_hi:.0f}% are typical in Northern New England multi-family.",
            _blurb_style
        ))
        elems.append(Spacer(1, 4))

        _add_shdr(f"Cash Purchase — Cap Rate  |  Current NOI {_money(noi_cur)}/yr")
        _add_data(f"{cap_lo:.0f}% cap rate — investor ceiling", pr_at_7_cur, cap_lo)
        _add_data(f"{cap_hi:.0f}% cap rate — strong investor value", pr_at_11_cur, cap_hi)

        if pr_at_7_mkt > 0:
            _add_shdr(f"Cash Purchase at Market Rents — NOI {_money(noi_mkt)}/yr", pink=True)
            _add_data(f"{cap_lo:.0f}% cap rate at market rents", pr_at_7_mkt, cap_lo, pink=True)
            _add_data(f"{cap_hi:.0f}% cap rate at market rents", pr_at_11_mkt, cap_hi, pink=True)

        # ── CoC blurb + rows (only when financing entered) ────────────────
        if show_fin and pr_coc8_cur > 0:
            # Render the cap-rate table first, then the CoC blurb + its own table
            col_w = [4.0*inch, 1.2*inch, 1.0*inch]
            rec_tbl = Table(rec_rows, colWidths=col_w)
            rec_style = [
                ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOX",          (0, 0), (-1, -1), 1.5, NAVY),
            ]
            for i, bg in enumerate(row_colors):
                rec_style.append(("BACKGROUND", (0, i), (-1, i), bg))
                if i > 0 and bg in (DHDR, PHDR):
                    rec_style.append(("SPAN", (0, i), (-1, i)))
            rec_tbl.setStyle(TableStyle(rec_style))
            elems.append(KeepTogether([rec_tbl]))
            elems.append(Spacer(1, 10))

            fin_lbl = f"{down_pct_v:.0f}% down @ {rate_v:.2f}% / {term_v} yr"
            elems.append(Paragraph(
                f"<b>Cash-on-Cash Return (CoC)</b> — return on just the down payment ({fin_lbl}) "
                "after paying the mortgage. Because of leverage, CoC can be higher than the cap rate. "
                f"An {coc_lo:.0f}\u2013{coc_hi:.0f}% CoC is generally considered a strong leveraged return.",
                _blurb_style
            ))
            elems.append(Spacer(1, 4))

            coc_rows = [[
                Paragraph("<b>Price Scenario</b>", s["label"]),
                _rp("<b>Implied Price</b>", bold=True, color=WHITE),
                _rp("<b>Return %</b>", bold=True, color=WHITE),
            ]]
            coc_colors = [NAVY]

            def _add_coc_shdr(text, pink=False):
                row, bg = _shdr_row(text, pink=pink)
                coc_rows.append(row)
                coc_colors.append(bg)

            def _add_coc_data(label, price, ret_pct, pink=False):
                coc_rows.append(_rec_row_pdf(label, price, ret_pct, pink=pink))
                coc_colors.append(LPINK if pink else LBLUE)

            _add_coc_shdr(f"Financed Buyer — Cash-on-Cash Return  |  {fin_lbl}")
            _add_coc_data(f"{coc_lo:.0f}% CoC — solid leveraged return", pr_coc8_cur, coc_lo)
            _add_coc_data(f"{coc_hi:.0f}% CoC — strong leveraged return", pr_coc12_cur, coc_hi)
            if pr_coc8_mkt > 0:
                _add_coc_shdr(f"Financed at Market Rents  |  {fin_lbl}", pink=True)
                _add_coc_data(f"{coc_lo:.0f}% CoC at market rents", pr_coc8_mkt, coc_lo, pink=True)
                _add_coc_data(f"{coc_hi:.0f}% CoC at market rents", pr_coc12_mkt, coc_hi, pink=True)

            coc_tbl = Table(coc_rows, colWidths=col_w)
            coc_style = [
                ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOX",          (0, 0), (-1, -1), 1.5, NAVY),
            ]
            for i, bg in enumerate(coc_colors):
                coc_style.append(("BACKGROUND", (0, i), (-1, i), bg))
                if i > 0 and bg in (DHDR, PHDR):
                    coc_style.append(("SPAN", (0, i), (-1, i)))
            coc_tbl.setStyle(TableStyle(coc_style))
            elems.append(KeepTogether([coc_tbl]))
        else:
            # No financing — render the single cap-rate table
            col_w = [4.0*inch, 1.2*inch, 1.0*inch]
            rec_tbl = Table(rec_rows, colWidths=col_w)
            rec_style = [
                ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOX",          (0, 0), (-1, -1), 1.5, NAVY),
            ]
            for i, bg in enumerate(row_colors):
                rec_style.append(("BACKGROUND", (0, i), (-1, i), bg))
                if i > 0 and bg in (DHDR, PHDR):
                    rec_style.append(("SPAN", (0, i), (-1, i)))
            rec_tbl.setStyle(TableStyle(rec_style))
            elems.append(KeepTogether([rec_tbl]))

        elems.append(Spacer(1, 6))
        elems.append(Paragraph(
            f"<i>★ Cap rate = NOI ÷ Price (cash basis, no debt). These are income-based price targets "
            f"for investor buyers. Final list price may differ based on comparable sales, condition, "
            f"and market demand. {cap_lo:.0f}–{cap_hi:.0f}% is a typical Northern New England multi-family cap rate range.</i>",
            s["caption"]
        ))


    return elems


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

    # Multi-family cap rate analysis (only for multi-family)
    if subject.get("property_type") == "Multi Family" and subject.get("mf_units"):
        story += _build_cap_rate_analysis(subject, price_rec, s)
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
