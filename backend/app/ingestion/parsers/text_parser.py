def parse_text(path: str) -> list[dict]:
    """Returns a list of one page-like unit: {"page": 1, "text": ...}."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return [{"page": 1, "text": f.read()}]
