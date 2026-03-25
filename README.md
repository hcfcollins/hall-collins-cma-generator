# Hall Collins CMA Generator

A Streamlit web app that generates a beautifully branded **Comparative Market Analysis (CMA)** Word document for Hall Collins Real Estate Group.

## Features

- 🔍 **Auto-lookup** property data from public web sources (Zillow public pages, geocoding)
- 🗺️ **Interactive map** showing subject property + up to 3 comps with distance lines
- 🌿 **Vermont ANR Atlas link** auto-generated for every property
- 📊 **Comparison table** — beds, baths, garage, sq ft, lot, year built, DOM, finishes
- 📝 **Narrative research notes** with auto-generated property description
- ✅ **Recommendation checklist** (septic, staging, deep clean, etc.) with full text written automatically
- 💰 **Price recommendation section** with comp analysis and price/sq ft
- 📄 **Downloads a `.docx`** Word document — fully branded Hall Collins design

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment (Streamlit Cloud)

1. Push to GitHub
2. Connect repo at [share.streamlit.io](https://share.streamlit.io)
3. Set main file to `app.py`

## Note on MLS Data

Per MLS rules, this app does **not** use any MLS API. Property data is pulled from publicly visible web pages only (Zillow public listings, Nominatim geocoding). All fields can be manually overridden.
