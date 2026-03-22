from __future__ import annotations

import json
import re
import uuid
from pathlib import Path


def _safe_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_") or "file"


class LocalStorage:
    def __init__(self, upload_dir: Path, parsed_dir: Path) -> None:
        self.upload_dir = upload_dir
        self.parsed_dir = parsed_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, *, job_id: uuid.UUID, filename: str, data: bytes) -> Path:
        path = self.upload_dir / f"{job_id}_{_safe_slug(filename)}"
        path.write_bytes(data)
        return path

    def save_parsed_markdown(self, *, document_id: uuid.UUID, text: str) -> Path:
        path = self.parsed_dir / f"{document_id}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def save_parsed_pages(self, *, document_id: uuid.UUID, pages: list[dict]) -> Path:
        path = self.parsed_dir / f"{document_id}.pages.json"
        path.write_text(json.dumps({"pages": pages}, indent=2), encoding="utf-8")
        return path
