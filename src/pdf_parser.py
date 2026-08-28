from __future__ import annotations

from typing import Final
import pymupdf
import re

PDF_TEXT_MIN_LENGTH: Final[int] = 20

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        extracted_pages = [page.get_text("text") for page in document]
        text = "\n\n".join(page for page in extracted_pages if page)
    finally:
        document.close()

    cleaned_text = re.sub(r"\s+", " ", text).strip()
    if len(cleaned_text) < PDF_TEXT_MIN_LENGTH:
        raise ValueError("Extracted text is too short. Please ensure the PDF contains readable text.")
    return cleaned_text