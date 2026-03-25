#!/usr/bin/env python3
"""
Map Builder Module
Creates a Folium map showing the subject property and comparable properties.
"""

import folium
from folium import plugins
import base64
import os


HALL_COLLINS_NAVY = "#173348"
HALL_COLLINS_PINK = "#E91E63"
COMP_COLORS = ["#2196F3", "#4CAF50", "#FF9800"]  # Blue, Green, Orange for comps 1-3


def _make_icon(color: str, label: str) -> folium.DivIcon:
    """Create a clean styled map pin with a label."""
    html = f"""
    <div style="
        background-color: {color};
        color: white;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        width: 36px;
        height: 36px;
        border: 3px solid white;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.4);
        display: flex;
        align-items: center;
        justify-content: center;
    ">
        <span style="transform: rotate(45deg); font-size: 11px; font-weight: bold;">{label}</span>
    </div>
    """
    return folium.DivIcon(html=html, icon_size=(36, 36), icon_anchor=(18, 36))


def build_comparison_map(subject: dict, comps: list) -> folium.Map:
    """
    Build a folium map with:
    - Subject property marked in Hall Collins navy/pink
    - Up to 3 comparable properties marked with numbered icons
    - Distance lines from subject to each comp
    - Clean tile layer (CartoDB Positron for elegant look)

    subject: {"address": str, "lat": float, "lng": float}
    comps: [{"address": str, "lat": float, "lng": float, "sale_price": ..., ...}, ...]
    """
    # Collect all valid coordinates
    all_coords = []
    if subject.get("lat") and subject.get("lng"):
        all_coords.append((subject["lat"], subject["lng"]))
    for c in comps:
        if c.get("lat") and c.get("lng"):
            all_coords.append((c["lat"], c["lng"]))

    # Default center on Vermont if no coords
    if not all_coords:
        center = [43.8, -72.5]
        zoom = 8
    elif len(all_coords) == 1:
        center = list(all_coords[0])
        zoom = 14
    else:
        avg_lat = sum(c[0] for c in all_coords) / len(all_coords)
        avg_lng = sum(c[1] for c in all_coords) / len(all_coords)
        center = [avg_lat, avg_lng]
        zoom = 11

    # Create map with elegant CartoDB tile
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Add subject property marker
    if subject.get("lat") and subject.get("lng"):
        subj_popup = folium.Popup(
            f"""
            <div style="font-family: Georgia, serif; min-width: 200px;">
                <b style="color: {HALL_COLLINS_NAVY};">⭐ SUBJECT PROPERTY</b><br>
                <span style="font-size: 12px;">{subject.get('address', '')}</span>
            </div>
            """,
            max_width=250,
        )
        folium.Marker(
            location=[subject["lat"], subject["lng"]],
            popup=subj_popup,
            tooltip=f"⭐ Subject: {subject.get('address', '')}",
            icon=_make_icon(HALL_COLLINS_PINK, "★"),
        ).add_to(m)

    # Add comp markers
    for i, comp in enumerate(comps[:3]):
        if not (comp.get("lat") and comp.get("lng")):
            continue
        color = COMP_COLORS[i]
        label = str(i + 1)
        price_str = ""
        if comp.get("sale_price"):
            price_str = f"<br><b>Sale Price:</b> ${int(comp['sale_price']):,}"
        beds_str = f"<br><b>Beds:</b> {comp.get('beds', 'N/A')}" if comp.get("beds") else ""
        sqft_str = f"<br><b>Sq Ft:</b> {int(comp['sqft']):,}" if comp.get("sqft") else ""

        comp_popup = folium.Popup(
            f"""
            <div style="font-family: Georgia, serif; min-width: 200px;">
                <b style="color: {color};">Comp #{label}</b><br>
                <span style="font-size: 12px;">{comp.get('address', '')}</span>
                {price_str}{beds_str}{sqft_str}
            </div>
            """,
            max_width=250,
        )
        folium.Marker(
            location=[comp["lat"], comp["lng"]],
            popup=comp_popup,
            tooltip=f"Comp #{label}: {comp.get('address', '')}",
            icon=_make_icon(color, label),
        ).add_to(m)

        # Draw a dashed line from subject to comp
        if subject.get("lat") and subject.get("lng"):
            folium.PolyLine(
                locations=[
                    [subject["lat"], subject["lng"]],
                    [comp["lat"], comp["lng"]],
                ],
                color=color,
                weight=2,
                opacity=0.6,
                dash_array="8 4",
            ).add_to(m)

    # Fit bounds if we have multiple points
    if len(all_coords) > 1:
        m.fit_bounds([[min(c[0] for c in all_coords) - 0.02,
                       min(c[1] for c in all_coords) - 0.02],
                      [max(c[0] for c in all_coords) + 0.02,
                       max(c[1] for c in all_coords) + 0.02]])

    return m


def map_to_png_bytes(folium_map: folium.Map) -> bytes | None:
    """
    Save folium map as PNG for embedding in Word doc.
    Requires selenium + a browser driver. If not available, returns None.
    We handle gracefully - the Word doc will include the ANR link instead.
    """
    try:
        import tempfile
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            folium_map.save(f.name)
            html_path = f.name

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=900,600")
        driver = webdriver.Chrome(options=options)
        driver.get(f"file://{html_path}")
        import time
        time.sleep(2)
        png_bytes = driver.get_screenshot_as_png()
        driver.quit()
        return png_bytes
    except Exception:
        return None
