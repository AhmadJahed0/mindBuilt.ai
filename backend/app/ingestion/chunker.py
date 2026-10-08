import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    """Token-aware chunking so chunk boundaries respect the embedding model's
    context limit instead of splitting on an arbitrary character count."""
    tokens = ENCODING.encode(text)
    if not tokens:
        return []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(ENCODING.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap_tokens

    return chunks
