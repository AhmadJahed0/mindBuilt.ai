"""Splits a multi-part question into separate standalone search queries
before retrieval runs, instead of hoping the agent decides to search twice.

Why this exists: a compound question ("who founded DKK and what water
infrastructure services do we offer?") embeds as one blended vector that
skews toward whichever topic dominates it, silently starving the other
topic's chunks out of the results. Telling the model in its system prompt
to "search separately for each part" was tried first and didn't change its
actual behavior — it kept issuing one search. Decomposing in code, before
the vector search ever runs, makes this deterministic instead of a hope.
"""

from pydantic import BaseModel

from app.llm import get_chat_model

DECOMPOSE_PROMPT = (
    "Break the question below into separate, standalone search queries — "
    "one per distinct topic or fact being asked about. Each query must "
    "stand alone (no pronouns like 'it' or 'that' referring to another "
    "part) and must preserve the full proper nouns, names, and specific "
    "terms from the original question exactly as written — do not shorten "
    "or generalize them (e.g. keep 'DKK Consulting', not just 'DKK'). "
    "These queries feed a semantic search, where dropping specific wording "
    "measurably hurts match quality. If the question is already about a "
    "single topic, return it unchanged as the only item.\n\n"
    "Question: {question}"
)


class QueryParts(BaseModel):
    queries: list[str]


def decompose_query(question: str) -> list[str]:
    model = get_chat_model().with_structured_output(QueryParts)
    result = model.invoke(DECOMPOSE_PROMPT.format(question=question))
    queries = [q.strip() for q in result.queries if q.strip()]
    return queries or [question]
