from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dpa_checklist.schema import ChecklistDocument
from dpa_registry.constants import PARSED_BUCKET, RAW_BUCKET, DEFAULT_SEED_SOURCES
from dpa_registry.db import RegistryRepository
from dpa_registry.diffing import classify_change
from dpa_registry.drafting import DraftContext, generate_candidate_checklist
from dpa_registry.fetchers import fetch_url
from dpa_registry.models import ChangeClass, ReviewDecision, SnapshotParseStatus, SourceRegistryEntry
from dpa_registry.normalize import normalize_html_to_text, sha256_hex
from dpa_registry.storage import StorageBackend


@dataclass
class RegistryService:
    repository: RegistryRepository
    storage: StorageBackend

    def seed(self, actor_id: str) -> int:
        entries = [
            SourceRegistryEntry(
                source_id=src.source_id,
                authority=src.authority,
                celex_or_doc_id=src.celex_or_doc_id,
                source_type=src.source_type,
                languages=list(src.languages),
                status_rule=src.status_rule,
                fetch_url_map=src.fetch_url_map,
            )
            for src in DEFAULT_SEED_SOURCES
        ]
        inserted = self.repository.seed_sources(entries)
        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.seed",
            resource_type="registry_sources",
            resource_id="seed",
            trace_id=_trace_id(),
            details={"inserted": inserted},
        )
        return inserted

    def fetch(self, actor_id: str, source_filter: str | None = None) -> dict[str, int]:
        sources = self.repository.list_sources(source_filter)
        fetched_count = 0
        for source in sources:
            source_pk = source["id"]
            source_id = source["source_id"]
            fetch_url_map: dict[str, str] = source["fetch_url_map"]
            for language, url in fetch_url_map.items():
                document = fetch_url(url=url, language=language)
                sha = sha256_hex(document.body_bytes)
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                raw_object_key = f"{source_id}/{language}/{ts}_{sha}.raw"
                raw_storage_path = self.storage.upload_bytes(
                    bucket=RAW_BUCKET,
                    object_key=raw_object_key,
                    payload=document.body_bytes,
                    content_type=document.content_type or "application/octet-stream",
                )

                parsed_storage_path: str | None = None
                parse_status = SnapshotParseStatus.RAW_ONLY
                normalized_text = ""
                tracked_sections: list[str] = []
                metadata = {"source_url": url, "content_type": document.content_type}
                try:
                    normalized = normalize_html_to_text(document.body_bytes, url=url)
                    normalized_text = normalized.normalized_text
                    tracked_sections = normalized.tracked_sections
                    parsed_payload = normalized_text.encode("utf-8")
                    parsed_object_key = f"{source_id}/{language}/{ts}_{sha}.txt"
                    parsed_storage_path = self.storage.upload_bytes(
                        bucket=PARSED_BUCKET,
                        object_key=parsed_object_key,
                        payload=parsed_payload,
                        content_type="text/plain; charset=utf-8",
                    )
                    metadata.update(normalized.metadata)
                    parse_status = SnapshotParseStatus.PARSED
                except Exception as exc:  # pragma: no cover - defensive path
                    metadata["parse_error"] = str(exc)
                    parse_status = SnapshotParseStatus.FAILED

                self.repository.insert_snapshot(
                    registry_source_id=source_pk,
                    source_id=source_id,
                    language=language,
                    http_etag=document.http_etag,
                    http_last_modified=document.http_last_modified,
                    sha256=sha,
                    raw_storage_path=raw_storage_path,
                    parsed_storage_path=parsed_storage_path,
                    parse_status=parse_status,
                    normalized_text=normalized_text,
                    tracked_sections=tracked_sections,
                    metadata_json=metadata,
                )
                fetched_count += 1

        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.fetch",
            resource_type="registry_sources",
            resource_id=source_filter or "all",
            trace_id=_trace_id(),
            details={"fetched_snapshots": fetched_count},
        )
        return {"fetched_snapshots": fetched_count}

    def diff(self, actor_id: str, source_filter: str | None = None) -> dict[str, int]:
        sources = self.repository.list_sources(source_filter)
        created_diffs = 0
        material_changes = 0
        for source in sources:
            for language in source["languages"]:
                snapshots = self.repository.last_two_snapshots(source["source_id"], language)
                if not snapshots:
                    continue
                current = snapshots[0]
                previous = snapshots[1] if len(snapshots) > 1 else None
                diff = classify_change(
                    previous_text=(previous["normalized_text"] if previous else None),
                    current_text=current["normalized_text"],
                    tracked_sections=current["tracked_sections"] or [],
                )
                self.repository.insert_diff(
                    registry_source_id=source["id"],
                    source_id=source["source_id"],
                    language=language,
                    from_snapshot_id=(previous["id"] if previous else None),
                    to_snapshot_id=current["id"],
                    change_class=diff.change_class,
                    summary=diff.summary,
                    changed_sections=diff.changed_sections,
                    token_change_ratio=diff.token_change_ratio,
                )
                created_diffs += 1
                if diff.change_class == ChangeClass.MATERIAL_CHANGE:
                    material_changes += 1

        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.diff",
            resource_type="registry_sources",
            resource_id=source_filter or "all",
            trace_id=_trace_id(),
            details={"created_diffs": created_diffs, "material_changes": material_changes},
        )
        return {"created_diffs": created_diffs, "material_changes": material_changes}

    def draft(
        self,
        *,
        actor_id: str,
        policy_version: str,
        from_file: str | None = None,
    ) -> dict[str, str]:
        material_diffs = self.repository.latest_material_diffs()
        if not material_diffs:
            raise RuntimeError("No material diffs available. Draft generation skipped.")

        changed_sections: list[str] = []
        snapshot_ids: list[str] = []
        for diff in material_diffs:
            changed_sections.extend(diff["changed_sections"] or [])
            snapshot_ids.append(str(diff["to_snapshot_id"]))

        if from_file:
            payload = json.loads(Path(from_file).read_text(encoding="utf-8"))
            checklist = ChecklistDocument.model_validate(payload)
        else:
            active = self.repository.get_active_checklist()
            checklist = generate_candidate_checklist(
                DraftContext(
                    policy_version=policy_version,
                    changed_sections=changed_sections,
                    prior_checklist_json=(active["checklist_json"] if active else None),
                ),
                retries=2,
            )

        version_pk, version_id = self.repository.create_checklist_candidate(
            checklist_document=checklist,
            generated_from_snapshot_set=snapshot_ids,
            created_by=actor_id,
        )
        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.draft",
            resource_type="checklist_versions",
            resource_id=version_id,
            trace_id=_trace_id(),
            details={"version_pk": str(version_pk), "source_snapshot_count": len(snapshot_ids)},
        )
        return {"version_id": version_id}

    def review(self, *, actor_id: str, version_id: str, decision: ReviewDecision, comment: str | None) -> None:
        self.repository.mark_review(version_id=version_id, reviewer_id=actor_id, decision=decision, comment=comment)
        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.review",
            resource_type="checklist_versions",
            resource_id=version_id,
            trace_id=_trace_id(),
            details={"decision": decision.value, "comment": comment},
        )

    def approve(self, *, actor_id: str, version_id: str, notes: str | None) -> None:
        self.repository.approve_and_promote(version_id=version_id, approver_id=actor_id, notes=notes)
        self.repository.add_registry_audit_event(
            actor_type="user",
            actor_id=actor_id,
            event_name="registry.approve",
            resource_type="checklist_versions",
            resource_id=version_id,
            trace_id=_trace_id(),
            details={"action": "APPROVED_AND_PROMOTED", "notes": notes},
        )

    def status(self) -> dict[str, Any]:
        return self.repository.status_summary()


def _trace_id() -> str:
    return uuid.uuid4().hex
