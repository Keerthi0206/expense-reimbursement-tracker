"""
OCR-based receipt data extraction using Tesseract (local, no API key needed)
plus regex parsing on the recognized text. Values are always suggestions,
never applied automatically -- accuracy varies with image quality.

PDFs try the embedded text layer first; falls back to OCR on a rendered
page if there's no text layer (scanned PDF).
"""
import io
import re
from datetime import datetime
from typing import Optional

import pytesseract
from PIL import Image
import pymupdf as fitz


def get_file_metadata(contents: bytes, mime: str) -> dict:
    metadata = {
        "size_kb": round(len(contents) / 1024, 1),
        "format": mime,
        "width": None,
        "height": None,
        "page_count": None,
    }
    try:
        if mime in ("image/jpeg", "image/png"):
            img = Image.open(io.BytesIO(contents))
            metadata["width"], metadata["height"] = img.size
        elif mime == "application/pdf":
            doc = fitz.open(stream=contents, filetype="pdf")
            metadata["page_count"] = doc.page_count
            if doc.page_count > 0:
                pix = doc[0].get_pixmap()
                metadata["width"], metadata["height"] = pix.width, pix.height
            doc.close()
    except Exception:
        pass  # metadata is a nice-to-have; never let it break the request
    return metadata


def extract_text(contents: bytes, mime: str) -> str:
    if mime in ("image/jpeg", "image/png"):
        img = Image.open(io.BytesIO(contents))
        return pytesseract.image_to_string(img)

    if mime == "application/pdf":
        doc = fitz.open(stream=contents, filetype="pdf")
        try:
            text_layer = doc[0].get_text().strip()
            if len(text_layer) > 20:  # a real text layer, not just noise
                return text_layer
            # scanned PDF with no usable text layer -- render and OCR it
            pix = doc[0].get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img)
        finally:
            doc.close()

    return ""


_AMOUNT_PATTERN = re.compile(r"\$\s*([\d,]+\.\d{2})")
_TOTAL_LINE_PATTERN = re.compile(r"\btotal\b", re.IGNORECASE)
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "%m/%d/%Y"),
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "%Y-%m-%d"),
]


def parse_amount(text: str) -> Optional[float]:
    matches = _AMOUNT_PATTERN.findall(text)
    if not matches:
        return None
    amounts = [float(m.replace(",", "")) for m in matches]
    # prefer a standalone "total" line over subtotal/line items
    # (\btotal\b won't match inside "subtotal" -- no word boundary there)
    for line in text.splitlines():
        if _TOTAL_LINE_PATTERN.search(line):
            line_match = _AMOUNT_PATTERN.search(line)
            if line_match:
                return float(line_match.group(1).replace(",", ""))
    # no explicit total line -- fall back to the largest amount found
    return max(amounts)


def parse_date(text: str) -> Optional[str]:
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                parsed = datetime.strptime(match.group(0), fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def parse_merchant(text: str) -> Optional[str]:
    # Receipts conventionally put the store/merchant name as the first
    # substantial line -- skip blank lines and very short OCR noise.
    for line in text.splitlines():
        cleaned = line.strip()
        if len(cleaned) >= 3 and not cleaned.replace(" ", "").isdigit():
            return cleaned
    return None


def extract_receipt_suggestions(contents: bytes, mime: str) -> dict:
    text = extract_text(contents, mime)
    return {
        "suggested_amount": parse_amount(text),
        "suggested_date": parse_date(text),
        "suggested_merchant": parse_merchant(text),
        "raw_text_preview": text.strip()[:500],
    }
