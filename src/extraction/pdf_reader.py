"""
Getting something out of a PDF before Claude sees it.

Two jobs. Pull the text layer if there is one, and turn the page into an image
if there is not. Which of the two happens decides whether the invoice goes down
the text route or the vision route, and that decision is made on evidence rather
than on a flag in a spreadsheet.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config as cfg

# Below this many characters the page is treated as having no usable text.
# A scanned page usually returns nothing at all, but a page carrying only a
# stray watermark or a form field label would otherwise slip through.
MIN_USEFUL_CHARS = 120


def page_text(pdf_path: Path) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            parts = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(parts).strip()
    except Exception:
        return ""


def has_text_layer(text: str) -> bool:
    return len(text) >= MIN_USEFUL_CHARS


def page_png_base64(pdf_path: Path, dpi: int | None = None) -> str:
    """First page as a base64 PNG, for the vision route."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=dpi or cfg.VISION_DPI)
    data = pix.tobytes("png")
    doc.close()
    return base64.standard_b64encode(data).decode("ascii")
