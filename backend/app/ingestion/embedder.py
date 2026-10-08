"""Embedding generation — swappable provider, same shape as app/llm.py.

embedding_provider is deliberately independent of llm_provider (architecture
doc Section 1.6 gap: the embedding model must be swappable on its own, not
locked to whatever the chat model is) — a deployment could run chat on
Azure and embeddings locally, or any other combination.
"""

from app.config import settings

_local_model = None


def _get_local_model():
    """Loaded once per process and reused — a sentence-transformers model
    is too expensive (seconds, real memory) to reload on every call."""
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(settings.local_embedding_model)
    return _local_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.embedding_provider == "local":
        # No hosted API involved — the model runs in this process.
        return _get_local_model().encode(texts, show_progress_bar=False).tolist()

    if not settings.openai_api_key and not settings.azure_openai_api_key:
        raise RuntimeError(
            "No embedding provider configured. Add OPENAI_API_KEY or the "
            "AZURE_OPENAI_* variables to your .env before running ingestion "
            "past the parsing/chunking stage, or set EMBEDDING_PROVIDER=local."
        )

    if settings.embedding_provider == "azure":
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        response = client.embeddings.create(
            input=texts,
            model=settings.azure_openai_deployment,
        )
    else:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(
            input=texts,
            model=settings.embedding_model,
        )

    return [item.embedding for item in response.data]
