from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_host: str
    api_port: int
    max_upload_mb: int
    document_storage_backend: str
    upload_storage_dir: Path
    parsed_storage_dir: Path
    tokenizer_encoding: str
    openai_api_key: str | None
    openai_embedding_model: str
    gemini_api_key: str | None
    gemini_checklist_model: str
    gemini_review_model: str
    mistral_api_key: str | None
    mistral_ocr_model: str
    mistral_include_image_base64: bool
    store_parsed_pages_json: bool
    r2_account_id: str | None
    r2_bucket: str | None
    r2_access_key_id: str | None
    r2_secret_access_key: str | None
    r2_endpoint_url: str | None
    dpa_chunk_size: int
    dpa_chunk_overlap: int
    default_dev_tenant_id: uuid.UUID
    repo_root: Path


def load_settings() -> Settings:
    load_dotenv()
    repo_root = Path(__file__).resolve().parents[4]
    upload_storage_dir = Path(os.getenv("UPLOAD_STORAGE_DIR", ".registry_storage/uploads"))
    parsed_storage_dir = Path(os.getenv("PARSED_STORAGE_DIR", ".registry_storage/parsed"))
    r2_account_id = _env_first("R2_ACCOUNT_ID", "ACCOUNT_ID")
    r2_bucket = _env_first("R2_BUCKET")
    r2_access_key_id = _env_first("R2_ACCESS_KEY_ID", "ACCESS_KEY_ID")
    r2_secret_access_key = _env_first("R2_SECRET_ACCESS_KEY", "SECRET_ACCESS_KEY")
    r2_endpoint_url = _env_first("R2_ENDPOINT_URL", "S3_API_KEY")
    default_storage_backend = (
        "r2"
        if all((r2_account_id, r2_bucket, r2_access_key_id, r2_secret_access_key))
        else "local"
    )

    if not upload_storage_dir.is_absolute():
        upload_storage_dir = repo_root / upload_storage_dir
    if not parsed_storage_dir.is_absolute():
        parsed_storage_dir = repo_root / parsed_storage_dir

    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8001")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "50")),
        document_storage_backend=os.getenv("DOCUMENT_STORAGE_BACKEND", default_storage_backend).strip().lower(),
        upload_storage_dir=upload_storage_dir,
        parsed_storage_dir=parsed_storage_dir,
        tokenizer_encoding=os.getenv("TOKENIZER_ENCODING", "cl100k_base"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_checklist_model=os.getenv("GEMINI_CHECKLIST_MODEL", "gemini-3-flash-preview"),
        gemini_review_model=os.getenv("GEMINI_REVIEW_MODEL", "gemini-3-flash-preview"),
        mistral_api_key=os.getenv("MISTRAL_API_KEY"),
        mistral_ocr_model=os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
        mistral_include_image_base64=_env_bool("MISTRAL_INCLUDE_IMAGE_BASE64", False),
        store_parsed_pages_json=_env_bool("STORE_PARSED_PAGES_JSON", False),
        r2_account_id=r2_account_id,
        r2_bucket=r2_bucket,
        r2_access_key_id=r2_access_key_id,
        r2_secret_access_key=r2_secret_access_key,
        r2_endpoint_url=r2_endpoint_url,
        dpa_chunk_size=int(os.getenv("DPA_CHUNK_SIZE", "800")),
        dpa_chunk_overlap=int(os.getenv("DPA_CHUNK_OVERLAP", "300")),
        default_dev_tenant_id=uuid.UUID(os.getenv("DEFAULT_DEV_TENANT_ID", "00000000-0000-0000-0000-000000000001")),
        repo_root=repo_root,
    )
