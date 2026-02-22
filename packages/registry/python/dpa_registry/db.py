from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, and_, create_engine, select, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.engine import Engine

from dpa_checklist.schema import ChecklistDocument
from dpa_registry.models import (
    ApprovalAction,
    ChangeClass,
    ChecklistVersionStatus,
    ReviewDecision,
    SnapshotParseStatus,
    SourceRegistryEntry,
)


metadata = MetaData()

registry_sources_table = Table(
    "registry_sources",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("source_id", sa.String, nullable=False),
    sa.Column("authority", sa.String, nullable=False),
    sa.Column("celex_or_doc_id", sa.String, nullable=False),
    sa.Column("source_type", sa.String, nullable=False),
    sa.Column("languages", ARRAY(sa.String), nullable=False),
    sa.Column("status_rule", sa.String, nullable=False),
    sa.Column("fetch_url_map", JSONB, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False),
)

registry_snapshots_table = Table(
    "registry_snapshots",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("registry_source_id", UUID(as_uuid=True), nullable=False),
    sa.Column("source_id", sa.String, nullable=False),
    sa.Column("language", sa.String, nullable=False),
    sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("http_etag", sa.String),
    sa.Column("http_last_modified", sa.String),
    sa.Column("sha256", sa.String, nullable=False),
    sa.Column("raw_storage_path", sa.String, nullable=False),
    sa.Column("parsed_storage_path", sa.String),
    sa.Column("parse_status", sa.String, nullable=False),
    sa.Column("normalized_text", sa.Text, nullable=False),
    sa.Column("tracked_sections", JSONB, nullable=False),
    sa.Column("metadata", JSONB, nullable=False),
)

