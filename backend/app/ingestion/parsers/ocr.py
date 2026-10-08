from io import BytesIO

import pytesseract
from PIL import Image


def ocr_page_image(pixmap) -> str:
    """Runs local OCR (Tesseract) on a rendered page image.

    Swap this out for PaddleOCR or Surya later if Tesseract's accuracy
    isn't good enough on the client's scanned archive — the pipeline
    only depends on this function's signature, not its implementation.
    """
    img_bytes = pixmap.tobytes("png")
    image = Image.open(BytesIO(img_bytes))
    return pytesseract.image_to_string(image)
