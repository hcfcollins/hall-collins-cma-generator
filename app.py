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
APP_VERSION = "2.4.3"
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
        "price_rec": st.session_state.get("price_rec", 425000),
        "price_notes": st.session_state.get("price_notes", ""),
        "agent_notes": st.session_state.get("agent_notes", ""),
        "recommendations": {
            "rec_spring":          st.session_state.get("rec_spring", False),
            "rec_septic":          st.session_state.get("rec_septic", False),
            "rec_home_insp":       st.session_state.get("rec_home_insp", False),
            "rec_staging":         st.session_state.get("rec_staging", False),
            "rec_clean":           st.session_state.get("rec_clean", False),
            "rec_subdivision":     st.session_state.get("rec_subdivision", False),
            "rec_painting":        st.session_state.get("rec_painting", False),
            "rec_organize_leases": st.session_state.get("rec_organize_leases", False),
            "rec_evict_tenants":   st.session_state.get("rec_evict_tenants", False),
            "rec_system_repairs":  st.session_state.get("rec_system_repairs", False),
        },
        # multi-family income fields are stored inside subject_data["mf_*"]
    }


def _load_session_from_dict(d: dict):
    """Push a saved session dict back into session state."""
    if "subject" in d:
        st.session_state.subject_data = d["subject"]
        st.session_state.subject_searched = bool(d["subject"].get("street_address"))
    for key in ("price_low", "price_high", "price_rec", "price_notes", "agent_notes"):
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

# Subject property detail form — always show the type selector; full details once address entered
_prop_type_opts = ["Single Family", "Multi Family", "Condo", "Land", "Commercial", "Other"]
_pt_saved = st.session_state.subject_data.get("property_type", "Single Family")
_pt_idx   = _prop_type_opts.index(_pt_saved) if _pt_saved in _prop_type_opts else 0
_quick_type = st.selectbox(
    "Property Type",
    _prop_type_opts,
    index=_pt_idx,
    key="s_type",
    help="Select Multi Family to unlock income & cap rate analysis below.",
)
st.session_state.subject_data["property_type"] = _quick_type

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
            sd["lot_acres"] = st.number_input("Lot Size (acres)", min_value=0.0, max_value=1000.0, step=0.1,
                                               value=float(sd["lot_acres"]) if sd.get("lot_acres") else 0.0, key="s_lot")
            sd["year_built"] = st.number_input("Year Built", min_value=1700, max_value=2030,
                                                value=int(sd["year_built"]) if sd.get("year_built") else 1990, key="s_year")
        with dc3:
            # Property type is set above (always visible) — show read-only label here
            st.markdown(f"**Property Type**")
            st.markdown(f"*{st.session_state.subject_data.get('property_type', 'Single Family')}*  *(change above)*")
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
# STEP 1b — MULTI-FAMILY INCOME INPUTS (conditional)
# ══════════════════════════════════════════════════════════════════════════════
# s_type widget always renders above, so this is always current
_prop_type_now = st.session_state.get("s_type", "Single Family")
st.session_state.subject_data["property_type"] = _prop_type_now

