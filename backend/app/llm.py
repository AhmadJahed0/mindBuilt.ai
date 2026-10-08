"""Shared chat-model factory. Lives outside app.agent and app.retrieval so
both can import it without a circular dependency (the retrieval layer now
needs an LLM too, for query decomposition — see retrieval/decompose.py)."""

from app.config import settings


def get_chat_model():
    if settings.llm_provider == "local":
        # Ollama, not a hosted API — no key needed, nothing leaves the
        # machine it's running on.
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url)

    provider_key = {
        "azure": settings.azure_openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
    }.get(settings.llm_provider, "")

    if not provider_key:
        raise RuntimeError(
            f"No API key set for LLM_PROVIDER={settings.llm_provider}. "
            "Add the matching key to .env (see .env.example) before using /chat."
        )

    if settings.llm_provider == "azure":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            azure_deployment=settings.azure_openai_deployment,
            api_key=settings.azure_openai_api_key,
        )

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model="claude-sonnet-5", api_key=settings.anthropic_api_key)

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)
