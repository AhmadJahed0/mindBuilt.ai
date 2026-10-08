from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql://coreveil:coreveil@localhost:5432/coreveil"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    storage_path: str = "./data/storage"

    storage_provider: str = "local"  # local | supabase
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "documents"

    llm_provider: str = "openai"  # openai | azure | anthropic | local
    openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Ollama, running natively on the host (not in Docker) for real GPU/MLX
    # acceleration — see app/llm.py. host.docker.internal is how a
    # container reaches the host's localhost on both Docker Desktop and
    # Colima.
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.1:8b"

    # Independent from llm_provider on purpose (architecture doc Section
    # 1.6 gap: the embedding model must be swappable separately from the
    # chat model) — a client could run chat on Azure and embeddings
    # locally, or vice versa.
    embedding_provider: str = "openai"  # openai | azure | local
    embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "BAAI/bge-base-en-v1.5"

    rerank_provider: str = "llm"  # llm | (future: cohere, cross-encoder, ...)

    jwt_secret: str = ""


settings = Settings()
