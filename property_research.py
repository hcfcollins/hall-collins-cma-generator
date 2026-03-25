#!/usr/bin/env python3
"""
Property Research Module
Scrapes public data from Zillow, town records, and other public sources.
MLS data is NOT accessed via API per rules - only publicly visible web data.
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def geocode_address(address: str) -> dict:
    """Get lat/lng for an address using Nominatim (free, no API key)."""
    try:
        geolocator = Nominatim(user_agent="hall_collins_cma_v1")
        location = geolocator.geocode(address, timeout=10)
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
    return {"lat": None, "lng": None, "display_name": address}


def search_zillow_property(address: str) -> dict:
    """
    Attempt to pull publicly visible listing data from Zillow search.
    Returns whatever can be scraped from the public page.
    """
    result = {
        "source": "Zillow (public)",
        "address": address,
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
        "photo_url": None,
        "error": None,
    }

    try:
        # Encode address for Zillow search URL
        encoded = address.replace(" ", "-").replace(",", "").replace("  ", "-")
        search_url = f"https://www.zillow.com/homes/{encoded}_rb/"
        result["url"] = search_url

        resp = requests.get(search_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        soup = BeautifulSoup(resp.text, "lxml")

        # Try to find JSON-LD structured data (most reliable)
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") in ("SingleFamilyResidence", "House", "Residence", "Product"):
                        result["description"] = data.get("description", "")
                        if "numberOfRooms" in data:
                            result["beds"] = data["numberOfRooms"]
                        if "floorSize" in data:
                            fs = data["floorSize"]
                            if isinstance(fs, dict):
                                result["sqft"] = fs.get("value")
            except Exception:
                continue

        # Try __NEXT_DATA__ JSON blob (Zillow embeds full listing data here)
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script:
            try:
                nd = json.loads(next_data_script.string)
                # Drill into the nested props structure
                props = (
                    nd.get("props", {})
                    .get("pageProps", {})
                    .get("componentProps", {})
                    .get("gdpClientCache", {})
                )
                # gdpClientCache is a JSON string
                if isinstance(props, str):
                    props = json.loads(props)
                for key, val in props.items():
                    if isinstance(val, dict) and "property" in val:
                        prop = val["property"]
                        result["beds"] = prop.get("bedrooms") or result["beds"]
                        result["baths"] = prop.get("bathrooms") or result["baths"]
                        result["sqft"] = prop.get("livingArea") or result["sqft"]
                        result["year_built"] = prop.get("yearBuilt") or result["year_built"]
                        result["sale_price"] = prop.get("price") or result["sale_price"]
                        result["days_on_market"] = prop.get("daysOnZillow") or result["days_on_market"]
                        result["description"] = prop.get("description") or result["description"]
                        result["property_type"] = prop.get("homeType") or result["property_type"]
                        result["lot_acres"] = prop.get("lotAreaValue") or result["lot_acres"]
                        # Photo
                        images = prop.get("originalPhotos", []) or prop.get("photos", [])
                        if images and len(images) > 0:
                            first = images[0]
                            if isinstance(first, dict):
                                result["photo_url"] = first.get("mixedSources", {}).get("jpeg", [{}])[0].get("url")
                        break
            except Exception:
                pass

        # Fallback: scrape visible HTML summary
        if not result["beds"]:
            beds_el = soup.find("span", {"data-testid": "bed-bath-beyond-property-bedbath"})
            if beds_el:
                text = beds_el.get_text()
                bed_match = re.search(r"(\d+)\s*bd", text)
                bath_match = re.search(r"(\d+\.?\d*)\s*ba", text)
                sqft_match = re.search(r"([\d,]+)\s*sqft", text)
                if bed_match:
                    result["beds"] = int(bed_match.group(1))
                if bath_match:
                    result["baths"] = float(bath_match.group(1))
                if sqft_match:
                    result["sqft"] = int(sqft_match.group(1).replace(",", ""))

        # Price from meta tag
        if not result["sale_price"]:
            meta_price = soup.find("meta", {"property": "og:description"})
            if meta_price:
                price_match = re.search(r"\$([\d,]+)", meta_price.get("content", ""))
                if price_match:
                    result["sale_price"] = int(price_match.group(1).replace(",", ""))

    except Exception as e:
        result["error"] = str(e)

    return result


def search_vermont_anr_map(address: str) -> dict:
    """
    Build direct link to Vermont ANR Natural Resource Atlas for a given address.
    The ANR Atlas is a public web GIS - we can deep-link to a location.
    """
    geo = geocode_address(address)
    lat = geo.get("lat")
    lng = geo.get("lng")

    result = {
        "address": address,
        "lat": lat,
        "lng": lng,
        "anr_atlas_url": None,
        "anr_embed_url": None,
    }

    if lat and lng:
        # Vermont ANR Natural Resource Atlas deep link with coordinates
        # Zoom level 14 gives a good property-level view
        result["anr_atlas_url"] = (
            f"https://anrmaps.vermont.gov/websites/anra5/"
            f"#coords={lng},{lat},14"
        )
        # Also build an embeddable iframe URL for the WMS/tile viewer
        result["anr_embed_url"] = (
            f"https://anrmaps.vermont.gov/websites/anra5/"
            f"?coords={lng},{lat}&zoom=14"
        )

    return result


def get_property_data(address: str) -> dict:
    """
    Master function: geocode the address, pull Zillow data, and ANR link.
    Returns a unified dict with everything found.
    """
    data = {
        "address": address,
        "geocode": {},
        "zillow": {},
        "anr": {},
    }

    data["geocode"] = geocode_address(address)
    time.sleep(0.5)  # Be polite to geocoder
    data["zillow"] = search_zillow_property(address)
    data["anr"] = search_vermont_anr_map(address)

    return data