registry_diffs_table = Table(
    "registry_diffs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("registry_source_id", UUID(as_uuid=True), nullable=False),
    sa.Column("source_id", sa.String, nullable=False),
    sa.Column("language", sa.String, nullable=False),
    sa.Column("from_snapshot_id", UUID(as_uuid=True)),
    sa.Column("to_snapshot_id", UUID(as_uuid=True), nullable=False),
    sa.Column("change_class", sa.String, nullable=False),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("changed_sections", JSONB, nullable=False),
    sa.Column("token_change_ratio", sa.Float, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

checklist_versions_table = Table(
    "checklist_versions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("version_id", sa.String, nullable=False),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("is_active", sa.Boolean, nullable=False),
    sa.Column("policy_version", sa.String, nullable=False),
    sa.Column("generated_from_snapshot_set", JSONB, nullable=False),
    sa.Column("governance", JSONB, nullable=False),
    sa.Column("checklist_json", JSONB, nullable=False),
    sa.Column("created_by", sa.String, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("approved_by", sa.String),
    sa.Column("approved_at", sa.TIMESTAMP(timezone=True)),
)

checklist_items_table = Table(
    "checklist_items",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("checklist_version_id", UUID(as_uuid=True), nullable=False),
    sa.Column("check_id", sa.String, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("legal_basis", JSONB, nullable=False),
    sa.Column("required", sa.Boolean, nullable=False),
    sa.Column("severity", sa.String, nullable=False),
    sa.Column("evidence_hint", sa.Text, nullable=False),
    sa.Column("pass_criteria", JSONB, nullable=False),
    sa.Column("fail_criteria", JSONB, nullable=False),
    sa.Column("sort_order", sa.Integer, nullable=False),
)

checklist_item_sources_table = Table(
    "checklist_item_sources",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("checklist_item_id", UUID(as_uuid=True), nullable=False),
    sa.Column("source_type", sa.String, nullable=False),
    sa.Column("authority", sa.String, nullable=False),
    sa.Column("source_ref", sa.Text, nullable=False),
    sa.Column("source_url", sa.Text, nullable=False),
    sa.Column("source_excerpt", sa.Text, nullable=False),
    sa.Column("interpretation_notes", sa.Text),
)

checklist_reviews_table = Table(
    "checklist_reviews",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("checklist_version_id", UUID(as_uuid=True), nullable=False),
    sa.Column("reviewer_id", sa.String, nullable=False),
    sa.Column("decision", sa.String, nullable=False),
    sa.Column("comment", sa.Text),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

checklist_approvals_table = Table(
    "checklist_approvals",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("checklist_version_id", UUID(as_uuid=True), nullable=False),
    sa.Column("approver_id", sa.String, nullable=False),
    sa.Column("action", sa.String, nullable=False),
    sa.Column("notes", sa.Text),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

registry_audit_events_table = Table(
    "registry_audit_events",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("actor_type", sa.String, nullable=False),
    sa.Column("actor_id", sa.String, nullable=False),
    sa.Column("event_name", sa.String, nullable=False),
    sa.Column("resource_type", sa.String, nullable=False),
    sa.Column("resource_id", sa.String, nullable=False),
    sa.Column("trace_id", sa.String, nullable=False),
    sa.Column("details", JSONB, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RegistryRepository:
    engine: Engine

    @classmethod
    def from_url(cls, database_url: str) -> "RegistryRepository":
        return cls(engine=create_engine(database_url, future=True))

    def seed_sources(self, sources: list[SourceRegistryEntry]) -> int:
        inserted = 0
        with self.engine.begin() as conn:
            for source in sources:
                existing = conn.execute(
                    select(registry_sources_table.c.id).where(registry_sources_table.c.source_id == source.source_id)
                ).first()
                if existing:
                    continue
                conn.execute(
                    registry_sources_table.insert().values(
                        id=uuid.uuid4(),
                        source_id=source.source_id,
                        authority=source.authority,
                        celex_or_doc_id=source.celex_or_doc_id,
                        source_type=source.source_type.value,
                        languages=source.languages,
                        status_rule=source.status_rule,
                        fetch_url_map=source.fetch_url_map,
                        enabled=True,
                    )
                )
                inserted += 1
        return inserted

    def list_sources(self, source_id: str | None = None) -> list[dict[str, Any]]:
        query = select(registry_sources_table)
        if source_id:
            query = query.where(registry_sources_table.c.source_id == source_id)
        with self.engine.begin() as conn:
            rows = conn.execute(query.order_by(registry_sources_table.c.source_id.asc())).mappings().all()
        return [dict(row) for row in rows]

    def insert_snapshot(
        self,
        *,
        registry_source_id: uuid.UUID,
        source_id: str,
        language: str,
        http_etag: str | None,
        http_last_modified: str | None,
        sha256: str,
        raw_storage_path: str,
        parsed_storage_path: str | None,
        parse_status: SnapshotParseStatus,
        normalized_text: str,
        tracked_sections: list[str],
        metadata_json: dict[str, Any],
    ) -> uuid.UUID:
        snapshot_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                registry_snapshots_table.insert().values(
                    id=snapshot_id,
                    registry_source_id=registry_source_id,
                    source_id=source_id,
                    language=language,
                    fetched_at=utcnow(),
                    http_etag=http_etag,
                    http_last_modified=http_last_modified,
                    sha256=sha256,
                    raw_storage_path=raw_storage_path,
                    parsed_storage_path=parsed_storage_path,
                    parse_status=parse_status.value,
                    normalized_text=normalized_text,
                    tracked_sections=tracked_sections,
                    metadata=metadata_json,
                )
            )
        return snapshot_id

    def last_two_snapshots(self, source_id: str, language: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(registry_snapshots_table)
                .where(
                    and_(
                        registry_snapshots_table.c.source_id == source_id,
                        registry_snapshots_table.c.language == language,
                    )
                )
                .order_by(registry_snapshots_table.c.fetched_at.desc())
                .limit(2)
            ).mappings().all()
        return [dict(row) for row in rows]

    def insert_diff(
        self,
        *,
        registry_source_id: uuid.UUID,
        source_id: str,
        language: str,
        from_snapshot_id: uuid.UUID | None,
        to_snapshot_id: uuid.UUID,
        change_class: ChangeClass,
        summary: str,
        changed_sections: list[str],
        token_change_ratio: float,
    ) -> uuid.UUID:
        diff_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                registry_diffs_table.insert().values(
                    id=diff_id,
                    registry_source_id=registry_source_id,
                    source_id=source_id,
                    language=language,
                    from_snapshot_id=from_snapshot_id,
                    to_snapshot_id=to_snapshot_id,
                    change_class=change_class.value,
                    summary=summary,
                    changed_sections=changed_sections,
                    token_change_ratio=token_change_ratio,
                    created_at=utcnow(),
                )
            )
        return diff_id

    def latest_material_diffs(self) -> list[dict[str, Any]]:
        query = sa.text(
            """
            SELECT DISTINCT ON (source_id, language)
              id, registry_source_id, source_id, language, from_snapshot_id, to_snapshot_id,
              change_class, summary, changed_sections, token_change_ratio, created_at
            FROM registry_diffs
            WHERE change_class = 'MATERIAL_CHANGE'
            ORDER BY source_id, language, created_at DESC
            """
        )
        with self.engine.begin() as conn:
            rows = conn.execute(query).mappings().all()
        return [dict(row) for row in rows]

    def snapshot_by_id(self, snapshot_id: uuid.UUID) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(registry_snapshots_table).where(registry_snapshots_table.c.id == snapshot_id)
            ).mappings().first()
        return dict(row) if row else None

    def get_active_checklist(self) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(checklist_versions_table).where(checklist_versions_table.c.is_active.is_(True))
            ).mappings().first()
        return dict(row) if row else None

    def create_checklist_candidate(
        self,
        *,
        checklist_document: ChecklistDocument,
        generated_from_snapshot_set: list[str],
        created_by: str,
    ) -> tuple[uuid.UUID, str]:
        checklist_version_pk = uuid.uuid4()
        version_id = f"checklist_{utcnow().strftime('%Y%m%d_%H%M%S')}"
        now = utcnow()
        payload = checklist_document.model_dump(mode="json")
        with self.engine.begin() as conn:
            conn.execute(
                checklist_versions_table.insert().values(
                    id=checklist_version_pk,
                    version_id=version_id,
                    status=ChecklistVersionStatus.DRAFT.value,
                    is_active=False,
                    policy_version=checklist_document.governance.policy_version,
                    generated_from_snapshot_set=generated_from_snapshot_set,
                    governance=checklist_document.governance.model_dump(mode="json"),
                    checklist_json=payload,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                )
            )

            for idx, check in enumerate(checklist_document.checks):
                item_pk = uuid.uuid4()
                conn.execute(
                    checklist_items_table.insert().values(
                        id=item_pk,
                        checklist_version_id=checklist_version_pk,
                        check_id=check.check_id,
                        title=check.title,
                        category=check.category,
                        legal_basis=check.legal_basis,
                        required=check.required,
                        severity=check.severity.value,
                        evidence_hint=check.evidence_hint,
                        pass_criteria=check.pass_criteria,
                        fail_criteria=check.fail_criteria,
                        sort_order=idx,
                    )
                )
                for source in check.sources:
                    conn.execute(
                        checklist_item_sources_table.insert().values(
                            id=uuid.uuid4(),
                            checklist_item_id=item_pk,
                            source_type=source.source_type.value,
                            authority=source.authority,
                            source_ref=source.source_ref,
                            source_url=str(source.source_url),
                            source_excerpt=source.source_excerpt,
                            interpretation_notes=source.interpretation_notes,
                        )
                    )
        return checklist_version_pk, version_id

    def mark_review(
        self,
        *,
        version_id: str,
        reviewer_id: str,
        decision: ReviewDecision,
        comment: str | None,
    ) -> None:
        now = utcnow()
        with self.engine.begin() as conn:
            version = conn.execute(
                select(checklist_versions_table.c.id).where(checklist_versions_table.c.version_id == version_id)
            ).first()
            if not version:
                raise ValueError(f"Unknown version_id: {version_id}")
            version_pk = version[0]
            conn.execute(
                checklist_versions_table.update()
                .where(checklist_versions_table.c.id == version_pk)
                .values(status=decision.value, updated_at=now)
            )
            conn.execute(
                checklist_reviews_table.insert().values(
                    id=uuid.uuid4(),
                    checklist_version_id=version_pk,
                    reviewer_id=reviewer_id,
                    decision=decision.value,
                    comment=comment,
                    created_at=now,
                )
            )

    def approve_and_promote(self, *, version_id: str, approver_id: str, notes: str | None = None) -> None:
        now = utcnow()
        with self.engine.begin() as conn:
            candidate = conn.execute(
                select(checklist_versions_table).where(checklist_versions_table.c.version_id == version_id)
            ).mappings().first()
            if not candidate:
                raise ValueError(f"Unknown version_id: {version_id}")
            candidate_pk = candidate["id"]

            conn.execute(
                update(checklist_versions_table)
                .where(checklist_versions_table.c.is_active.is_(True))
                .values(
                    is_active=False,
                    status=ChecklistVersionStatus.ARCHIVED.value,
                    updated_at=now,
                )
            )
            conn.execute(
                checklist_versions_table.update()
                .where(checklist_versions_table.c.id == candidate_pk)
                .values(
                    is_active=True,
                    status=ChecklistVersionStatus.ACTIVE.value,
                    approved_by=approver_id,
                    approved_at=now,
                    updated_at=now,
                )
            )
            conn.execute(
                checklist_approvals_table.insert().values(
                    id=uuid.uuid4(),
                    checklist_version_id=candidate_pk,
                    approver_id=approver_id,
                    action=ApprovalAction.APPROVED_AND_PROMOTED.value,
                    notes=notes,
                    created_at=now,
                )
            )

    def get_checklist_version(self, version_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(checklist_versions_table).where(checklist_versions_table.c.version_id == version_id)
            ).mappings().first()
        return dict(row) if row else None

    def add_registry_audit_event(
        self,
        *,
        actor_type: str,
        actor_id: str,
        event_name: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        details: dict[str, Any],
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                registry_audit_events_table.insert().values(
                    id=uuid.uuid4(),
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_name=event_name,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    trace_id=trace_id,
                    details=details,
                    created_at=utcnow(),
                )
            )

    def status_summary(self) -> dict[str, Any]:
        with self.engine.begin() as conn:
            source_count = conn.execute(select(sa.func.count()).select_from(registry_sources_table)).scalar_one()
            snapshot_count = conn.execute(select(sa.func.count()).select_from(registry_snapshots_table)).scalar_one()
            diff_count = conn.execute(select(sa.func.count()).select_from(registry_diffs_table)).scalar_one()
            active = conn.execute(
                select(checklist_versions_table).where(checklist_versions_table.c.is_active.is_(True))
            ).mappings().first()
        return {
            "sources": int(source_count),
            "snapshots": int(snapshot_count),
            "diffs": int(diff_count),
            "active_checklist_version": active["version_id"] if active else None,
            "active_policy_version": active["policy_version"] if active else None,
        }
