# Hall Collins CMA Generator — Changelog

All notable changes are logged here. Most recent version is at the top.

---

## v1.2.0 — August 9, 2026

### Changed
- **Removed Microsoft Word dependency entirely** — CMA content is now built
  natively as a PDF using ReportLab. The app now works on any computer (and
  on Streamlit Cloud) without Word installed.
- `pdf_builder.py` fully rewritten: ReportLab renders the CMA content pages
  directly. `docx2pdf` is gone.
- `doc_builder.py` is no longer called during PDF generation (kept in repo
  for reference).
- Removed the "Download DOCX" secondary button — output is PDF only.
- `requirements.txt`: replaced `docx2pdf>=0.1.8` with `reportlab>=4.0.0`.

### Added
- `CHANGELOG.md` — this file, so you have a running log of every change.

---

## v1.1.0 — August 9, 2026

### Added
- **PDF output** — final CMA is now a merged PDF instead of a Word document.
- **HC Cover Page** (`HC - CMA Cover Page Summer Pic.pdf`) automatically
  prepended to every generated CMA — no manual steps required.
- **Step 5 — Agent Notes** — free-text field for personal notes; rendered as
  a dedicated section in the report.
- **Step 7 — Supplemental PDF Upload** — upload any PDF and the app will
  automatically strip its first 2 pages and append the rest to the CMA.
- `pdf_builder.py` — new module handling all PDF merge logic.
- `Launch CMA Generator.command` — double-click launcher for macOS (runs on
  port 8502 so it doesn't conflict with the Listing Packet app on 8501).
- `.gitignore` updated to exclude generated `CMA_*.pdf` / `CMA_*.docx` files.

### Changed
- Steps renumbered 1–7 to accommodate new Agent Notes and Supplemental PDF steps.
- `doc_builder.py` updated to include agent notes as a section in the document.
- `requirements.txt`: added `pypdf>=4.0.0`, `docx2pdf>=0.1.8`.

---

## v1.0.0 — Initial Release

### Added
- Streamlit web app (`app.py`) with Hall Collins branding (navy + pink).
- Subject property lookup from public records (Redfin, Census geocoder,
  OpenStreetMap Nominatim).
- Up to 3 comparable properties with auto-lookup and manual override.
- Price recommendation section (low / target / high) with comp analysis
  and price-per-sq-ft calculation.
- Recommendations checklist (Wait for Spring, Septic Inspection, Home
  Inspection, Staging, Deep Clean, Land Subdivision, Painting Projects) —
  each generates full paragraph text in the report.
- Interactive location map via Folium / streamlit-folium.
- Word document output (`doc_builder.py`) with branded cover page, comparison
  table, research narrative, recommendations, and price section.
- Vermont ANR Natural Resource Atlas deep-link generation.
- `map_builder.py` — Folium map with subject pin and numbered comp markers.
- `property_research.py` — public data scraping (Redfin, Census, Nominatim,
  Vermont grand list, ANR).

---

## How to Use This Log

When you want something changed, you can reference this file to explain what
version introduced a feature. For example:
> "In v1.1.0 you added the supplemental PDF upload — can you change it so
> it strips the first 3 pages instead of 2?"

Each change made going forward will be added as a new version block at the top.
