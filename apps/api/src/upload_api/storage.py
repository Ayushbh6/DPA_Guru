from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

from .config import Settings


R2_URI_SCHEME = "r2://"


def _safe_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_") or "file"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_r2_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith(R2_URI_SCHEME):
        raise ValueError(f"Unsupported R2 URI: {uri}")
    remainder = uri[len(R2_URI_SCHEME) :]
    bucket, _, object_key = remainder.partition("/")
    if not bucket or not object_key:
        raise ValueError(f"Malformed R2 URI: {uri}")
    return bucket, object_key


def build_source_object_key(*, tenant_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".bin"
    return f"tenants/{tenant_id}/projects/{project_id}/documents/{document_id}/source/original{suffix}"


def build_parsed_markdown_object_key(*, tenant_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/projects/{project_id}/documents/{document_id}/parsed/parsed.md"


def build_parsed_pages_object_key(*, tenant_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/projects/{project_id}/documents/{document_id}/parsed/pages.json"


@dataclass(frozen=True)
class StoredArtifact:
    storage_provider: str
    bucket: str | None
    object_key: str
    object_uri: str
    content_type: str
    byte_size: int
    sha256: str


class _LocalArtifactBackend:
    def __init__(self, upload_dir: Path, parsed_dir: Path) -> None:
        self.upload_dir = upload_dir
        self.parsed_dir = parsed_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

    def store_bytes(self, *, object_key: str, data: bytes, content_type: str) -> StoredArtifact:
        path = self._path_for_key(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredArtifact(
            storage_provider="local",
            bucket=self._bucket_name_for_key(object_key),
            object_key=object_key,
            object_uri=str(path.resolve()),
            content_type=content_type,
            byte_size=len(data),
            sha256=_sha256_hex(data),
        )

    def read_bytes(self, uri: str) -> bytes:
        return self.resolve_uri_to_path(uri).read_bytes()

    def read_text(self, uri: str, *, encoding: str = "utf-8") -> str:
        return self.resolve_uri_to_path(uri).read_text(encoding=encoding)

    def read_json(self, uri: str) -> dict[str, Any]:
        return json.loads(self.read_text(uri))

    def resolve_uri_to_path(self, uri: str) -> Path:
        path = Path(uri).expanduser()
        if path.is_absolute():
            return path.resolve()
        raise ValueError(f"Unsupported local artifact URI: {uri}")

    def _bucket_name_for_key(self, object_key: str) -> str:
        return "uploads" if "/source/" in object_key else "parsed"

    def _path_for_key(self, object_key: str) -> Path:
        base_dir = self.upload_dir if "/source/" in object_key else self.parsed_dir
        return (base_dir / object_key).resolve()


class _R2ArtifactBackend:
    def __init__(
        self,
        *,
        account_id: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.account_id = account_id
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url or f"https://{account_id}.r2.cloudflarestorage.com"
        self._client = client

    def store_bytes(self, *, object_key: str, data: bytes, content_type: str) -> StoredArtifact:
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        return StoredArtifact(
            storage_provider="r2",
            bucket=self.bucket,
            object_key=object_key,
            object_uri=f"{R2_URI_SCHEME}{self.bucket}/{object_key}",
            content_type=content_type,
            byte_size=len(data),
            sha256=_sha256_hex(data),
        )

    def read_bytes(self, uri: str) -> bytes:
        bucket, object_key = parse_r2_uri(uri)
        payload = self.client.get_object(Bucket=bucket, Key=object_key)
        body = payload["Body"]
        return body.read()

    def read_text(self, uri: str, *, encoding: str = "utf-8") -> str:
        return self.read_bytes(uri).decode(encoding)

    def read_json(self, uri: str) -> dict[str, Any]:
        return json.loads(self.read_text(uri))

    @property
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        if boto3 is None:  # pragma: no cover - exercised only when dependency is missing
            raise RuntimeError("boto3 is required for R2 artifact storage.")
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name="auto",
        )
        return self._client


class ArtifactStore:
    def __init__(
        self,
        *,
        primary_backend: str,
        upload_dir: Path,
        parsed_dir: Path,
        r2_backend: _R2ArtifactBackend | None = None,
    ) -> None:
        self.primary_backend = primary_backend
        self.local = _LocalArtifactBackend(upload_dir, parsed_dir)
        self.r2 = r2_backend

    @classmethod
    def from_settings(cls, settings: Settings) -> "ArtifactStore":
        backend = settings.document_storage_backend
        if backend not in {"local", "r2"}:
            raise RuntimeError(f"Unsupported DOCUMENT_STORAGE_BACKEND '{backend}'.")
        r2_backend = None
        if settings.r2_bucket and settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key:
            r2_backend = _R2ArtifactBackend(
                account_id=settings.r2_account_id,
                bucket=settings.r2_bucket,
                access_key_id=settings.r2_access_key_id,
                secret_access_key=settings.r2_secret_access_key,
                endpoint_url=settings.r2_endpoint_url,
            )
        if backend == "r2" and r2_backend is None:
            raise RuntimeError("R2 storage backend selected but R2 credentials are incomplete.")
        return cls(
            primary_backend=backend,
            upload_dir=settings.upload_storage_dir,
            parsed_dir=settings.parsed_storage_dir,
            r2_backend=r2_backend,
        )

    def save_upload(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> StoredArtifact:
        object_key = build_source_object_key(
            tenant_id=tenant_id,
            project_id=project_id,
            document_id=document_id,
            filename=filename,
        )
        return self._writer_backend().store_bytes(object_key=object_key, data=data, content_type=content_type)

    def save_parsed_markdown(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        text: str,
    ) -> StoredArtifact:
        object_key = build_parsed_markdown_object_key(
            tenant_id=tenant_id,
            project_id=project_id,
            document_id=document_id,
        )
        return self._writer_backend().store_bytes(
            object_key=object_key,
            data=text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )

    def save_parsed_pages(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        pages: list[dict[str, Any]],
    ) -> StoredArtifact:
        object_key = build_parsed_pages_object_key(
            tenant_id=tenant_id,
            project_id=project_id,
            document_id=document_id,
        )
        payload = json.dumps({"pages": pages}, indent=2).encode("utf-8")
        return self._writer_backend().store_bytes(
            object_key=object_key,
            data=payload,
            content_type="application/json",
        )

    def read_bytes(self, uri: str) -> bytes:
        return self._backend_for_uri(uri).read_bytes(uri)

    def read_text(self, uri: str, *, encoding: str = "utf-8") -> str:
        return self._backend_for_uri(uri).read_text(uri, encoding=encoding)

    def read_json(self, uri: str) -> dict[str, Any]:
        return self._backend_for_uri(uri).read_json(uri)

    @contextmanager
    def local_path_for_processing(self, uri: str, *, suffix: str = ""):
        if uri.startswith(R2_URI_SCHEME):
            temp_path = self._download_r2_to_temp(uri, suffix=suffix)
            try:
                yield temp_path
            finally:
                temp_path.unlink(missing_ok=True)
            return
        yield self.local.resolve_uri_to_path(uri)

    def _backend_for_uri(self, uri: str):
        if uri.startswith(R2_URI_SCHEME):
            if self.r2 is None:
                raise RuntimeError("R2 artifact requested but R2 backend is not configured.")
            return self.r2
        return self.local

    def _writer_backend(self):
        if self.primary_backend == "r2":
            if self.r2 is None:
                raise RuntimeError("R2 artifact storage is not configured.")
            return self.r2
        return self.local

    def _download_r2_to_temp(self, uri: str, *, suffix: str) -> Path:
        payload = self.read_bytes(uri)
        fd, temp_name = tempfile.mkstemp(suffix=suffix or "")
        os.close(fd)
        path = Path(temp_name)
        path.write_bytes(payload)
        return path
