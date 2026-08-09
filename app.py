#!/usr/bin/env python3
"""
Hall Collins CMA Generator
Streamlit app to produce a branded Comparative Market Analysis Word document.
"""

import streamlit as st
import os
import base64
import time
import re
import json
from datetime import date
from io import BytesIO

from property_research import get_property_data, geocode_address, search_vermont_anr_map
from map_builder import build_comparison_map
from pdf_builder import merge_cma_pdf

# ── App Config ─────────────────────────────────────────────────────────────────
APP_VERSION = "1.0.0"
NAVY = "#173348"
PINK = "#E91E63"

st.set_page_config(
    page_title="Hall Collins CMA Generator",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Lato:wght@300;400;600&display=swap');

  html, body, [class*="css"] {{ font-family: 'Lato', sans-serif; }}

  .main-title {{
    font-family: 'Playfair Display', Georgia, serif;
    color: {NAVY};
    font-size: 2rem;
    font-weight: 700;
    text-align: center;
    margin: 0;
  }}
  .sub-title {{
    font-family: 'Lato', sans-serif;
    color: {PINK};
    font-size: 1rem;
    text-align: center;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 2rem;
  }}
  .section-label {{
    font-family: 'Playfair Display', Georgia, serif;
    color: {NAVY};
    font-size: 1.15rem;
    font-weight: 600;
    border-bottom: 2px solid {PINK};
    padding-bottom: 4px;
    margin-bottom: 1rem;
    margin-top: 1.5rem;
  }}
  .comp-card {{
    background: #f9f4f6;
    border-left: 4px solid {NAVY};
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 12px;
  }}
  .comp-card.auto {{ border-left-color: {PINK}; background: #fff8fb; }}
  .rec-check {{ color: {NAVY}; font-weight: 600; }}
  .stButton > button {{
    background-color: {NAVY} !important;
    color: white !important;
    border-radius: 6px !important;
    font-family: 'Lato', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    border: none !important;
    padding: 0.5rem 2rem !important;
  }}
  .stButton > button:hover {{ background-color: {PINK} !important; }}
  .generate-btn > button {{
    background-color: {PINK} !important;
    font-size: 1.1rem !important;
    padding: 0.75rem 3rem !important;
    width: 100% !important;
  }}
  .generate-btn > button:hover {{ background-color: {NAVY} !important; }}
  div[data-testid="stExpander"] {{ border: 1px solid #e0e0e0; border-radius: 8px; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_logo_b64():
    for p in ["hall_collins_logo.png", "templates/hall_collins_logo.png"]:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return None


def fmt_price(val):
    try:
        return f"${int(val):,}"
    except Exception:
        return str(val) if val else "—"


# ── Session State ──────────────────────────────────────────────────────────────
defaults = {
    "subject_data": {},
    "subject_searched": False,
    "doc_bytes": None,
    "pdf_bytes": None,
    "map_html": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Sidebar — Save & Load Session ─────────────────────────────────────────────

def _session_to_dict():
    """Collect all editable CMA data into a plain dict for JSON export."""
    return {
        "_version": APP_VERSION,
        "_saved": date.today().isoformat(),
        "subject": st.session_state.get("subject_data", {}),
        "price_low": st.session_state.get("price_low", 400000),
        "price_high": st.session_state.get("price_high", 450000),
        "price_notes": st.session_state.get("price_notes", ""),
        "agent_notes": st.session_state.get("agent_notes", ""),
        "recommendations": {
            "rec_spring":      st.session_state.get("rec_spring", False),
            "rec_septic":      st.session_state.get("rec_septic", False),
            "rec_home_insp":   st.session_state.get("rec_home_insp", False),
            "rec_staging":     st.session_state.get("rec_staging", False),
            "rec_clean":       st.session_state.get("rec_clean", False),
            "rec_subdivision": st.session_state.get("rec_subdivision", False),
            "rec_painting":    st.session_state.get("rec_painting", False),
        },
    }


def _load_session_from_dict(d: dict):
    """Push a saved session dict back into session state."""
    if "subject" in d:
        st.session_state.subject_data = d["subject"]
        st.session_state.subject_searched = bool(d["subject"].get("street_address"))
    for key in ("price_low", "price_high", "price_notes", "agent_notes"):
        if key in d:
            st.session_state[key] = d[key]
    for rec_key, val in d.get("recommendations", {}).items():
        st.session_state[rec_key] = val


with st.sidebar:
    st.markdown(
        f'<div style="font-family:Georgia;color:{NAVY};font-size:1.1rem;'
        f'font-weight:700;border-bottom:2px solid {PINK};padding-bottom:6px;'
        f'margin-bottom:12px;">💾 Save & Reload CMA</div>',
        unsafe_allow_html=True,
    )

    # ── Load ──────────────────────────────────────────────────────────────────
    st.markdown("**Open a saved CMA session:**")
    uploaded_session = st.file_uploader(
        "Upload .json session file",
        type=["json"],
        key="session_upload",
        label_visibility="collapsed",
    )
    if uploaded_session is not None:
        try:
            session_data = json.loads(uploaded_session.read().decode("utf-8"))
            _load_session_from_dict(session_data)
            saved_on = session_data.get("_saved", "unknown date")
            st.success(f"✅ Session loaded (saved {saved_on})")
            st.rerun()
        except Exception as e:
            st.error(f"Could not load session: {e}")

    st.markdown("---")

    # ── Save ──────────────────────────────────────────────────────────────────
    st.markdown("**Save your current work:**")
    if st.button("💾 Save Session to File", use_container_width=True, key="save_btn"):
        session_dict = _session_to_dict()
        session_json = json.dumps(session_dict, indent=2, default=str)
        subj = st.session_state.subject_data.get("street_address", "CMA")
        slug = re.sub(r"[^a-zA-Z0-9]", "_", subj)
        st.session_state["_save_json"] = session_json
        st.session_state["_save_filename"] = f"CMA_session_{slug}_{date.today().isoformat()}.json"

    if st.session_state.get("_save_json"):
        st.download_button(
            label="⬇️ Download Session File",
            data=st.session_state["_save_json"],
            file_name=st.session_state["_save_filename"],
            mime="application/json",
            use_container_width=True,
            key="save_download_btn",
        )
        st.caption("Upload this file later to pick up exactly where you left off.")

    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.75rem;color:#999;">'
        'The session file saves all property details, comps, pricing, '
        'notes, and recommendations — not the PDF itself.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Edit Agent Notes from Existing PDF ────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div style="font-family:Georgia;color:{NAVY};font-size:1.1rem;'
        f'font-weight:700;border-bottom:2px solid {PINK};padding-bottom:6px;'
        f'margin-bottom:12px;">✏️ Edit Agent Notes in PDF</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Upload a previously generated CMA PDF to extract and edit the "
        "Agent Notes, then regenerate the PDF with your changes.",
        unsafe_allow_html=False,
    )

    uploaded_cma_pdf = st.file_uploader(
        "Upload existing CMA PDF",
        type=["pdf"],
        key="edit_pdf_upload",
        label_visibility="collapsed",
    )

    if uploaded_cma_pdf is not None:
        try:
            from pypdf import PdfReader as _PR
            import io as _io
            raw = uploaded_cma_pdf.read()
            reader = _PR(_io.BytesIO(raw))

            # Walk every page and collect all text
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )

            # Extract the Agent Notes section — look for the header we write
            # in pdf_builder.py ("AGENT NOTES") and grab text until the next
            # all-caps section header or end of document.
            import re as _re
            # Match everything after "AGENT NOTES" up to the next ALLCAPS header
            # or end of string
            pattern = _re.compile(
                r"AGENT NOTES\s*\n(.*?)(?=\n[A-Z][A-Z\s]{4,}\n|\Z)",
                _re.DOTALL | _re.IGNORECASE,
            )
            match = pattern.search(full_text)
            if match:
                extracted_notes = match.group(1).strip()
            else:
                # Fallback: look for any lines after "Agent Notes" heading
                lines = full_text.splitlines()
                notes_lines = []
                capturing = False
                for line in lines:
                    if _re.match(r"^AGENT NOTES\s*$", line.strip(), _re.IGNORECASE):
                        capturing = True
                        continue
                    if capturing:
                        # Stop at next section header (all-caps line 5+ chars)
                        if _re.match(r"^[A-Z][A-Z\s]{4,}$", line.strip()):
                            break
                        notes_lines.append(line)
                extracted_notes = "\n".join(notes_lines).strip()

            if extracted_notes:
                st.success("✅ Agent Notes extracted from PDF.")
            else:
                extracted_notes = ""
                st.info(
                    "ℹ️ No Agent Notes section found in this PDF. "
                    "You can type new notes below and regenerate."
                )

            # Show editable text area pre-filled with extracted notes
            edited_notes = st.text_area(
                "Edit Agent Notes:",
                value=extracted_notes,
                height=200,
                key="sidebar_edited_notes",
            )

            if st.button("✅ Apply to Session & Regenerate", use_container_width=True, key="apply_notes_btn"):
                # Push edited notes into session state so the main form picks them up
                st.session_state.subject_data["agent_notes"] = edited_notes
                st.session_state["agent_notes_prefill"] = edited_notes
                # Store the raw PDF bytes so pdf_builder can re-use the same
                # supplemental data if needed
                st.session_state["_edited_notes"] = edited_notes
                st.session_state["_edit_pdf_bytes"] = raw
                st.success(
                    "✅ Notes updated! Scroll down and click "
                    "**Generate CMA PDF** to rebuild the document."
                )
                st.rerun()

        except Exception as e:
            st.error(f"Could not read PDF: {e}")


# ── Header ─────────────────────────────────────────────────────────────────────
logo_b64 = get_logo_b64()
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    if logo_b64:
        st.markdown(
            f'<div style="text-align:center;margin-bottom:8px;">'
            f'<img src="data:image/png;base64,{logo_b64}" style="width:260px;max-width:100%;">'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<h1 class="main-title">Comparative Market Analysis</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Hall Collins Real Estate Group</p>', unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — SUBJECT PROPERTY
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 1 — Subject Property</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])
with col1:
    subj_street = st.text_input("Street Address", placeholder="123 Maple Street", key="subj_street")
    subj_city = st.text_input("City, State, ZIP", placeholder="Woodstock, VT 05091", key="subj_city")

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    search_subj = st.button("🔍 Look Up Property", key="search_subj_btn", use_container_width=True)

if search_subj and subj_street and subj_city:
    full_address = f"{subj_street}, {subj_city}"
    with st.spinner(f"Searching public records for {full_address}…"):
        result = get_property_data(full_address)
    zillow = result.get("zillow", {})
    geo = result.get("geocode", {})
    anr = result.get("anr", {})
    st.session_state.subject_data = {
        "street_address": subj_street,
        "city_state": subj_city,
        "address": full_address,
        "beds": zillow.get("beds"),
        "baths": zillow.get("baths"),
        "sqft": zillow.get("sqft"),
        "lot_acres": zillow.get("lot_acres"),
        "year_built": zillow.get("year_built"),
        "sale_price": zillow.get("sale_price"),
        "days_on_market": zillow.get("days_on_market"),
        "garage": zillow.get("garage"),
        "property_type": zillow.get("property_type"),
        "description": zillow.get("description"),
        "finishes_note": "",
        "source": zillow.get("source", "Public Records"),
        "lat": geo.get("lat"),
        "lng": geo.get("lng"),
        "url": zillow.get("url"),
        "anr_url": anr.get("anr_atlas_url"),
    }
    st.session_state.subject_searched = True

    found = [k for k in ["beds","baths","sqft","year_built","sale_price"] if zillow.get(k)]
    source_label = zillow.get("source", "public records")
    if found:
        st.success(f"✅ Found data from {source_label}: {', '.join(found)}")
        st.caption("Review below and fill in anything missing.")
    else:
        st.info("ℹ️ Address located but no public listing data found. Please fill in the details below manually — this is normal for off-market or rural properties.")

# Subject property detail form
if subj_street or st.session_state.subject_searched:
    sd = st.session_state.subject_data
    with st.expander("📋 Subject Property Details (review & edit)", expanded=st.session_state.subject_searched):
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            sd["beds"] = st.number_input("Bedrooms", min_value=0, max_value=20,
                                          value=int(sd["beds"]) if sd.get("beds") else 0, key="s_beds")
            sd["baths"] = st.number_input("Bathrooms", min_value=0.0, max_value=20.0, step=0.5,
                                           value=float(sd["baths"]) if sd.get("baths") else 0.0, key="s_baths")
            sd["garage"] = st.number_input("Garage Spaces", min_value=0, max_value=10,
                                            value=int(sd["garage"]) if sd.get("garage") else 0, key="s_garage")
        with dc2:
            sd["sqft"] = st.number_input("Living Area (sq ft)", min_value=0, max_value=20000,
                                          value=int(sd["sqft"]) if sd.get("sqft") else 0, key="s_sqft")
            sd["lot_acres"] = st.number_input("Lot Size (acres)", min_value=0.0, max_value=1000.0, step=0.1,
                                               value=float(sd["lot_acres"]) if sd.get("lot_acres") else 0.0, key="s_lot")
            sd["year_built"] = st.number_input("Year Built", min_value=1700, max_value=2030,
                                                value=int(sd["year_built"]) if sd.get("year_built") else 1990, key="s_year")
        with dc3:
            sd["property_type"] = st.selectbox("Property Type",
                ["Single Family", "Multi Family", "Condo", "Land", "Commercial", "Other"],
                index=0, key="s_type")
            sd["sale_price"] = st.number_input("Recent Sale/List Price ($)", min_value=0,
                                                value=int(sd["sale_price"]) if sd.get("sale_price") else 0, key="s_price")
            sd["days_on_market"] = st.number_input("Days on Market", min_value=0, max_value=1000,
                                                    value=int(sd["days_on_market"]) if sd.get("days_on_market") else 0, key="s_dom")
        sd["features_notes"] = st.text_area("Notable Features / Highlights",
            placeholder="e.g. Original hardwood floors, updated kitchen, mountain views, wrap-around porch...",
            value=sd.get("features_notes", ""), key="s_features")
        sd["finishes_note"] = st.text_area("Quality of Finishes",
            placeholder="e.g. High-end finishes throughout, granite counters, custom cabinetry...",
            value=sd.get("finishes_note", ""), key="s_finishes")

        st.markdown("---")
        st.markdown("**Property Characteristics**")

        # ── Fuel Types (multi-select checkboxes) ──────────────────────────────
        st.markdown("*Fuel Type(s):*")
        fuel_options = ["Oil", "Propane", "Pellet", "Electric", "Mini Split", "Wood", "Other"]
        current_fuel = sd.get("fuel_types", [])
        fuel_cols = st.columns(4)
        selected_fuel = []
        for i, fuel in enumerate(fuel_options):
            with fuel_cols[i % 4]:
                if st.checkbox(fuel, value=(fuel in current_fuel), key=f"fuel_{fuel}"):
                    selected_fuel.append(fuel)
        sd["fuel_types"] = selected_fuel

        # ── Septic / Well / View / Solar ─────────────────────────────────────
        st.markdown("")
        char_col1, char_col2 = st.columns(2)
        with char_col1:
            septic_options = ["— not specified —", "Yes", "No"]
            septic_idx = septic_options.index(sd["private_septic"]) if sd.get("private_septic") in septic_options else 0
            sd["private_septic"] = st.selectbox("Private Septic", septic_options, index=septic_idx, key="s_septic")

            well_options = ["— not specified —", "Yes", "No"]
            well_idx = well_options.index(sd["private_well"]) if sd.get("private_well") in well_options else 0
            sd["private_well"] = st.selectbox("Private Well", well_options, index=well_idx, key="s_well")

            view_options = ["— not specified —", "Yes", "No"]
            view_idx = view_options.index(sd["view"]) if sd.get("view") in view_options else 0
            sd["view"] = st.selectbox("View", view_options, index=view_idx, key="s_view")

        with char_col2:
            solar_options = ["— not specified —", "No", "Yes — Owned", "Yes — Leased"]
            solar_idx = solar_options.index(sd["solar"]) if sd.get("solar") in solar_options else 0
            sd["solar"] = st.selectbox("Solar", solar_options, index=solar_idx, key="s_solar")

        # ── Boundary Notes ────────────────────────────────────────────────────
        sd["boundary_notes"] = st.text_area(
            "Notes on Boundary Lines",
            placeholder="e.g. Back boundary runs along the stone wall, front setback is 25 ft from road...",
            value=sd.get("boundary_notes", ""),
            key="s_boundary",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PRICING
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 2 — Price Recommendation</div>', unsafe_allow_html=True)

p1, p2 = st.columns(2)
with p1:
    price_low = st.number_input("Recommended Low ($)", min_value=0, value=400000, step=5000, key="price_low")
with p2:
    price_high = st.number_input("Recommended High ($)", min_value=0, value=450000, step=5000, key="price_high")

price_notes = st.text_area(
    "Agent Pricing Notes (optional)",
    placeholder="e.g. Priced conservatively to generate multiple offers. Strong buyer demand in this price range...",
    key="price_notes",
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — RECOMMENDATIONS CHECKLIST
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 3 — Agent Recommendations</div>', unsafe_allow_html=True)
st.markdown("*Check all that apply — detailed language will be written into the report automatically.*")

rec_col1, rec_col2 = st.columns(2)
with rec_col1:
    rec_wait_spring = st.checkbox("🌸 Wait for Spring", key="rec_spring")
    rec_septic = st.checkbox("🔍 Septic Inspection Recommended in Advance", key="rec_septic")
    rec_home_insp = st.checkbox("🏠 Home Inspection Recommended in Advance", key="rec_home_insp")
    rec_staging = st.checkbox("🛋️ Staging Instructions", key="rec_staging")
with rec_col2:
    rec_clean = st.checkbox("🧹 Deep Clean / Clear Out Recommended", key="rec_clean")
    rec_subdivision = st.checkbox("📐 Land Subdivision Opportunity", key="rec_subdivision")
    rec_painting = st.checkbox("🎨 Painting / Complete A Few Projects", key="rec_painting")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — AGENT NOTES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 4 — Agent Notes</div>', unsafe_allow_html=True)
st.markdown("*Your personal notes — these will appear as a dedicated section in the final PDF.*")

# Pre-fill from sidebar PDF extraction if available
_notes_prefill = (
    st.session_state.get("agent_notes_prefill")
    or st.session_state.subject_data.get("agent_notes")
    or ""
)
# Clear the prefill trigger after consuming it so it doesn't fight edits
if "agent_notes_prefill" in st.session_state:
    del st.session_state["agent_notes_prefill"]

agent_notes = st.text_area(
    "Agent Notes",
    value=_notes_prefill,
    placeholder=(
        "e.g. The sellers are motivated and flexible on closing date. "
        "The basement has been freshly waterproofed. "
        "Neighbors have expressed interest — could be an off-market opportunity…"
    ),
    height=160,
    key="agent_notes",
    label_visibility="collapsed",
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — MAP PREVIEW
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 5 — Location Map Preview</div>', unsafe_allow_html=True)

valid_comps_for_map = [
    c for c in st.session_state.comps_data
    if c.get("address") and (c.get("lat") or c.get("address"))
]

subj_for_map = st.session_state.subject_data

show_map = st.button("🗺️ Generate Map Preview", key="gen_map_btn")
if show_map:
    with st.spinner("Building location map…"):
        if not subj_for_map.get("lat") and subj_street and subj_city:
            geo = geocode_address(f"{subj_street}, {subj_city}")
            subj_for_map["lat"] = geo.get("lat")
            subj_for_map["lng"] = geo.get("lng")

        m = build_comparison_map(subj_for_map, [])

    from streamlit_folium import st_folium
    st_folium(m, width=700, height=450, returned_objects=[])
    st.caption("★ Pink = Subject Property")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — OTHER CMA FORMAT PDF (strip first 2 pages)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 6 — Attach Other CMA Report (Optional)</div>', unsafe_allow_html=True)
st.markdown(
    "Upload your other CMA format PDF here — e.g. from your MLS or third-party CMA tool. "
    "**Pages 1 and 2 will be automatically stripped** (cover/title pages) and the rest will be "
    "appended to the end of your Hall Collins CMA."
)

supplemental_pdf_file = st.file_uploader(
    "Upload other CMA PDF",
    type=["pdf"],
    key="supplemental_pdf",
    label_visibility="collapsed",
)

if supplemental_pdf_file:
    from pypdf import PdfReader as _PdfReader
    import io as _io
    supp_bytes_preview = supplemental_pdf_file.read()
    supplemental_pdf_file.seek(0)
    try:
        supp_reader = _PdfReader(_io.BytesIO(supp_bytes_preview))
        total_pages = len(supp_reader.pages)
        pages_to_include = max(0, total_pages - 2)
        if pages_to_include > 0:
            st.success(
                f"✅ **{supplemental_pdf_file.name}** — {total_pages} pages total. "
                f"Pages 1–2 (cover) will be removed; **{pages_to_include} pages** will be appended."
            )
        else:
            st.warning(
                f"⚠️ **{supplemental_pdf_file.name}** only has {total_pages} page(s). "
                "After removing the first 2, nothing remains to append."
            )
    except Exception:
        st.error("Could not read the uploaded PDF. Please try a different file.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — ANR MAP PDF UPLOAD
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 7 — ANR Map (Optional)</div>', unsafe_allow_html=True)
st.markdown(
    "Go to [anrmaps.vermont.gov](https://anrmaps.vermont.gov/websites/anra5/) to pull up the property, "
    "print/export it as a PDF, then upload it here. It will be appended to the end of the CMA as-is — "
    "no pages will be removed."
)

anr_pdf_file = st.file_uploader(
    "Upload ANR Map PDF",
    type=["pdf"],
    key="anr_pdf",
    label_visibility="collapsed",
)

if anr_pdf_file:
    from pypdf import PdfReader as _PdfReader
    import io as _io
    try:
        anr_reader = _PdfReader(_io.BytesIO(anr_pdf_file.read()))
        anr_pdf_file.seek(0)
        st.success(f"✅ **{anr_pdf_file.name}** — {len(anr_reader.pages)} page(s) will be appended.")
    except Exception:
        st.error("Could not read the uploaded PDF. Please try a different file.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# GENERATE PDF
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Generate CMA Report</div>', unsafe_allow_html=True)

st.info(
    "📋 **What gets generated:**\n"
    "1. **HC Cover Page** (always included automatically)\n"
    "2. **CMA Content** — subject property details, price recommendation, recommendations & notes\n"
    "3. **Other CMA Report** — your uploaded PDF minus its first 2 pages *(if uploaded)*\n"
    "4. **ANR Map** — your uploaded ANR PDF appended as-is *(if uploaded)*",
    icon=None,
)

# Build recommendations list
recs = []
if rec_wait_spring: recs.append("wait_spring")
if rec_septic:       recs.append("septic_inspection")
if rec_home_insp:    recs.append("home_inspection")
if rec_staging:      recs.append("staging")
if rec_clean:        recs.append("deep_clean")
if rec_subdivision:  recs.append("land_subdivision")
if rec_painting:     recs.append("painting_projects")

st.markdown('<div class="generate-btn">', unsafe_allow_html=True)
generate = st.button("📄 Generate CMA PDF", key="generate_btn")
st.markdown('</div>', unsafe_allow_html=True)

if generate:
    if not subj_street:
        st.error("⚠️ Please enter a subject property address first.")
        st.stop()

    sd = st.session_state.subject_data
    if not sd.get("street_address"):
        sd["street_address"] = subj_street
        sd["city_state"] = subj_city
        sd["address"] = f"{subj_street}, {subj_city}"

    # Attach agent notes to subject dict so doc_builder can include them
    sd["agent_notes"] = agent_notes

    with st.spinner("Building your CMA PDF…"):
        # Geocode subject if needed
        if not sd.get("lat") and sd.get("address"):
            geo = geocode_address(sd["address"])
            sd["lat"] = geo.get("lat")
            sd["lng"] = geo.get("lng")

        # Read uploaded PDFs
        supp_bytes = None
        if supplemental_pdf_file is not None:
            supplemental_pdf_file.seek(0)
            supp_bytes = supplemental_pdf_file.read()

        anr_bytes = None
        if anr_pdf_file is not None:
            anr_pdf_file.seek(0)
            anr_bytes = anr_pdf_file.read()

        # Build and merge the final PDF directly (no Word needed)
        try:
            pdf_bytes = merge_cma_pdf(
                subject=sd,
                comps=[],
                recommendations=recs,
                price_low=int(price_low),
                price_high=int(price_high),
                price_notes=price_notes,
                logo_path="hall_collins_logo.png",
                anr_url=None,
                supplemental_pdf_bytes=supp_bytes,
                anr_pdf_bytes=anr_bytes,
            )
            st.session_state.pdf_bytes = pdf_bytes
            st.session_state.doc_bytes = None  # no DOCX in this flow
            # Auto-generate a session save file at the same time
            st.session_state["_save_json"] = json.dumps(_session_to_dict(), indent=2, default=str)
            slug = re.sub(r"[^a-zA-Z0-9]", "_", sd.get("street_address", "CMA"))
            st.session_state["_save_filename"] = f"CMA_session_{slug}_{date.today().isoformat()}.json"
            st.success("✅ CMA PDF generated successfully!")
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"❌ PDF generation failed: {e}")
            st.stop()

if st.session_state.get("pdf_bytes"):
    addr_slug = re.sub(r"[^a-zA-Z0-9]", "_", subj_street or "CMA")
    filename = f"CMA_{addr_slug}.pdf"
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            label="⬇️ Download CMA PDF",
            data=st.session_state.pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )
    with dl_col2:
        if st.session_state.get("_save_json"):
            st.download_button(
                label="⬇️ Download Session File",
                data=st.session_state["_save_json"],
                file_name=st.session_state.get("_save_filename", "CMA_session.json"),
                mime="application/json",
                use_container_width=True,
                key="main_save_btn",
            )
    st.caption(
        f"📄 **PDF** — HC Cover + CMA Content"
        + (" + Other CMA Pages" if supplemental_pdf_file else "")
        + (" + ANR Map" if anr_pdf_file else "")
        + "  |  💾 **Session file** — upload this to reopen and edit later"
    )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="text-align:center;color:#999;font-size:0.75rem;">'
    f'Hall Collins Real Estate Group · CMA Generator v{APP_VERSION}'
    f'</div>',
    unsafe_allow_html=True,
)

