import fitz  # PyMuPDF

# A page with fewer than this many extracted characters is treated as
# image-based (scanned) and routed to OCR instead of native extraction.
MIN_CHARS_FOR_NATIVE_TEXT = 20


def parse_pdf(path: str) -> list[dict]:
    """Returns one entry per page: {"page": N, "text": ..., "needs_ocr": bool}."""
    pages = []
    doc = fitz.open(path)
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        pages.append({
            "page": i,
            "text": text,
            "needs_ocr": len(text) < MIN_CHARS_FOR_NATIVE_TEXT,
        })
    doc.close()
    return pages


def render_page_image(path: str, page_number: int):
    """Renders a page to a PIL-compatible pixmap, for handoff to OCR."""
    doc = fitz.open(path)
    page = doc[page_number - 1]
    pix = page.get_pixmap(dpi=300)
    doc.close()
    return pix
