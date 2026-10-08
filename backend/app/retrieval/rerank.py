"""Reranking — the "Rerank" step in the architecture doc's retrieval
pipeline (Vector Search -> Merge Results -> Rerank -> LLM Context). The
doc is explicit that "the reranker technology can be selected during
implementation" and "the architecture should keep this component
replaceable" — so this follows the same swappable-provider shape as
app/llm.py and app/storage.py: callers only ever call rerank_chunks(),
and adding a real cross-encoder or a hosted reranker (Cohere, etc.) later
means adding a branch here, not touching any caller.
"""

from pydantic import BaseModel

from app.config import settings
from app.llm import get_chat_model

RERANK_INPUT_CAP = 20  # cap how many candidates ever go into the ranking prompt — cost/latency control
CHUNK_PREVIEW_CHARS = 300  # enough to judge relevance; the full chunk still reaches the agent afterward
TOP_N = 8


class RankedOrder(BaseModel):
    ranked_indices: list[int]


def rerank_chunks(query: str, chunks: list[dict], top_n: int = TOP_N) -> list[dict]:
    """Reorders chunks by relevance to query and trims to top_n."""
    if len(chunks) <= 1:
        return chunks

    if settings.rerank_provider == "llm":
        return _rerank_with_llm(query, chunks, top_n)

    raise RuntimeError(
        f"Unknown RERANK_PROVIDER '{settings.rerank_provider}'. Supported: llm "
        "(a cross-encoder or hosted reranker would be added here, as its own branch)."
    )


def _rerank_with_llm(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    """No new ML dependency — a dedicated cross-encoder reranker would mean
    pulling in sentence-transformers/torch, the same heavy-dependency
    tradeoff already deferred for local embeddings. Reuses the chat model
    that's already configured instead, at the cost of one extra LLM call
    per retrieval. Falls back to vector-search order (just truncated) on
    any failure — reranking is an optimization, never a hard dependency of
    retrieval working at all."""
    candidates = chunks[:RERANK_INPUT_CAP]
    listing = "\n\n".join(f"[{i}] {c['text'][:CHUNK_PREVIEW_CHARS]}" for i, c in enumerate(candidates))
    prompt = (
        f"Question: {query}\n\nPassages:\n\n{listing}\n\n"
        "Return the passage indices ordered from most to least relevant to the question. "
        "Include every index exactly once, even ones that seem irrelevant — put those last."
    )

    try:
        result = get_chat_model().with_structured_output(RankedOrder).invoke(prompt)
        order = [i for i in result.ranked_indices if isinstance(i, int) and 0 <= i < len(candidates)]
        seen = set(order)
        order += [i for i in range(len(candidates)) if i not in seen]  # anything the model dropped stays, just at the end
        ranked = [candidates[i] for i in order]
    except Exception:
        ranked = candidates

    return ranked[:top_n]
