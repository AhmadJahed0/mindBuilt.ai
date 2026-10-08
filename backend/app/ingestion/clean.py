"""Text normalization between extraction and chunking (architecture doc
Section 1.6: "Clean extracted text -> tiktoken -> chunks..."). Before this,
the pipeline only did a bare .strip() — real extracted text, especially
from OCR or PDFs, routinely has null bytes, repeated blank lines, and
non-breaking spaces that waste tokens and can confuse chunk boundaries.
"""

import re
import unicodedata

_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_MULTI_SPACES = re.compile(r"[ \t]{2,}")


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", "")  # null bytes: seen from some malformed PDF extractions
    text = unicodedata.normalize("NFKC", text)  # e.g. non-breaking space -> regular space
    text = _MULTI_SPACES.sub(" ", text)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)  # collapse 3+ blank lines to one
    return text.strip()
