from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import requests


class StorageBackend(Protocol):
    def upload_bytes(self, bucket: str, object_key: str, payload: bytes, content_type: str) -> str:
        raise NotImplementedError


class LocalStorageBackend:
    def __init__(self, root_dir: str | Path = ".registry_storage") -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def upload_bytes(self, bucket: str, object_key: str, payload: bytes, content_type: str) -> str:
        file_path = self._root / bucket / object_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)
        return file_path.resolve().as_uri()


class SupabaseStorageBackend:
    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._base = supabase_url.rstrip("/")
        self._key = service_role_key

    def upload_bytes(self, bucket: str, object_key: str, payload: bytes, content_type: str) -> str:
        url = f"{self._base}/storage/v1/object/{bucket}/{object_key}"
        response = requests.post(
            url,
            headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            data=payload,
            timeout=60,
        )
        response.raise_for_status()
        return f"supabase://{bucket}/{object_key}"


def get_storage_backend() -> StorageBackend:
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if supabase_url and service_role_key:
        return SupabaseStorageBackend(supabase_url=supabase_url, service_role_key=service_role_key)
    return LocalStorageBackend()
