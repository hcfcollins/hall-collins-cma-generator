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
from io import BytesIO

from property_research import get_property_data, geocode_address
from map_builder import build_comparison_map
from doc_builder import build_cma_document

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


def empty_comp():
    return {
        "address": "", "beds": None, "baths": None, "sqft": None,
        "lot_acres": None, "year_built": None, "sale_price": None,
        "days_on_market": None, "garage": None, "property_type": None,
        "finishes_note": "", "source": "Manual Entry",
        "lat": None, "lng": None, "url": None,
    }


# ── Session State ──────────────────────────────────────────────────────────────
defaults = {
    "subject_data": {},
    "comps_data": [empty_comp(), empty_comp(), empty_comp()],
    "subject_searched": False,
    "comp_searched": [False, False, False],
    "doc_bytes": None,
    "map_html": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


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

    if zillow.get("error"):
        st.warning(f"⚠️ Zillow search note: {zillow['error']}. Please fill in details manually below.")
    else:
        found = [k for k in ["beds","baths","sqft","year_built"] if zillow.get(k)]
        if found:
            st.success(f"✅ Found data from Zillow: {', '.join(found)}")
        else:
            st.info("ℹ️ Property found but limited public data available. Please fill in details below.")

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

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — COMPARABLE PROPERTIES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 2 — Comparable Properties</div>', unsafe_allow_html=True)
st.markdown(
    "*Enter addresses and click **Look Up** to auto-fill from public web data. "
    "All fields are editable — override anything.*"
)

for comp_idx in range(3):
    comp_colors = [PINK, "#2196F3", "#4CAF50"]
    comp_color = comp_colors[comp_idx]
    with st.expander(f"Comparable #{comp_idx + 1}", expanded=True):
        cc1, cc2 = st.columns([3, 1])
        with cc1:
            addr_val = st.text_input(
                f"Comp #{comp_idx+1} Address",
                value=st.session_state.comps_data[comp_idx].get("address", ""),
                placeholder="456 Oak Road, Woodstock, VT 05091",
                key=f"comp_addr_{comp_idx}",
            )
            st.session_state.comps_data[comp_idx]["address"] = addr_val
        with cc2:
            st.markdown("<br>", unsafe_allow_html=True)
            lookup_comp = st.button(f"🔍 Look Up", key=f"lookup_comp_{comp_idx}", use_container_width=True)

        if lookup_comp and addr_val:
            with st.spinner(f"Searching public records for Comp #{comp_idx+1}…"):
                result = get_property_data(addr_val)
            z = result.get("zillow", {})
            geo = result.get("geocode", {})
            cd = st.session_state.comps_data[comp_idx]
            cd.update({
                "beds": z.get("beds"),
                "baths": z.get("baths"),
                "sqft": z.get("sqft"),
                "lot_acres": z.get("lot_acres"),
                "year_built": z.get("year_built"),
                "sale_price": z.get("sale_price"),
                "days_on_market": z.get("days_on_market"),
                "garage": z.get("garage"),
                "property_type": z.get("property_type"),
                "description": z.get("description", ""),
                "source": z.get("source", "Public Records"),
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
                "url": z.get("url"),
            })
            st.session_state.comp_searched[comp_idx] = True
            if z.get("error"):
                st.warning(f"⚠️ Note: {z['error']}. Please fill in manually.")
            else:
                found = [k for k in ["beds","baths","sqft","year_built","sale_price"] if z.get(k)]
                if found:
                    st.success(f"✅ Found: {', '.join(found)}")
                else:
                    st.info("ℹ️ Limited data found. Fill in below.")

        # Detail fields for comp
        cd = st.session_state.comps_data[comp_idx]
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            cd["beds"] = st.number_input(f"Bedrooms", min_value=0, max_value=20,
                value=int(cd["beds"]) if cd.get("beds") else 0, key=f"c{comp_idx}_beds")
            cd["baths"] = st.number_input(f"Bathrooms", min_value=0.0, max_value=20.0, step=0.5,
                value=float(cd["baths"]) if cd.get("baths") else 0.0, key=f"c{comp_idx}_baths")
            cd["garage"] = st.number_input(f"Garage Spaces", min_value=0, max_value=10,
                value=int(cd["garage"]) if cd.get("garage") else 0, key=f"c{comp_idx}_garage")
        with fc2:
            cd["sqft"] = st.number_input(f"Living Area (sq ft)", min_value=0, max_value=20000,
                value=int(cd["sqft"]) if cd.get("sqft") else 0, key=f"c{comp_idx}_sqft")
            cd["lot_acres"] = st.number_input(f"Lot (acres)", min_value=0.0, max_value=1000.0, step=0.1,
                value=float(cd["lot_acres"]) if cd.get("lot_acres") else 0.0, key=f"c{comp_idx}_lot")
            cd["year_built"] = st.number_input(f"Year Built", min_value=1700, max_value=2030,
                value=int(cd["year_built"]) if cd.get("year_built") else 1990, key=f"c{comp_idx}_year")
        with fc3:
            cd["sale_price"] = st.number_input(f"Sale Price ($)", min_value=0,
                value=int(cd["sale_price"]) if cd.get("sale_price") else 0, key=f"c{comp_idx}_price")
            cd["days_on_market"] = st.number_input(f"Days on Market", min_value=0, max_value=2000,
                value=int(cd["days_on_market"]) if cd.get("days_on_market") else 0, key=f"c{comp_idx}_dom")
            cd["property_type"] = st.selectbox(f"Property Type",
                ["Single Family", "Multi Family", "Condo", "Land", "Commercial", "Other"],
                key=f"c{comp_idx}_type")
        cd["finishes_note"] = st.text_area(f"Finish Quality / Notes",
            placeholder="e.g. Updated baths, original kitchen, laminate floors...",
            value=cd.get("finishes_note", ""), key=f"c{comp_idx}_finishes")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — PRICING
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Step 3 — Price Recommendation</div>', unsafe_allow_html=True)

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
st.markdown('<div class="section-label">Step 4 — Agent Recommendations</div>', unsafe_allow_html=True)
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
    # Geocode any comps that weren't auto-searched
    with st.spinner("Building location map…"):
        if not subj_for_map.get("lat") and subj_street and subj_city:
            geo = geocode_address(f"{subj_street}, {subj_city}")
            subj_for_map["lat"] = geo.get("lat")
            subj_for_map["lng"] = geo.get("lng")

        for cd in st.session_state.comps_data:
            if cd.get("address") and not cd.get("lat"):
                geo = geocode_address(cd["address"])
                cd["lat"] = geo.get("lat")
                cd["lng"] = geo.get("lng")
                time.sleep(0.3)

        active_comps = [c for c in st.session_state.comps_data if c.get("address")]
        m = build_comparison_map(subj_for_map, active_comps)

    from streamlit_folium import st_folium
    st_folium(m, width=700, height=450, returned_objects=[])
    st.caption("★ Pink = Subject Property  |  ● Numbered = Comparable Properties")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# GENERATE DOCUMENT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Generate CMA Report</div>', unsafe_allow_html=True)

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
generate = st.button("📄 Generate CMA Word Document", key="generate_btn")
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

    active_comps = [c for c in st.session_state.comps_data if c.get("address")]

    with st.spinner("Building your CMA document…"):
        # Geocode any missing coordinates
        if not sd.get("lat") and sd.get("address"):
            geo = geocode_address(sd["address"])
            sd["lat"] = geo.get("lat")
            sd["lng"] = geo.get("lng")

        for cd in active_comps:
            if not cd.get("lat") and cd.get("address"):
                geo = geocode_address(cd["address"])
                cd["lat"] = geo.get("lat")
                cd["lng"] = geo.get("lng")
                time.sleep(0.3)

        anr_url = sd.get("anr_url")
        if not anr_url and sd.get("lat") and sd.get("lng"):
            from property_research import search_vermont_anr_map
            anr_data = search_vermont_anr_map(sd["address"])
            anr_url = anr_data.get("anr_atlas_url")

        # Build the Word doc
        doc_buffer = build_cma_document(
            subject=sd,
            comps=active_comps,
            recommendations=recs,
            price_low=int(price_low),
            price_high=int(price_high),
            price_notes=price_notes,
            map_png_bytes=None,   # Interactive map via folium in app; link in doc
            anr_url=anr_url,
            logo_path="hall_collins_logo.png",
        )
        st.session_state.doc_bytes = doc_buffer.getvalue()

    st.success("✅ CMA document generated!")

if st.session_state.doc_bytes:
    addr_slug = re.sub(r"[^a-zA-Z0-9]", "_", subj_street or "CMA")
    filename = f"CMA_{addr_slug}.docx"
    st.download_button(
        label="⬇️ Download CMA Word Document",
        data=st.session_state.doc_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    st.caption(f"📄 {filename} — Open in Microsoft Word or Google Docs")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="text-align:center;color:#999;font-size:0.75rem;">'
    f'Hall Collins Real Estate Group · CMA Generator v{APP_VERSION}'
    f'</div>',
    unsafe_allow_html=True,
)
