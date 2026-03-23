from __future__ import annotations

import uuid
from pathlib import Path

from upload_api.storage import ArtifactStore, _R2ArtifactBackend, parse_r2_uri


def test_parse_r2_uri_round_trips_bucket_and_key() -> None:
    bucket, key = parse_r2_uri("r2://docs/tenants/a/projects/b/documents/c/source/original.pdf")
    assert bucket == "docs"
    assert key == "tenants/a/projects/b/documents/c/source/original.pdf"


def test_local_artifact_store_writes_and_reads_round_trip(tmp_path: Path) -> None:
    store = ArtifactStore(
        primary_backend="local",
        upload_dir=tmp_path / "uploads",
        parsed_dir=tmp_path / "parsed",
    )
    tenant_id = uuid.uuid4()
    project_id = uuid.uuid4()
    document_id = uuid.uuid4()

    upload = store.save_upload(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        filename="sample.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    parsed = store.save_parsed_markdown(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        text="page_no: 1\npage_text:\nHello\npage_images: []\n",
    )

    assert Path(upload.object_uri).exists()
    assert store.read_bytes(upload.object_uri) == b"%PDF-1.4"
    assert "Hello" in store.read_text(parsed.object_uri)


def test_r2_artifact_store_uses_r2_backend_and_temp_materialization(tmp_path: Path) -> None:
    class _Body:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class _FakeClient:
        def __init__(self) -> None:
            self.objects: dict[tuple[str, str], bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str):  # noqa: ARG002,N803
            self.objects[(Bucket, Key)] = Body

        def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
            return {"Body": _Body(self.objects[(Bucket, Key)])}

    fake_client = _FakeClient()
    store = ArtifactStore(
        primary_backend="r2",
        upload_dir=tmp_path / "uploads",
        parsed_dir=tmp_path / "parsed",
        r2_backend=_R2ArtifactBackend(
            account_id="acct",
            bucket="docs",
            access_key_id="key",
            secret_access_key="secret",
            client=fake_client,
        ),
    )

    artifact = store.save_parsed_markdown(
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text="hello from r2",
    )

    assert artifact.object_uri.startswith("r2://docs/")
    assert store.read_text(artifact.object_uri) == "hello from r2"
    with store.local_path_for_processing(artifact.object_uri, suffix=".md") as local_path:
        assert local_path.read_text(encoding="utf-8") == "hello from r2"