if _prop_type_now == "Multi Family":
    st.markdown('<div class="section-label">Step 1b — Multi-Family Income Analysis</div>', unsafe_allow_html=True)
    st.markdown(
        "Fill in the income and expense details below. "
        "Cap rate will be calculated automatically and included in the CMA."
    )
    _sd = st.session_state.subject_data

    # ── Number of units + expenses ─────────────────────────────────────────
    mf_col1, mf_col2 = st.columns(2)
    with mf_col1:
        _sd["mf_units"] = st.number_input(
            "Number of Units", min_value=2, max_value=20, step=1,
            value=int(_sd.get("mf_units", 2)), key="mf_units"
        )
        _sd["mf_vacancy_pct"] = st.number_input(
            "Vacancy Rate (%)", min_value=0.0, max_value=100.0, step=0.5,
            value=float(_sd.get("mf_vacancy_pct", 5.0)), key="mf_vacancy_pct"
        )
    with mf_col2:
        _sd["mf_taxes"] = st.number_input(
            "Annual Property Taxes ($)", min_value=0, step=100,
            value=int(_sd.get("mf_taxes", 4000)), key="mf_taxes"
        )
        _sd["mf_insurance"] = st.number_input(
            "Annual Insurance ($)", min_value=0, step=100,
            value=int(_sd.get("mf_insurance", 1500)), key="mf_insurance"
        )
        _sd["mf_maintenance"] = st.number_input(
            "Annual Maintenance & Other Expenses ($)", min_value=0, step=100,
            value=int(_sd.get("mf_maintenance", 2000)), key="mf_maintenance"
        )
    st.markdown(
        "**Capital Reserve Buffer** — set aside a % of gross rent per unit for big-ticket replacements "
        "*(roof, heating system, appliances, painting, etc.)*"
    )
    _res_col1, _res_col2 = st.columns([1, 3])
    with _res_col1:
        _sd["mf_reserve_pct"] = st.number_input(
            "Reserve (% of gross rent)", min_value=0.0, max_value=30.0, step=0.5,
            value=float(_sd.get("mf_reserve_pct", 5.0)), key="mf_reserve_pct",
            help="A common rule of thumb is 5–10% of gross rent. This is deducted from NOI as an operating expense."
        )
    with _res_col2:
        st.caption(
            "Common rule of thumb: **5%** per unit for newer/well-maintained buildings, "
            "**8–10%** for older buildings or those with aging systems. "
            "This reduces NOI and therefore the income-based price — making it a more conservative, realistic estimate."
        )

    # ── Per-unit rent breakdown ────────────────────────────────────────────
    st.markdown("**Rent by Unit** — enter current and market rent for each unit")
    _num_units = int(_sd.get("mf_units", 2))

    # Ensure unit list is the right length
    _existing_units = _sd.get("mf_unit_rents", [])
    while len(_existing_units) < _num_units:
        _existing_units.append({"label": f"Unit {len(_existing_units) + 1}", "current": 0, "market": 0})
    _existing_units = _existing_units[:_num_units]
    _sd["mf_unit_rents"] = _existing_units

    # Header row
    _hcols = st.columns([1.5, 2, 2, 2])
    _hcols[0].markdown("**Unit**")
    _hcols[1].markdown("**Description** *(optional)*")
    _hcols[2].markdown("**Current Rent/mo ($)**")
    _hcols[3].markdown("**Market Rent/mo ($)**")

    for _i in range(_num_units):
        _ucols = st.columns([1.5, 2, 2, 2])
        with _ucols[0]:
            st.markdown(f"<div style='padding-top:8px;font-weight:600;color:#173348;'>Unit {_i+1}</div>", unsafe_allow_html=True)
        with _ucols[1]:
            _existing_units[_i]["label"] = st.text_input(
                f"desc_{_i}", label_visibility="collapsed",
                placeholder=f"e.g. 2BR/1BA upstairs",
                value=_existing_units[_i].get("label", f"Unit {_i+1}"),
                key=f"mf_unit_label_{_i}"
            )
        with _ucols[2]:
            _existing_units[_i]["current"] = st.number_input(
                f"cur_{_i}", label_visibility="collapsed",
                min_value=0, step=50,
                value=int(_existing_units[_i].get("current", 0)),
                key=f"mf_unit_cur_{_i}"
            )
        with _ucols[3]:
            _existing_units[_i]["market"] = st.number_input(
                f"mkt_{_i}", label_visibility="collapsed",
                min_value=0, step=50,
                value=int(_existing_units[_i].get("market", 0)),
                key=f"mf_unit_mkt_{_i}"
            )

    # ── What's Included in Rent ───────────────────────────────────────────
    st.markdown("**What's Included in Rent?** *(check all that apply — will appear in the CMA report)*")
    _util_opts = ["Electric", "Heat", "Plowing", "Mowing", "Trash", "Internet"]
    _util_icons = {"Electric": "⚡", "Heat": "🔥", "Plowing": "❄️", "Mowing": "🌿", "Trash": "🗑️", "Internet": "📶"}
    _existing_utils = _sd.get("mf_included_utilities", [])
    _util_cols = st.columns(len(_util_opts))
    _selected_utils = []
    for _ui, _uopt in enumerate(_util_opts):
        with _util_cols[_ui]:
            _checked = st.checkbox(
                f"{_util_icons[_uopt]} {_uopt}",
                value=(_uopt in _existing_utils),
                key=f"mf_util_{_uopt.lower()}"
            )
            if _checked:
                _selected_utils.append(_uopt)
    _sd["mf_included_utilities"] = _selected_utils

    st.markdown("**Financing Scenario** *(optional — for cash-flow-after-financing analysis)*")
    fin_col1, fin_col2, fin_col3 = st.columns(3)
    with fin_col1:
        _sd["mf_down_pct"] = st.number_input(
            "Down Payment (%)", min_value=0.0, max_value=100.0, step=1.0,
            value=float(_sd.get("mf_down_pct", 25.0)), key="mf_down_pct",
            help="Typical commercial multi-family financing requires 20–30% down."
        )
    with fin_col2:
        _sd["mf_interest_rate"] = st.number_input(
            "Interest Rate (%)", min_value=0.0, max_value=25.0, step=0.125,
            value=float(_sd.get("mf_interest_rate", 7.0)), key="mf_interest_rate"
        )
    with fin_col3:
        _sd["mf_loan_term_yrs"] = st.number_input(
            "Loan Term (years)", min_value=5, max_value=30, step=5,
            value=int(_sd.get("mf_loan_term_yrs", 30)), key="mf_loan_term_yrs"
        )

    # ── Calculations ───────────────────────────────────────────────────────
    _units        = int(_sd.get("mf_units", 2))
    _unit_rents   = _sd.get("mf_unit_rents", [])
    _vacancy      = float(_sd.get("mf_vacancy_pct", 5.0))
    _taxes        = int(_sd.get("mf_taxes", 4000))
    _insurance    = int(_sd.get("mf_insurance", 1500))
    _maintenance  = int(_sd.get("mf_maintenance", 2000))
    _reserve_pct  = float(_sd.get("mf_reserve_pct", 5.0))
    _price_for_cap = st.session_state.get("price_rec", st.session_state.get("price_high", 450000))

    # Sum across all units
    _gross_cur    = sum(u.get("current", 0) for u in _unit_rents) * 12
    _gross_mkt    = sum(u.get("market", 0) for u in _unit_rents) * 12
    # Derived totals for summary (average per unit for backwards compat)
    _rent_pu      = int(_gross_cur / 12 / _units) if _units > 0 else 0
    _mkt_rent_pu  = int(_gross_mkt / 12 / _units) if _units > 0 else 0

    _reserve_cur  = _gross_cur * (_reserve_pct / 100)
    _reserve_mkt  = _gross_mkt * (_reserve_pct / 100)
    _base_expenses = _taxes + _insurance + _maintenance
    _expenses     = _base_expenses + _reserve_cur   # total expenses at current rents
    _expenses_mkt = _base_expenses + _reserve_mkt   # total expenses at market rents

    _eff_cur      = _gross_cur * (1 - _vacancy / 100)
    _noi_cur      = _eff_cur - _expenses
    _cap_cur      = (_noi_cur / _price_for_cap * 100) if _price_for_cap > 0 else 0.0

    _eff_mkt      = _gross_mkt * (1 - _vacancy / 100)
    _noi_mkt      = _eff_mkt - _expenses_mkt
    _cap_mkt      = (_noi_mkt / _price_for_cap * 100) if _price_for_cap > 0 else 0.0
    _has_upside   = _gross_mkt != _gross_cur

    # Financing calculations
    _down_pct     = float(_sd.get("mf_down_pct", 25.0))
    _rate_annual  = float(_sd.get("mf_interest_rate", 7.0))
    _term_yrs     = int(_sd.get("mf_loan_term_yrs", 30))
    _show_financing = _down_pct > 0 and _rate_annual > 0
    _down_amt     = _price_for_cap * (_down_pct / 100)
    _loan_amt     = _price_for_cap - _down_amt
    # Standard amortization: M = P * [r(1+r)^n] / [(1+r)^n - 1]
    _r_monthly    = (_rate_annual / 100) / 12
    _n_payments   = _term_yrs * 12
    if _r_monthly > 0 and _loan_amt > 0:
        _monthly_pmt  = _loan_amt * (_r_monthly * (1 + _r_monthly) ** _n_payments) / ((1 + _r_monthly) ** _n_payments - 1)
    else:
        _monthly_pmt  = (_loan_amt / _n_payments) if _n_payments > 0 else 0
    _annual_debt  = _monthly_pmt * 12
    _cf_cur       = _noi_cur - _annual_debt      # cash flow after financing, current rents
    _cf_mkt       = _noi_mkt - _annual_debt      # cash flow after financing, market rents
    _coc_cur      = (_cf_cur / _down_amt * 100) if _down_amt > 0 else 0.0   # cash-on-cash return
    _coc_mkt      = (_cf_mkt / _down_amt * 100) if _down_amt > 0 else 0.0

    # Store for PDF
    _sd["mf_gross_income"]       = _gross_cur
    _sd["mf_eff_gross"]          = _eff_cur
    _sd["mf_total_expenses"]     = _expenses
    _sd["mf_total_expenses_mkt"] = _expenses_mkt
    _sd["mf_reserve_cur"]        = round(_reserve_cur)
    _sd["mf_reserve_mkt"]        = round(_reserve_mkt)
    _sd["mf_base_expenses"]      = _base_expenses
    _sd["mf_noi"]                = _noi_cur
    _sd["mf_cap_rate"]           = round(_cap_cur, 2)
    _sd["mf_gross_income_mkt"]   = _gross_mkt
    _sd["mf_eff_gross_mkt"]      = _eff_mkt
    _sd["mf_noi_mkt"]            = _noi_mkt
    _sd["mf_cap_rate_mkt"]       = round(_cap_mkt, 2)
    _sd["mf_rent_per_unit"]      = _rent_pu      # avg, kept for PDF fallback
    _sd["mf_market_rent_per_unit"] = _mkt_rent_pu  # avg, kept for PDF fallback
    _sd["mf_show_financing"]     = _show_financing
    _sd["mf_down_amt"]           = round(_down_amt)
    _sd["mf_loan_amt"]           = round(_loan_amt)
    _sd["mf_monthly_payment"]    = round(_monthly_pmt, 2)
    _sd["mf_annual_debt_service"]= round(_annual_debt, 2)
    _sd["mf_cf_cur"]             = round(_cf_cur, 2)
    _sd["mf_cf_mkt"]             = round(_cf_mkt, 2)
    _sd["mf_coc_cur"]            = round(_coc_cur, 2)
    _sd["mf_coc_mkt"]            = round(_coc_mkt, 2)

    # ── Live preview ───────────────────────────────────────────────────────
    _has_upside = _mkt_rent_pu != _rent_pu
    _upside_row = (
        f'<tr style="border-top:1px solid #ccc;">'
        f'<td style="color:#999;font-size:0.85rem;padding-top:4px;" colspan="3">'
        f'<em>Market rents total ${_gross_mkt/12:,.0f}/mo — ${(_gross_mkt - _gross_cur)/12:+,.0f}/mo vs. current</em>'
        f'</td></tr>'
    ) if _has_upside else ""

    def _cf_color(val):
        return "#2e7d32" if val >= 0 else "#c62828"

    _fin_rows = ""
    if _show_financing:
        _fin_rows = f"""
        <tr><td colspan="{"3" if _has_upside else "2"}" style="padding:6px 8px 2px;font-family:Georgia;font-weight:700;color:#173348;border-top:2px solid #173348;font-size:0.9rem;">
            🏦 Financing: {_down_pct:.0f}% down @ {_rate_annual:.3f}% for {_term_yrs} yrs</td></tr>
        <tr style="background:#f5f5f5;"><td style="padding:3px 8px;">Loan Amount</td>
            <td style="text-align:right;padding:3px 8px;">${_loan_amt:,.0f}</td>
            {"<td style='text-align:right;padding:3px 8px;'>${:,.0f}</td>".format(_loan_amt) if _has_upside else ""}</tr>
        <tr><td style="padding:3px 8px;">Annual Debt Service</td>
            <td style="text-align:right;padding:3px 8px;">(${_annual_debt:,.0f})</td>
            {"<td style='text-align:right;padding:3px 8px;'>(${:,.0f})</td>".format(_annual_debt) if _has_upside else ""}</tr>
        <tr style="border-top:1px solid #E91E63;background:#fff0f5;">
            <td style="padding:5px 8px;font-weight:700;">Cash Flow After Financing</td>
            <td style="text-align:right;padding:5px 8px;font-weight:700;color:{_cf_color(_cf_cur)};">${_cf_cur:,.0f}</td>
            {"<td style='text-align:right;padding:5px 8px;font-weight:700;color:{};'>${:,.0f}</td>".format(_cf_color(_cf_mkt), _cf_mkt) if _has_upside else ""}</tr>
        <tr style="background:#f5f5f5;">
            <td style="padding:3px 8px;color:#555;font-size:0.88rem;">Cash-on-Cash Return <span style="color:#999;">(on ${_down_amt:,.0f} down)</span></td>
            <td style="text-align:right;padding:3px 8px;font-weight:700;color:{_cf_color(_coc_cur)};font-size:0.88rem;">{_coc_cur:.2f}%</td>
            {"<td style='text-align:right;padding:3px 8px;font-weight:700;font-size:0.88rem;color:{};'>{:.2f}%</td>".format(_cf_color(_coc_mkt), _coc_mkt) if _has_upside else ""}</tr>
        <tr><td colspan="{"3" if _has_upside else "2"}" style="padding:4px 8px;font-size:0.78rem;color:#999;font-style:italic;">
            ⚠️ Most commercial lenders require 2 years of documented operating history to finance a multi-family property. Cap rate analysis above remains the primary investor metric.
            </td></tr>
        """

    st.markdown(
        f"""
        <div style="background:#FFF8FB;border:1px solid #E91E63;border-radius:8px;padding:14px 20px;margin-top:8px;">
        <div style="font-family:Georgia;color:#173348;font-size:1rem;font-weight:700;margin-bottom:10px;">📊 Live Analysis Preview</div>
        <table style="width:100%;font-family:Georgia;font-size:0.9rem;border-collapse:collapse;">
          <thead>
            <tr>
              <th style="text-align:left;padding:4px 8px;color:#173348;border-bottom:2px solid #173348;"></th>
              <th style="text-align:right;padding:4px 8px;color:#173348;border-bottom:2px solid #173348;">Current Rents</th>
              {"<th style='text-align:right;padding:4px 8px;color:#E91E63;border-bottom:2px solid #173348;'>Market Rents</th>" if _has_upside else ""}
            </tr>
          </thead>
          <tbody>
            <tr><td style="padding:3px 8px;">Gross Annual Rent</td>
                <td style="text-align:right;padding:3px 8px;">${_gross_cur:,.0f}</td>
                {"<td style='text-align:right;padding:3px 8px;color:#E91E63;'>${:,.0f}</td>".format(_gross_mkt) if _has_upside else ""}</tr>
            <tr style="background:#f9f0f4;"><td style="padding:3px 8px;">Effective Gross Income <span style="color:#999;font-size:0.82rem;">({_vacancy}% vac.)</span></td>
                <td style="text-align:right;padding:3px 8px;">${_eff_cur:,.0f}</td>
                {"<td style='text-align:right;padding:3px 8px;color:#E91E63;'>${:,.0f}</td>".format(_eff_mkt) if _has_upside else ""}</tr>
            <tr><td style="padding:3px 8px;">Operating Expenses</td>
                <td style="text-align:right;padding:3px 8px;">(${_base_expenses:,.0f})</td>
                {"<td style='text-align:right;padding:3px 8px;color:#E91E63;'>(${:,.0f})</td>".format(_base_expenses) if _has_upside else ""}</tr>
            <tr style="background:#f9f0f4;"><td style="padding:3px 8px;">Capital Reserve <span style="color:#999;font-size:0.82rem;">({_reserve_pct:.0f}% of gross — roof, HVAC, etc.)</span></td>
                <td style="text-align:right;padding:3px 8px;">(${_reserve_cur:,.0f})</td>
                {"<td style='text-align:right;padding:3px 8px;color:#E91E63;'>(${:,.0f})</td>".format(_reserve_mkt) if _has_upside else ""}</tr>
            <tr style="border-top:1px solid #E91E63;background:#fff0f5;"><td style="padding:5px 8px;font-weight:700;">NOI</td>
                <td style="text-align:right;padding:5px 8px;font-weight:700;">${_noi_cur:,.0f}</td>
                {"<td style='text-align:right;padding:5px 8px;font-weight:700;color:#E91E63;'>${:,.0f}</td>".format(_noi_mkt) if _has_upside else ""}</tr>
            <tr style="border-top:2px solid #173348;"><td style="padding:6px 8px;color:#E91E63;font-weight:700;font-size:1.05rem;">Cap Rate</td>
                <td style="text-align:right;padding:6px 8px;color:#E91E63;font-weight:700;font-size:1.05rem;">{_cap_cur:.2f}%</td>
                {"<td style='text-align:right;padding:6px 8px;color:#E91E63;font-weight:700;font-size:1.05rem;'>{:.2f}%</td>".format(_cap_mkt) if _has_upside else ""}</tr>
            {_upside_row}
            {_fin_rows}
          </tbody>
        </table>
        <div style="font-size:0.8rem;color:#999;margin-top:8px;font-style:italic;">Values update when you change the recommended price in Step 2.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Suggested Price Range ──────────────────────────────────────────────
    def _price_at_cap(noi, cap_pct):
        return int(noi / (cap_pct / 100)) if cap_pct > 0 and noi > 0 else 0

    def _ads_for_price(price, down_pct, rate, term_yrs):
        """Annual debt service for a given price and loan terms."""
        loan = price * (1 - down_pct / 100)
        rm   = (rate / 100) / 12
        n    = term_yrs * 12
        if rm > 0 and loan > 0:
            pmt = loan * (rm * (1 + rm) ** n) / ((1 + rm) ** n - 1)
        else:
            pmt = loan / n if n > 0 else 0
        return pmt * 12

    def _leveraged_return(noi, price, down_pct, rate, term_yrs):
        """Cash-on-cash return = (NOI - debt service) / down payment."""
        down = price * (down_pct / 100)
        ads  = _ads_for_price(price, down_pct, rate, term_yrs)
        cf   = noi - ads
        return (cf / down * 100) if down > 0 else 0.0, cf, ads

    CAP_LOW, CAP_HIGH = 7.0, 11.0
    COC_LOW, COC_HIGH = 8.0, 12.0

    def _price_at_coc(noi, coc_target_pct, down_pct, rate_annual, term_yrs):
        """Solve price = NOI / (CoC×d + (1−d)×k) where k = annual payment factor."""
        if noi <= 0 or down_pct <= 0 or rate_annual <= 0:
            return 0
        d  = down_pct / 100.0
        r  = (rate_annual / 100.0) / 12.0
        n  = term_yrs * 12
        k  = r * (1 + r) ** n / ((1 + r) ** n - 1) * 12  # annual pmt per $1 of loan
        denom = (coc_target_pct / 100.0) * d + (1.0 - d) * k
        return int(noi / denom) if denom > 0 else 0

    if _noi_cur > 0:
        _pr_at_7_cur  = _price_at_cap(_noi_cur, CAP_LOW)
        _pr_at_11_cur = _price_at_cap(_noi_cur, CAP_HIGH)
        _pr_at_7_mkt  = _price_at_cap(_noi_mkt, CAP_LOW)  if _has_upside else 0
        _pr_at_11_mkt = _price_at_cap(_noi_mkt, CAP_HIGH) if _has_upside else 0

        _pr_coc8_cur  = _price_at_coc(_noi_cur, COC_LOW,  _down_pct, _rate_annual, _term_yrs) if _show_financing else 0
        _pr_coc12_cur = _price_at_coc(_noi_cur, COC_HIGH, _down_pct, _rate_annual, _term_yrs) if _show_financing else 0
        _pr_coc8_mkt  = _price_at_coc(_noi_mkt, COC_LOW,  _down_pct, _rate_annual, _term_yrs) if (_show_financing and _has_upside) else 0
        _pr_coc12_mkt = _price_at_coc(_noi_mkt, COC_HIGH, _down_pct, _rate_annual, _term_yrs) if (_show_financing and _has_upside) else 0

        def _rec_row_html(label, price, ret_val, pink=False):
            c  = "#E91E63" if pink else "#173348"
            bg = "#FFF0F5" if pink else "#EEF3F8"
            return (
                f"<tr style='background:{bg};'>"
                f"<td style='padding:5px 8px;color:{c};font-weight:600;font-size:0.88rem;'>{label}</td>"
                f"<td style='text-align:right;padding:5px 8px;color:{c};font-weight:700;font-size:1rem;'>${price:,.0f}</td>"
                f"<td style='text-align:right;padding:5px 8px;color:{c};font-weight:600;'>{ret_val:.1f}%</td>"
                f"</tr>"
            )

        def _section_hdr(text, colspan=3, pink=False, top_border=False):
            c  = "#E91E63" if pink else "#173348"
            bg = "#FCE4EC" if pink else "#D8E4F0"
            tb = f"border-top:2px solid {c};" if top_border else ""
            return f"<tr style='background:{bg};{tb}'><td colspan='{colspan}' style='padding:6px 8px 3px;color:{c};font-weight:700;font-size:0.82rem;'>{text}</td></tr>"

        # Cap-rate rows
        _cap_rows_cur = (
            _rec_row_html(f"{CAP_LOW:.0f}% cap rate — investor ceiling", _pr_at_7_cur, CAP_LOW)
            + _rec_row_html(f"{CAP_HIGH:.0f}% cap rate — strong investor value", _pr_at_11_cur, CAP_HIGH)
        )
        _cap_rows_mkt = ""
        if _has_upside and _pr_at_7_mkt > 0:
            _cap_rows_mkt = (
                _section_hdr(f"📈 At Market Rents — NOI ${_noi_mkt:,.0f}/yr", pink=True, top_border=True)
                + _rec_row_html(f"{CAP_LOW:.0f}% cap rate at market rents", _pr_at_7_mkt, CAP_LOW, pink=True)
                + _rec_row_html(f"{CAP_HIGH:.0f}% cap rate at market rents", _pr_at_11_mkt, CAP_HIGH, pink=True)
            )

        # CoC rows (only if financing entered)
        _coc_rows = ""
        if _show_financing and _pr_coc8_cur > 0:
            _fin_label = f"{_down_pct:.0f}% down @ {_rate_annual:.2f}% — {_term_yrs} yr"
            _coc_rows = (
                _section_hdr(f"🏦 Financed Buyer — Cash-on-Cash Return ({_fin_label})", top_border=True)
                + _rec_row_html(f"{COC_LOW:.0f}% CoC — solid leveraged return", _pr_coc8_cur, COC_LOW)
                + _rec_row_html(f"{COC_HIGH:.0f}% CoC — strong leveraged return", _pr_coc12_cur, COC_HIGH)
            )
            if _has_upside and _pr_coc8_mkt > 0:
                _coc_rows += (
                    _section_hdr(f"📈 Financed at Market Rents ({_fin_label})", pink=True, top_border=True)
                    + _rec_row_html(f"{COC_LOW:.0f}% CoC at market rents", _pr_coc8_mkt, COC_LOW, pink=True)
                    + _rec_row_html(f"{COC_HIGH:.0f}% CoC at market rents", _pr_coc12_mkt, COC_HIGH, pink=True)
                )

        # Store for PDF
        _sd["mf_pr_at_7_cur"]   = _pr_at_7_cur
        _sd["mf_pr_at_11_cur"]  = _pr_at_11_cur
        _sd["mf_pr_at_7_mkt"]   = _pr_at_7_mkt
        _sd["mf_pr_at_11_mkt"]  = _pr_at_11_mkt
        _sd["mf_cap_low"]       = CAP_LOW
        _sd["mf_cap_high"]      = CAP_HIGH
        _sd["mf_pr_coc8_cur"]   = _pr_coc8_cur
        _sd["mf_pr_coc12_cur"]  = _pr_coc12_cur
        _sd["mf_pr_coc8_mkt"]   = _pr_coc8_mkt
        _sd["mf_pr_coc12_mkt"]  = _pr_coc12_mkt
        _sd["mf_coc_low"]       = COC_LOW
        _sd["mf_coc_high"]      = COC_HIGH

        _coc_col_note = f" &nbsp;·&nbsp; <em>CoC assumes {_down_pct:.0f}% down @ {_rate_annual:.2f}%</em>" if _show_financing else ""

        _cap_rate_blurb = """
            <tr><td colspan="3" style="padding:8px 8px 6px;">
              <div style="font-family:Georgia;font-size:0.82rem;color:#444;line-height:1.5;
                          padding:8px 12px;background:#EEF3F8;border-left:3px solid #173348;border-radius:3px;">
                <strong>Cap Rate</strong> — return on an all-cash purchase (NOI &divide; Price, no debt).
                A 7% cap rate means the property generates <strong>$7 of annual income for every $100 of purchase price</strong>.
                Investors targeting 7–11% are typical in Northern New England multi-family.
              </div>
            </td></tr>"""

        _coc_blurb = f"""
            <tr><td colspan="3" style="padding:8px 8px 6px;">
              <div style="font-family:Georgia;font-size:0.82rem;color:#444;line-height:1.5;
                          padding:8px 12px;background:#EEF3F8;border-left:3px solid #173348;border-radius:3px;">
                <strong>A Note on Financing and List Price Strategy</strong><br><br>
                Most serious multi-family investors underwrite to a cash cap rate first.
                We recommend <strong>starting at the cash-based price above</strong> — it is well-supported by the income.
                However, if buyer feedback points to a financed buyer pool, it's worth knowing what price
                delivers an attractive cash-on-cash return.<br><br>
                A good CoC is generally <strong>{COC_LOW:.0f}–{COC_HIGH:.0f}%</strong>
                ({_down_pct:.0f}% down @ {_rate_annual:.2f}%).
                If the current recommended price doesn't hit that target, a price reduction may be needed —
                and the cap rate rows above give you the ceiling for any such adjustment.
              </div>
            </td></tr>""" if _show_financing and _pr_coc8_cur > 0 else ""

        st.markdown(
            f"""
            <div style="background:#F0F7FF;border:2px solid #173348;border-radius:8px;padding:14px 20px;margin-top:12px;">
            <div style="font-family:Georgia;color:#173348;font-size:1rem;font-weight:700;margin-bottom:8px;">
              💡 Income-Based Price Recommendation
            </div>
            <table style="width:100%;font-family:Georgia;font-size:0.9rem;border-collapse:collapse;">
              <thead>
                <tr>
                  <th style="text-align:left;padding:5px 8px;color:#fff;background:#173348;">Price Scenario</th>
                  <th style="text-align:right;padding:5px 8px;color:#fff;background:#173348;">Implied Price</th>
                  <th style="text-align:right;padding:5px 8px;color:#fff;background:#173348;">Return %</th>
                </tr>
              </thead>
              <tbody>
                {_cap_rate_blurb}
                {_section_hdr(f"💵 Cash Purchase — Cap Rate &nbsp;·&nbsp; Current NOI ${_noi_cur:,.0f}/yr")}
                {_cap_rows_cur}
                {_cap_rows_mkt}
                {_coc_blurb}
                {_coc_rows}
              </tbody>
            </table>
            <div style="font-size:0.78rem;color:#888;margin-top:8px;font-style:italic;">
              A lower price = higher return = more attractive to investors. Final list price reflects comps and market conditions, not income alone.
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PRICING
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 2 — Price Recommendation</div>', unsafe_allow_html=True)

# ── Auto-seed price range from income analysis (multi-family only) ──────────
_mf_low_suggest  = st.session_state.subject_data.get("mf_pr_at_11_cur", 0)   # 11% cap = conservative floor
_mf_high_suggest = st.session_state.subject_data.get("mf_pr_at_7_cur", 0)    # 7% cap  = investor ceiling
_mf_rec_suggest  = st.session_state.subject_data.get("mf_pr_at_7_mkt", 0) or _mf_high_suggest  # market upside or ceiling

_is_mf = st.session_state.get("s_type") == "Multi Family"
_has_income_data = _mf_low_suggest > 0 and _mf_high_suggest > 0

if _is_mf and _has_income_data:
    # Only seed if user hasn't manually changed these yet (i.e., they're still at defaults)
    _default_low  = round(_mf_low_suggest  / 5000) * 5000
    _default_high = round(_mf_high_suggest / 5000) * 5000
    _default_rec  = round(_mf_rec_suggest  / 1000) * 1000
    if "price_low" not in st.session_state:
        st.session_state["price_low"] = _default_low
    if "price_high" not in st.session_state:
        st.session_state["price_high"] = _default_high
    st.info(
        f"💡 **Income-based suggestion** — "
        f"based on current NOI, a 7–11% cap rate implies a price range of "
        f"**${_default_low:,} – ${_default_high:,}**. "
        f"{'Market rents support up to ' + '${:,}'.format(round(st.session_state.subject_data.get('mf_pr_at_7_mkt',0)/5000)*5000) + '. ' if st.session_state.subject_data.get('mf_pr_at_7_mkt',0) > 0 else ''}"
        f"Adjust below as needed based on comps and condition.",
        icon=None,
    )

p1, p2 = st.columns(2)
with p1:
    price_low = st.number_input("Lowest Price — As-Is ($)", min_value=0, value=int(st.session_state.get("price_low", 400000)), step=5000, key="price_low")
with p2:
    price_high = st.number_input("Highest Price — Instagram-Worthy ($)", min_value=0, value=int(st.session_state.get("price_high", 450000)), step=5000, key="price_high")

# Recommended price slider between low and high
_slider_min = int(price_low) if price_low else 0
_slider_max = int(price_high) if price_high else _slider_min + 50000
_slider_default = st.session_state.get("price_rec", int((_slider_min + _slider_max) / 2))
_slider_default = max(_slider_min, min(_slider_max, _slider_default))

price_rec = st.slider(
    "📍 Our Recommended List Price",
    min_value=_slider_min,
    max_value=_slider_max if _slider_max > _slider_min else _slider_min + 1,
    value=_slider_default,
    step=1000,
    key="price_rec",
    help="Drag to set where you recommend the property should list on the scale between low and high.",
)
st.caption(f"Recommended: **${price_rec:,}**  |  Low: ${price_low:,}  |  High: ${price_high:,}")

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

if st.session_state.get("s_type") == "Multi Family":
    st.markdown("*Multi-Family specific:*")
    mf_rec_col1, mf_rec_col2 = st.columns(2)
    with mf_rec_col1:
        rec_organize_leases = st.checkbox("📁 Organize Leases & Tenant Documents", key="rec_organize_leases")
        rec_evict_tenants   = st.checkbox("🚪 Consider Evicting Tenants Before Listing", key="rec_evict_tenants")
    with mf_rec_col2:
        rec_system_repairs  = st.checkbox("🔧 Make Repairs to Major Systems", key="rec_system_repairs")
else:
    rec_organize_leases = False
    rec_evict_tenants   = False
    rec_system_repairs  = False

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — AGENT NOTES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 4 — Agent Notes</div>', unsafe_allow_html=True)
st.markdown("*Your personal notes — these will appear as a dedicated section in the final PDF.*")

# Pre-fill from sidebar PDF extraction if available
if st.session_state.get("agent_notes_prefill"):
    st.session_state["agent_notes"] = st.session_state.pop("agent_notes_prefill")
elif "agent_notes" not in st.session_state:
    st.session_state["agent_notes"] = st.session_state.subject_data.get("agent_notes", "")

agent_notes = st.text_area(
    "Agent Notes",
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
if rec_organize_leases: recs.append("organize_leases")
if rec_evict_tenants:   recs.append("evict_tenants")
if rec_system_repairs:  recs.append("system_repairs")

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

    # Recalculate cap rates using final price_rec (in case it changed after Step 1b preview)
    if sd.get("property_type") == "Multi Family" and sd.get("mf_noi") and int(price_rec) > 0:
        _pr = int(price_rec)
        sd["mf_cap_rate"]     = round(sd["mf_noi"] / _pr * 100, 2)
        if sd.get("mf_noi_mkt"):
            sd["mf_cap_rate_mkt"] = round(sd["mf_noi_mkt"] / _pr * 100, 2)
        # Recompute financing against final price
        if sd.get("mf_show_financing"):
            _dp   = float(sd.get("mf_down_pct", 25.0))
            _rate = float(sd.get("mf_interest_rate", 7.0))
            _term = int(sd.get("mf_loan_term_yrs", 30))
            _down = _pr * (_dp / 100)
            _loan = _pr - _down
            _rm   = (_rate / 100) / 12
            _np   = _term * 12
            if _rm > 0 and _loan > 0:
                _pmt = _loan * (_rm * (1 + _rm) ** _np) / ((1 + _rm) ** _np - 1)
            else:
                _pmt = (_loan / _np) if _np > 0 else 0
            _ads  = _pmt * 12
            sd["mf_down_amt"]            = round(_down)
            sd["mf_loan_amt"]            = round(_loan)
            sd["mf_monthly_payment"]     = round(_pmt, 2)
            sd["mf_annual_debt_service"] = round(_ads, 2)
            sd["mf_cf_cur"]              = round(sd["mf_noi"] - _ads, 2)
            sd["mf_cf_mkt"]              = round(sd.get("mf_noi_mkt", sd["mf_noi"]) - _ads, 2)
            sd["mf_coc_cur"]             = round((sd["mf_cf_cur"] / _down * 100) if _down > 0 else 0, 2)
            sd["mf_coc_mkt"]             = round((sd["mf_cf_mkt"] / _down * 100) if _down > 0 else 0, 2)

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
                price_rec=int(price_rec),
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

            # ── Auto-upload to Dropbox ────────────────────────────────────────
            try:
                from dropbox_upload import upload_cma_to_dropbox
                pdf_filename = f"CMA_{slug}_{date.today().isoformat()}.pdf"
                ok, msg = upload_cma_to_dropbox(pdf_bytes, pdf_filename)
                if ok:
                    st.success(msg)
                else:
                    # Only show warning if credentials were actually set
                    if "not configured" not in msg:
                        st.warning(f"⚠️ Dropbox upload: {msg}")
            except Exception as _dbx_err:
                st.warning(f"⚠️ Dropbox upload skipped: {_dbx_err}")

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

# ── Version History ────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📋 Version History", expanded=False):
    st.markdown(f"""
| Version | Date | What Changed |
|---------|------|-------------|
| **v2.4.3** | Aug 11, 2026 | Larger HC logo in footer; footer text size increased; added Holly Hall & Fran Collins phone numbers to every page footer |
| **v2.4.2** | Aug 11, 2026 | Agent Notes moved to after Price Recommendation; fixed bullet squares on recommendations; price scale condition notes now stacked (not side-by-side) |
| **v2.4.1** | Aug 11, 2026 | Fixed Agent Notes extraction from sidebar not populating the text field |
| **v2.4.0** | Aug 11, 2026 | Page break before Price Recommendation; pink divider under recommended price; removed highlight from firm philosophy note; HC logo added to every page footer |
| **v2.3.3** | Aug 11, 2026 | Fixed recommendation bullet squares; updated septic, spring, and staging recommendation text |
| **v2.3.2** | Aug 11, 2026 | Price scale redesigned: text moved outside Drawing, arrow points down from above bar, better spacing throughout |
| **v2.3.1** | Aug 11, 2026 | Fixed year built showing as "1,990"; pink round bullets on recommendations |
| **v2.3.0** | Aug 11, 2026 | Justified text throughout; wider price scale (full page width); price labels below color bar; prominent recommended price display; new septic inspection paragraph |
| **v2.2.0** | Aug 9, 2026 | Removed auto-generated narrative from Research Notes; renamed to Agent Recommendations; Agent Notes moved above recommendations in PDF; paragraph breaks preserved |
| **v2.1.0** | Aug 9, 2026 | Price recommendation slider with gradient color scale and arrow marker; firm philosophy note |
| **v2.0.0** | Aug 9, 2026 | Added price recommendation section (As-Is low / Instagram-Worthy high); removed Days on Market and Living Area fields |
| **v1.9.0** | Aug 9, 2026 | Removed sale price field from subject property; removed Comparable Properties side-by-side table from PDF |
| **v1.8.0** | Aug 9, 2026 | Added fuel types (multi-select), private septic, private well, view, solar, and boundary notes fields to subject property |
| **v1.7.0** | Aug 9, 2026 | Replaced ANR link generator with simple PDF upload; ANR map appended as-is to final PDF |
| **v1.6.0** | Aug 9, 2026 | Removed comparable property fields entirely — handled by separate program |
| **v1.5.1** | Aug 9, 2026 | Streamlit Cloud deployment config; app live at hc-cma.streamlit.app |
| **v1.5.0** | Aug 9, 2026 | Added ANR map section and clearer "Other CMA Report" PDF upload labeling |
| **v1.4.0** | Aug 9, 2026 | Sidebar: upload existing CMA PDF, extract Agent Notes, edit and regenerate |
| **v1.3.0** | Aug 9, 2026 | Save & reload sessions — JSON file saves all fields; auto-generated on every PDF download |
| **v1.2.0** | Aug 9, 2026 | Switched to native PDF generation via ReportLab — no Microsoft Word required |
| **v1.1.0** | Aug 9, 2026 | PDF output; HC cover page always prepended; Agent Notes section; supplemental PDF upload (strips first 2 pages); double-click launcher |
| **v1.0.0** | Aug 9, 2026 | Initial release — subject property lookup, comparables, price recommendation, recommendations checklist, map, Word doc output |
""")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="text-align:center;color:#999;font-size:0.75rem;">'
    f'Hall Collins Real Estate Group · CMA Generator v{APP_VERSION}'
    f'</div>',
    unsafe_allow_html=True,
)

