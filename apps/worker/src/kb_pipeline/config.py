from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    database_url: str
    openrouter_api_key: str
    openai_api_key: str
    openrouter_model: str = "qwen/qwen3.5-397b-a17b:nitro"
    openai_embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 800
    chunk_overlap: int = 300
    full_doc_threshold_tokens: int = 50_000
    llm_concurrency: int = 4
    embed_concurrency: int = 8
    upsert_concurrency: int = 8
    request_retries: int = 3
    request_timeout_seconds: int = 180
    queue_maxsize: int = 64
    llm_validation_retries: int = 1
    progress_heartbeat_seconds: int = 10

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        database_url = os.getenv("DATABASE_URL", "").strip()
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        return cls(
            database_url=database_url,
            openrouter_api_key=openrouter_api_key,
            openai_api_key=openai_api_key,
            openrouter_model=os.getenv("OPENROUTER_MODEL", cls.openrouter_model),
            openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", cls.openai_embedding_model),
            chunk_size=int(os.getenv("KB_CHUNK_SIZE", cls.chunk_size)),
            chunk_overlap=int(os.getenv("KB_CHUNK_OVERLAP", cls.chunk_overlap)),
            full_doc_threshold_tokens=int(os.getenv("KB_FULL_DOC_THRESHOLD_TOKENS", cls.full_doc_threshold_tokens)),
            llm_concurrency=int(os.getenv("KB_LLM_CONCURRENCY", cls.llm_concurrency)),
            embed_concurrency=int(os.getenv("KB_EMBED_CONCURRENCY", cls.embed_concurrency)),
            upsert_concurrency=int(os.getenv("KB_UPSERT_CONCURRENCY", cls.upsert_concurrency)),
            request_retries=int(os.getenv("KB_REQUEST_RETRIES", cls.request_retries)),
            request_timeout_seconds=int(os.getenv("KB_REQUEST_TIMEOUT_SECONDS", cls.request_timeout_seconds)),
            queue_maxsize=int(os.getenv("KB_QUEUE_MAXSIZE", cls.queue_maxsize)),
            llm_validation_retries=int(os.getenv("KB_LLM_VALIDATION_RETRIES", cls.llm_validation_retries)),
            progress_heartbeat_seconds=int(
                os.getenv("KB_PROGRESS_HEARTBEAT_SECONDS", cls.progress_heartbeat_seconds)
            ),
        )

    def require_runtime_secrets(self) -> None:
        missing = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    def normalized_database_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")
