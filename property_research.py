#!/usr/bin/env python3
"""
Property Research Module
Pulls property data from sources that allow public access:
  1. Redfin public API (no key required, returns real listing data)
  2. US Census TIGER geocoder (free, no key)
  3. OpenStreetMap Nominatim (free geocoding fallback)
  4. Vermont public property records (town grand list URLs)
  5. Vermont ANR Natural Resource Atlas (deep link generator)

Zillow is intentionally NOT used - they block all automated requests (403).
"""

import requests
import re
import json
import time
import urllib.parse
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.redfin.com/",
}

REDFIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.redfin.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

EMPTY_RESULT = {
    "source": None,
    "address": "",
    "beds": None,
    "baths": None,
    "sqft": None,
    "lot_acres": None,
    "year_built": None,
    "sale_price": None,
    "list_price": None,
    "days_on_market": None,
    "description": None,
    "property_type": None,
    "garage": None,
    "url": None,
    "error": None,
}


# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode_address(address: str) -> dict:
    """
    Geocode using Nominatim (OpenStreetMap). Free, no API key required.
    Returns lat, lng, display_name.
    """
    try:
        geolocator = Nominatim(user_agent="hall_collins_cma_app_v2")
        location = geolocator.geocode(address, timeout=12)
        if location:
            return {
                "lat": location.latitude,
                "lng": location.longitude,
                "display_name": location.address,
            }
    except GeocoderTimedOut:
        pass
    except Exception:
        pass

    # Fallback: US Census geocoder (no key required)
    try:
        encoded = urllib.parse.quote(address)
        url = (
            f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
            f"?address={encoded}&benchmark=Public_AR_Current&format=json"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            matches = data.get("result", {}).get("addressMatches", [])
            if matches:
                coords = matches[0]["coordinates"]
                return {
                    "lat": float(coords["y"]),
                    "lng": float(coords["x"]),
                    "display_name": matches[0].get("matchedAddress", address),
                }
    except Exception:
        pass

    return {"lat": None, "lng": None, "display_name": address}


# ── Redfin Public API ─────────────────────────────────────────────────────────

def search_redfin(address: str) -> dict:
    """
    Use Redfin's unofficial but publicly accessible API.
    No API key required. Returns real listing/sale data.
    """
    result = {**EMPTY_RESULT, "address": address}

    try:
        # Step 1: autocomplete to get the Redfin property ID
        encoded = urllib.parse.quote(address)
        autocomplete_url = (
            f"https://www.redfin.com/stingray/do/location-autocomplete"
            f"?location={encoded}&v=2&al=1&iss=false"
        )
        r = requests.get(autocomplete_url, headers=REDFIN_HEADERS, timeout=10)
        if r.status_code != 200:
            result["error"] = f"Redfin autocomplete HTTP {r.status_code}"
            return result

        # Redfin prepends "{}&&" to JSON responses
        text = r.text
        if text.startswith("{}&&"):
            text = text[4:]
        data = json.loads(text)

        # Find best matching property suggestion
        suggestions = data.get("payload", {}).get("sections", [])
        property_id = None
        listing_id = None
        property_url = None

        for section in suggestions:
            for row in section.get("rows", []):
                rtype = row.get("type", "")
                if rtype in ("1", "2", "3"):  # 1=address, 2=neighborhood, 3=city
                    url_path = row.get("url", "")
                    property_id = row.get("id", {}).get("tableId")
                    listing_id = row.get("id", {}).get("listingId")
                    if url_path:
                        property_url = f"https://www.redfin.com{url_path}"
                    break
            if property_id:
                break

        if not property_id:
            result["error"] = "Property not found in Redfin"
            return result

        result["url"] = property_url

        # Step 2: get the above-the-fold data (fast summary endpoint)
        atf_url = (
            f"https://www.redfin.com/stingray/api/home/details/aboveTheFold"
            f"?propertyId={property_id}&accessLevel=1"
        )
        if listing_id:
            atf_url += f"&listingId={listing_id}"

        r2 = requests.get(atf_url, headers=REDFIN_HEADERS, timeout=10)
        if r2.status_code == 200:
            text2 = r2.text
            if text2.startswith("{}&&"):
                text2 = text2[4:]
            atf = json.loads(text2)
            payload = atf.get("payload", {})

            # Parse home facts
            hf = payload.get("homeSectionData", {}).get("homeFactsData", {}).get("homeFactsInfo", {})
            
            beds_raw = hf.get("beds", {}).get("value")
            baths_raw = hf.get("baths", {}).get("value")
            sqft_raw = hf.get("sqFt", {}).get("value")
            year_raw = hf.get("yearBuilt", {}).get("value")
            lot_raw = hf.get("lotSize", {}).get("value")
            style_raw = hf.get("propertyType", {}).get("value")

            if beds_raw:
                try: result["beds"] = int(str(beds_raw).replace(",", ""))
                except: pass
            if baths_raw:
                try: result["baths"] = float(str(baths_raw).replace(",", ""))
                except: pass
            if sqft_raw:
                try: result["sqft"] = int(str(sqft_raw).replace(",", ""))
                except: pass
            if year_raw:
                try: result["year_built"] = int(str(year_raw).replace(",", ""))
                except: pass
            if lot_raw:
                # Convert sq ft to acres if needed
                try:
                    lot_str = str(lot_raw).replace(",", "").lower()
                    if "acre" in lot_str:
                        result["lot_acres"] = float(re.findall(r"[\d.]+", lot_str)[0])
                    else:
                        lot_sqft = float(re.findall(r"[\d.]+", lot_str)[0])
                        result["lot_acres"] = round(lot_sqft / 43560, 2)
                except: pass
            if style_raw:
                result["property_type"] = str(style_raw)

            # Price info
            price_info = payload.get("mediaBrowserInfo", {}).get("priceInfo", {})
            if not price_info:
                price_info = payload.get("homeSectionData", {}).get("priceInfo", {})
            if price_info:
                amt = price_info.get("amount")
                if amt:
                    try: result["sale_price"] = int(str(amt).replace(",", "").replace("$", ""))
                    except: pass

            # Description
            description = payload.get("publicRemarksInfo", {}).get("remarks", "")
            if description:
                result["description"] = description

            result["source"] = "Redfin (public)"
            return result

        # Step 3: fallback - below the fold data
        btf_url = (
            f"https://www.redfin.com/stingray/api/home/details/belowTheFold"
            f"?propertyId={property_id}&accessLevel=1"
        )
        if listing_id:
            btf_url += f"&listingId={listing_id}"

        r3 = requests.get(btf_url, headers=REDFIN_HEADERS, timeout=10)
        if r3.status_code == 200:
            text3 = r3.text
            if text3.startswith("{}&&"):
                text3 = text3[4:]
            btf = json.loads(text3)
            # Extract from amenities/details
            amenities = btf.get("payload", {}).get("amenitiesInfo", {}).get("superGroups", [])
            for group in amenities:
                for section in group.get("amenityGroups", []):
                    for entry in section.get("redfin_defined_amenity_values", []):
                        name = entry.get("header", "").lower()
                        val = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
                        if "bed" in name and not result["beds"]:
                            try: result["beds"] = int(str(val).replace(",",""))
                            except: pass
                        elif "bath" in name and not result["baths"]:
                            try: result["baths"] = float(str(val).replace(",",""))
                            except: pass
                        elif "sq" in name and "ft" in name and not result["sqft"]:
                            try: result["sqft"] = int(str(val).replace(",",""))
                            except: pass
                        elif "year" in name and "built" in name and not result["year_built"]:
                            try: result["year_built"] = int(str(val).replace(",",""))
                            except: pass

            result["source"] = "Redfin (public)"

    except json.JSONDecodeError as e:
        result["error"] = f"Redfin parse error: {e}"
    except Exception as e:
        result["error"] = f"Redfin error: {e}"

    return result


# ── Vermont Public Records ────────────────────────────────────────────────────

def search_vermont_public_records(address: str) -> dict:
    """
    Try Vermont public property records via the VT open data portal.
    Uses the CAMA (Computer Assisted Mass Appraisal) public data.
    No API key required.
    """
    result = {**EMPTY_RESULT, "address": address}

    try:
        # Vermont public property data via public CAMA endpoint
        # Parse town from address
        parts = address.split(",")
        town = parts[1].strip().split()[0] if len(parts) > 1 else ""
        street = parts[0].strip()

        # VT Center for Geographic Information has open parcel data
        # Try the Vermont public CAMA API
        encoded_street = urllib.parse.quote(street)
        encoded_town = urllib.parse.quote(town)

        url = (
            f"https://maps.vcgi.vermont.gov/arcgis/rest/services/EGC_services/OPENDATA_VCGI_PARCEL_SP_NOCACHE_v1/MapServer/0/query"
            f"?where=PROPADDR+LIKE+%27%25{encoded_street}%25%27"
            f"&outFields=PROPADDR,TOWN,ACRESDISC,DESCRIPT,YEAR_BUILT,SQFT_TOTAL,BEDROOMS,BATHS,GARAGESPC,LISTPRICE,SALEPRICE,SALEDATE"
            f"&returnGeometry=false&f=json"
        )

        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features", [])
            if features:
                attrs = features[0].get("attributes", {})

                def safe_int(v):
                    try: return int(v) if v else None
                    except: return None

                def safe_float(v):
                    try: return float(v) if v else None
                    except: return None

                result["beds"] = safe_int(attrs.get("BEDROOMS"))
                result["baths"] = safe_float(attrs.get("BATHS"))
                result["sqft"] = safe_int(attrs.get("SQFT_TOTAL"))
                result["year_built"] = safe_int(attrs.get("YEAR_BUILT"))
                result["lot_acres"] = safe_float(attrs.get("ACRESDISC"))
                result["garage"] = safe_int(attrs.get("GARAGESPC"))
                result["sale_price"] = safe_int(attrs.get("SALEPRICE")) or safe_int(attrs.get("LISTPRICE"))
                result["property_type"] = attrs.get("DESCRIPT", "")
                result["source"] = "Vermont Public Records (VCGI)"
                return result

    except Exception as e:
        result["error"] = f"VT records: {e}"

    return result


# ── Vermont ANR Atlas ─────────────────────────────────────────────────────────

def search_vermont_anr_map(address: str) -> dict:
    """
    Build a direct deep-link to the Vermont ANR Natural Resource Atlas
    for a given address. No API key required — free public GIS.
    """
    geo = geocode_address(address)
    lat = geo.get("lat")
    lng = geo.get("lng")

    result = {
        "address": address,
        "lat": lat,
        "lng": lng,
        "anr_atlas_url": None,
    }

    if lat and lng:
        result["anr_atlas_url"] = (
            f"https://anrmaps.vermont.gov/websites/anra5/"
            f"#coords={lng},{lat},15"
        )

    return result


# ── Master Function ───────────────────────────────────────────────────────────

def get_property_data(address: str) -> dict:
    """
    Try data sources in order of reliability:
      1. Vermont public CAMA / parcel records (most accurate for VT properties)
      2. Redfin public API (good for listed/sold properties)
      3. Geocode only (always works)
    Merges results — best available data wins.
    """
    data = {
        "address": address,
        "geocode": {},
        "zillow": {},   # kept for compatibility — now filled by best source
        "anr": {},
    }

    # Always geocode
    data["geocode"] = geocode_address(address)
    time.sleep(0.3)

    # Try Vermont public records first
    vt_result = search_vermont_public_records(address)
    time.sleep(0.3)

    # Try Redfin
    redfin_result = search_redfin(address)
    time.sleep(0.3)

    # Merge: prefer VT public records for structural data, Redfin for price/description
    merged = {**EMPTY_RESULT, "address": address}

    for key in ["beds", "baths", "sqft", "year_built", "lot_acres", "garage", "property_type"]:
        merged[key] = vt_result.get(key) or redfin_result.get(key)

    for key in ["sale_price", "list_price", "days_on_market", "description", "url"]:
        merged[key] = redfin_result.get(key) or vt_result.get(key)

    # Determine source label
    if vt_result.get("source") and redfin_result.get("source"):
        merged["source"] = f"{vt_result['source']} + {redfin_result['source']}"
    elif vt_result.get("source"):
        merged["source"] = vt_result["source"]
    elif redfin_result.get("source"):
        merged["source"] = redfin_result["source"]
    else:
        # Collect any errors for display
        errors = []
        if vt_result.get("error"):
            errors.append(f"VT records: {vt_result['error']}")
        if redfin_result.get("error"):
            errors.append(f"Redfin: {redfin_result['error']}")
        merged["error"] = " | ".join(errors) if errors else "No public data found for this address"
        merged["source"] = "Not found — please fill in manually"

    data["zillow"] = merged
    data["anr"] = search_vermont_anr_map(address)

    return data
