from __future__ import annotations

import os
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} must be set.")
    return value.strip()


def _require_env_int(name: str) -> int:
    raw = _require_env(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def _require_env_uuid(name: str) -> uuid.UUID:
    raw = _require_env(name)
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a valid UUID.") from exc


def _require_env_bool(name: str) -> bool:
    raw = _require_env(name).lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean.")


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


def _env_list(name: str, default: list[str]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return tuple(default)
    stripped = value.strip()
    if stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:  # pragma: no cover - config validation
            raise RuntimeError(f"{name} must be valid JSON when using array syntax.") from exc
        if not isinstance(payload, list) or not all(isinstance(item, str) and item.strip() for item in payload):
            raise RuntimeError(f"{name} JSON value must be an array of non-empty strings.")
        return tuple(item.strip() for item in payload)
    return tuple(item.strip() for item in stripped.split(",") if item.strip())


def _require_env_list(name: str) -> tuple[str, ...]:
    values = _env_list(name, [])
    if not values:
        raise RuntimeError(f"{name} must be set.")
    return values


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_host: str
    api_port: int
    max_upload_mb: int
    max_pdf_pages: int
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
    alpha_users_json: str | None
    alpha_bootstrap_owner_username: str
    session_secret: str
    session_cookie_secure: bool
    session_cookie_domain: str | None
    app_allowed_origins: tuple[str, ...]
    alpha_max_projects_per_user: int
    alpha_max_documents_per_user: int
    alpha_max_check_runs_per_user: int
    alpha_max_total_documents: int
    alpha_max_total_active_storage_mb: int
    login_rate_limit_per_ip: int
    login_rate_limit_per_username: int
    login_rate_limit_window_seconds: int
    upload_rate_limit_per_user: int
    upload_rate_limit_per_ip: int
    upload_rate_limit_window_seconds: int
    checklist_rate_limit_per_user: int
    checklist_rate_limit_window_seconds: int
    analysis_rate_limit_per_user: int
    analysis_rate_limit_window_seconds: int
    worker_id: str
    worker_concurrency: int
    worker_poll_interval_seconds: int
    worker_lease_duration_seconds: int
    worker_heartbeat_interval_seconds: int
    worker_retry_backoff_first_seconds: int
    worker_retry_backoff_second_seconds: int
    deleted_project_retention_days: int
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
    app_allowed_origins = _require_env_list("APP_ALLOWED_ORIGINS")
    session_secret = _require_env("SESSION_SECRET")
    alpha_users_json = _require_env("ALPHA_USERS_JSON")
    alpha_bootstrap_owner_username = _require_env("ALPHA_BOOTSTRAP_OWNER_USERNAME")

    if not upload_storage_dir.is_absolute():
        upload_storage_dir = repo_root / upload_storage_dir
    if not parsed_storage_dir.is_absolute():
        parsed_storage_dir = repo_root / parsed_storage_dir

    return Settings(
        database_url=_require_env("DATABASE_URL"),
        api_host=_require_env("API_HOST"),
        api_port=_require_env_int("API_PORT"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        max_pdf_pages=int(os.getenv("MAX_PDF_PAGES", "200")),
        document_storage_backend=_require_env("DOCUMENT_STORAGE_BACKEND").strip().lower(),
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
        default_dev_tenant_id=_require_env_uuid("DEFAULT_DEV_TENANT_ID"),
        alpha_users_json=alpha_users_json,
        alpha_bootstrap_owner_username=alpha_bootstrap_owner_username,
        session_secret=session_secret,
        session_cookie_secure=_require_env_bool("SESSION_COOKIE_SECURE"),
        session_cookie_domain=_env_first("SESSION_COOKIE_DOMAIN"),
        app_allowed_origins=app_allowed_origins,
        alpha_max_projects_per_user=int(os.getenv("ALPHA_MAX_PROJECTS_PER_USER", "20")),
        alpha_max_documents_per_user=int(os.getenv("ALPHA_MAX_DOCUMENTS_PER_USER", "8")),
        alpha_max_check_runs_per_user=int(os.getenv("ALPHA_MAX_CHECK_RUNS_PER_USER", "15")),
        alpha_max_total_documents=int(os.getenv("ALPHA_MAX_TOTAL_DOCUMENTS", "50")),
        alpha_max_total_active_storage_mb=int(os.getenv("ALPHA_MAX_TOTAL_ACTIVE_STORAGE_MB", "5000")),
        login_rate_limit_per_ip=int(os.getenv("LOGIN_RATE_LIMIT_PER_IP", "20")),
        login_rate_limit_per_username=int(os.getenv("LOGIN_RATE_LIMIT_PER_USERNAME", "10")),
        login_rate_limit_window_seconds=int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")),
        upload_rate_limit_per_user=int(os.getenv("UPLOAD_RATE_LIMIT_PER_USER", "10")),
        upload_rate_limit_per_ip=int(os.getenv("UPLOAD_RATE_LIMIT_PER_IP", "20")),
        upload_rate_limit_window_seconds=int(os.getenv("UPLOAD_RATE_LIMIT_WINDOW_SECONDS", "600")),
        checklist_rate_limit_per_user=int(os.getenv("CHECKLIST_RATE_LIMIT_PER_USER", "1")),
        checklist_rate_limit_window_seconds=int(os.getenv("CHECKLIST_RATE_LIMIT_WINDOW_SECONDS", "60")),
        analysis_rate_limit_per_user=int(os.getenv("ANALYSIS_RATE_LIMIT_PER_USER", "1")),
        analysis_rate_limit_window_seconds=int(os.getenv("ANALYSIS_RATE_LIMIT_WINDOW_SECONDS", "60")),
        worker_id=os.getenv("WORKER_ID", "worker-1"),
        worker_concurrency=int(os.getenv("WORKER_CONCURRENCY", "2")),
        worker_poll_interval_seconds=int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "1")),
        worker_lease_duration_seconds=int(os.getenv("WORKER_LEASE_DURATION_SECONDS", "90")),
        worker_heartbeat_interval_seconds=int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "15")),
        worker_retry_backoff_first_seconds=int(os.getenv("WORKER_RETRY_BACKOFF_FIRST_SECONDS", "30")),
        worker_retry_backoff_second_seconds=int(os.getenv("WORKER_RETRY_BACKOFF_SECOND_SECONDS", "120")),
        deleted_project_retention_days=int(os.getenv("DELETED_PROJECT_RETENTION_DAYS", "30")),
        repo_root=repo_root,
    )
