# Hall Collins CMA Generator

> **🔗 Live App: [https://hc-cma.streamlit.app](https://hc-cma.streamlit.app)**

A Streamlit web app that generates a fully branded **Comparative Market Analysis (CMA) PDF** for Hall Collins Real Estate Group — including the HC cover page, comparable analysis, price recommendation, agent notes, ANR map, and your other CMA report, all merged into one clean document.

---

## How to Use

1. Open **[https://hc-cma.streamlit.app](https://hc-cma.streamlit.app)** in any browser
2. Fill in the steps (subject property, comps, pricing, recommendations, notes)
3. Upload your other CMA PDF if you have one (pages 1–2 auto-stripped)
4. Generate the ANR map link if needed
5. Click **Generate CMA PDF** and download

---

## Features

| Step | Feature |
|------|---------|
| 1 | **Subject Property** — auto-lookup from public records or fill manually |
| 2 | **Comparable Properties** — up to 3 comps with auto-lookup |
| 3 | **Price Recommendation** — low / target / high with comp analysis |
| 4 | **Recommendations Checklist** — Spring timing, septic, staging, deep clean, etc. |
| 5 | **Agent Notes** — free-text field, appears as its own PDF section |
| 6 | **Location Map** — interactive Folium map preview |
| 7 | **Other CMA PDF** — upload your MLS/third-party CMA; pages 1–2 auto-stripped |
| 8 | **Vermont ANR Map** — live iframe preview + link printed in PDF |
| — | **Generate PDF** — HC cover + CMA content + ANR link + your other CMA, all merged |

### Save & Reload Sessions
- Every generated PDF comes with a **session `.json` file** — download it to save your work
- Upload it later to restore all fields exactly and regenerate with edits
- Use the sidebar **"Save & Reload CMA"** panel at any time

### Edit Agent Notes from an Existing PDF
- Upload a previously generated CMA PDF in the sidebar
- Agent Notes are automatically extracted and pre-filled for editing
- Apply changes and regenerate a fresh PDF

---

## PDF Structure (every generated CMA)

```
1. HC Cover Page          ← HC - CMA Cover Page Summer Pic.pdf (always fixed)
2. Subject Property Overview
3. Comparable Properties Table
4. Research Notes & Recommendations
5. Agent Notes            ← your custom notes
6. Vermont ANR Map link   ← if generated
7. Price Recommendation
8. Other CMA Pages        ← your uploaded PDF minus first 2 pages (if uploaded)
```

---

## Running Locally

```bash
git clone https://github.com/hcfcollins/hall-collins-cma-generator.git
cd hall-collins-cma-generator
pip install -r requirements.txt
streamlit run app.py
```

Runs on **http://localhost:8502** (port chosen to avoid conflict with the Listing Packet app on 8501).

Or just double-click **`Launch CMA Generator.command`** in Finder.

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for a full log of every change.

| Version | Date | Summary |
|---------|------|---------|
| v1.5.1 | Aug 9, 2026 | Streamlit Cloud deployment config |
| v1.5.0 | Aug 9, 2026 | ANR map section, Other CMA PDF labeling |
| v1.4.0 | Aug 9, 2026 | Edit agent notes from existing PDF |
| v1.3.0 | Aug 9, 2026 | Save & reload sessions via JSON |
| v1.2.0 | Aug 9, 2026 | Native PDF via ReportLab, no Word required |
| v1.1.0 | Aug 9, 2026 | PDF output, agent notes, supplemental PDF, launcher |
| v1.0.0 | Aug 9, 2026 | Initial release |

---

## Note on MLS Data

Per MLS rules, this app does **not** use any MLS API. Property data is pulled from publicly visible web pages only (Redfin public listings, Nominatim/Census geocoding). All fields can be manually overridden.
