#!/usr/bin/env python3
"""
PDF Builder
Handles all PDF assembly for Hall Collins CMA Generator:
  1. Convert the CMA Word document to PDF (using docx2pdf on macOS/Windows)
  2. Prepend the fixed HC cover page PDF
  3. Append an optional supplementary PDF, stripping its first 2 pages
"""

import io
import os
import tempfile
from pypdf import PdfWriter, PdfReader

COVER_PDF_PATH = "HC - CMA Cover Page Summer Pic.pdf"


def _docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """
    Convert a DOCX (as bytes) to PDF bytes.
    Uses docx2pdf on macOS/Windows (requires Microsoft Word or LibreOffice).
    Falls back to a notice page if conversion fails.
    """
    try:
        from docx2pdf import convert
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(docx_bytes)
            tmp_docx_path = tmp_docx.name

        tmp_pdf_path = tmp_docx_path.replace(".docx", ".pdf")
        convert(tmp_docx_path, tmp_pdf_path)

        with open(tmp_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        os.unlink(tmp_docx_path)
        os.unlink(tmp_pdf_path)
        return pdf_bytes

    except Exception as e:
        # Return a minimal PDF with an error notice
        raise RuntimeError(
            f"Could not convert DOCX to PDF: {e}\n"
            "Make sure Microsoft Word is installed on this Mac."
        )


def merge_cma_pdf(
    docx_bytes: bytes,
    supplemental_pdf_bytes: bytes | None = None,
) -> bytes:
    """
    Build the final merged PDF:
      Page 1+   : HC Cover Page (always from local file)
      Page N+   : CMA content (converted from DOCX)
      Page M+   : Supplemental PDF pages 3+ (first 2 pages stripped), if provided

    Returns the merged PDF as bytes.
    """
    writer = PdfWriter()

    # ── 1. HC Cover Page ──────────────────────────────────────────────────────
    if os.path.exists(COVER_PDF_PATH):
        cover_reader = PdfReader(COVER_PDF_PATH)
        for page in cover_reader.pages:
            writer.add_page(page)
    else:
        raise FileNotFoundError(
            f"Cover PDF not found at: {COVER_PDF_PATH}\n"
            "Make sure 'HC - CMA Cover Page Summer Pic.pdf' is in the app folder."
        )

    # ── 2. CMA Content (DOCX → PDF) ───────────────────────────────────────────
    cma_pdf_bytes = _docx_bytes_to_pdf_bytes(docx_bytes)
    cma_reader = PdfReader(io.BytesIO(cma_pdf_bytes))

    # Skip the first page of the DOCX-generated doc (it has its own cover page
    # that we're replacing with the branded HC cover PDF above).
    pages_to_add = list(cma_reader.pages)
    if len(pages_to_add) > 1:
        pages_to_add = pages_to_add[1:]  # drop the in-doc cover, keep the rest

    for page in pages_to_add:
        writer.add_page(page)

    # ── 3. Supplemental PDF (strip pages 1 & 2) ───────────────────────────────
    if supplemental_pdf_bytes:
        supp_reader = PdfReader(io.BytesIO(supplemental_pdf_bytes))
        supp_pages = list(supp_reader.pages)
        # Strip first two pages, append the rest
        if len(supp_pages) > 2:
            for page in supp_pages[2:]:
                writer.add_page(page)
        elif len(supp_pages) == 2:
            pass  # Nothing left after stripping — silently skip
        else:
            pass  # Only 1 page — nothing to append

    # ── Output ────────────────────────────────────────────────────────────────
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()
