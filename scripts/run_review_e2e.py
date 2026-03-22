#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
SCHEMAS_PY = REPO_ROOT / "packages" / "schemas" / "python"
CHECKLIST_PY = REPO_ROOT / "packages" / "checklist" / "python"
EVAL_PY = REPO_ROOT / "packages" / "eval" / "python"

for path in (API_SRC, SCHEMAS_PY, CHECKLIST_PY, EVAL_PY):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from sqlalchemy import desc, func, select  # noqa: E402

from db.models import ApprovedChecklist, Document, DocumentChunk, Project  # noqa: E402
from upload_api.jobs import UploadPipelineService  # noqa: E402
from upload_api.main import service, session_factory, settings  # noqa: E402
from upload_api.schemas import CreateAnalysisRunRequest  # noqa: E402


LOGGER = logging.getLogger("review_e2e")


@dataclass(frozen=True)
class ProjectRunTarget:
    project_id: uuid.UUID
    name: str
    document_id: uuid.UUID
    document_filename: str
    approved_checklist_id: uuid.UUID
    checklist_version: str
    check_count: int
    selected_source_count: int
    chunk_count: int


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _pick_target_project(
    *,
    project_id: str | None,
    project_name: str | None,
) -> ProjectRunTarget:
    with session_factory() as session:
        checklist_subquery = (
            select(
                ApprovedChecklist.project_id.label("project_id"),
                func.max(ApprovedChecklist.created_at).label("latest_created_at"),
            )
            .group_by(ApprovedChecklist.project_id)
            .subquery()
        )

        chunk_counts = (
            select(DocumentChunk.document_id.label("document_id"), func.count(DocumentChunk.id).label("chunk_count"))
            .group_by(DocumentChunk.document_id)
            .subquery()
        )

        stmt = (
            select(Project, Document, ApprovedChecklist, chunk_counts.c.chunk_count)
            .join(Document, Document.project_id == Project.id)
            .join(
                checklist_subquery,
                checklist_subquery.c.project_id == Project.id,
            )
            .join(
                ApprovedChecklist,
                (ApprovedChecklist.project_id == Project.id)
                & (ApprovedChecklist.created_at == checklist_subquery.c.latest_created_at),
            )
            .join(chunk_counts, chunk_counts.c.document_id == Document.id)
            .where(Project.status != "DELETED")
            .where(Document.parse_status == "COMPLETED")
            .order_by(desc(Project.last_activity_at), desc(Project.updated_at))
        )

        rows = session.execute(stmt).all()
        if not rows:
            raise RuntimeError("No completed project with an approved checklist and document chunks was found.")

        matches: list[ProjectRunTarget] = []
        for project, document, approved, chunk_count in rows:
            if project_id and str(project.id) != project_id:
                continue
            if project_name and project.name.lower() != project_name.lower():
                continue
            checklist_json = approved.checklist_json or {}
            checks = checklist_json.get("checks") if isinstance(checklist_json, dict) else []
            check_count = len(checks) if isinstance(checks, list) else 0
            matches.append(
                ProjectRunTarget(
                    project_id=project.id,
                    name=project.name,
                    document_id=document.id,
                    document_filename=document.filename,
                    approved_checklist_id=approved.id,
                    checklist_version=approved.version,
                    check_count=check_count,
                    selected_source_count=len(approved.selected_source_ids or []),
                    chunk_count=int(chunk_count or 0),
                )
            )

        if not matches:
            raise RuntimeError("No project matched the provided filters.")

        if project_id:
            return matches[0]

        exact_test = [row for row in matches if row.name.lower() == "test"]
        if len(exact_test) == 1:
            return exact_test[0]

        if len(matches) == 1:
            return matches[0]

        names = ", ".join(f"{row.name} ({row.project_id})" for row in matches[:5])
        raise RuntimeError(
            "Multiple runnable projects were found. Pass --project-id or --project-name. "
            f"Top matches: {names}"
        )


def _log_target_summary(target: ProjectRunTarget) -> None:
    LOGGER.info("Using project: %s (%s)", target.name, target.project_id)
    LOGGER.info("Document: %s (%s)", target.document_filename, target.document_id)
    LOGGER.info(
        "Checklist version=%s, checks=%s, selected_sources=%s, chunks=%s",
        target.checklist_version,
        target.check_count,
        target.selected_source_count,
        target.chunk_count,
    )
    LOGGER.info("Database URL: %s", settings.database_url)
    LOGGER.info("Review model: %s", settings.gemini_review_model)


async def _wait_for_completion(
    pipeline_service: UploadPipelineService,
    run_id: uuid.UUID,
    *,
    poll_interval: float,
) -> tuple[object, float]:
    start_monotonic = time.perf_counter()
    last_stage: tuple[str | None, str | None, int | None, int | None] | None = None

    while True:
        snapshot = await asyncio.to_thread(pipeline_service.get_analysis_run_snapshot, run_id)
        if snapshot is None:
            raise RuntimeError(f"Analysis run {run_id} disappeared during execution.")

        stage_key = (
            snapshot.status,
            snapshot.stage,
            snapshot.progress_pct,
            getattr(snapshot, "finding_count", None),
        )
        if stage_key != last_stage:
            LOGGER.info(
                "Run update | status=%s stage=%s progress=%s%% findings=%s",
                snapshot.status,
                snapshot.stage,
                snapshot.progress_pct,
                getattr(snapshot, "finding_count", 0),
            )
            if snapshot.message:
                LOGGER.info("Message | %s", snapshot.message)
            if snapshot.error_message:
                LOGGER.error("Error | %s", snapshot.error_message)
            last_stage = stage_key

        if snapshot.status in {"COMPLETED", "FAILED"}:
            elapsed = time.perf_counter() - start_monotonic
            return snapshot, elapsed

        await asyncio.sleep(poll_interval)


def _log_report(run_snapshot, elapsed_seconds: float) -> None:
    report_response = service.get_analysis_report(run_snapshot.analysis_run_id)
    report = report_response.report
    findings = report_response.findings

    LOGGER.info("Run finished in %.2fs", elapsed_seconds)
    LOGGER.info("Persisted latency_ms: %s", getattr(run_snapshot, "latency_ms", None))
    LOGGER.info("Overall score: %s", round(report.overall.score, 2))
    LOGGER.info("Overall risk: %s", report.overall.risk_level)
    LOGGER.info("Overall confidence: %s%%", round(report.confidence * 100))
    LOGGER.info("Summary: %s", report.overall.summary)
    LOGGER.info("Highlights:")
    for item in report.highlights:
        LOGGER.info("  - %s", item)
    LOGGER.info("Next actions:")
    for item in report.next_actions:
        LOGGER.info("  - %s", item)

    LOGGER.info("Per-check findings:")
    for finding in findings:
        assessment = finding.assessment
        LOGGER.info(
            "  %s | %s | status=%s risk=%s confidence=%s%% abstained=%s",
            finding.check_id,
            finding.title,
            assessment.status,
            assessment.risk,
            round(assessment.confidence * 100),
            assessment.abstained,
        )
        if assessment.abstain_reason:
            LOGGER.info("    abstain_reason: %s", assessment.abstain_reason)
        if assessment.missing_elements:
            LOGGER.info("    missing_elements: %s", "; ".join(assessment.missing_elements))
        LOGGER.info("    rationale: %s", assessment.risk_rationale)
        if assessment.evidence_quotes:
            for quote in assessment.evidence_quotes[:3]:
                compact_quote = " ".join(quote.quote.split())
                LOGGER.info("    quote [p.%s]: %s", quote.page, compact_quote[:240])
        if assessment.kb_citations:
            for citation in assessment.kb_citations[:2]:
                LOGGER.info("    kb: %s | %s", citation.source_id, citation.source_ref)


async def run(args: argparse.Namespace) -> int:
    target = _pick_target_project(project_id=args.project_id, project_name=args.project_name)
    _log_target_summary(target)

    payload = CreateAnalysisRunRequest(project_id=target.project_id)
    LOGGER.info("Starting real analysis run using UploadPipelineService.create_analysis_run(...)")
    bootstrap = await service.create_analysis_run(payload)
    LOGGER.info("Analysis run created: %s", bootstrap.analysis_run_id)

    snapshot, elapsed_seconds = await _wait_for_completion(
        service,
        bootstrap.analysis_run_id,
        poll_interval=args.poll_interval,
    )

    if snapshot.status == "FAILED":
        LOGGER.error("Analysis run failed after %.2fs", elapsed_seconds)
        if snapshot.error_message:
            LOGGER.error("Failure detail: %s", snapshot.error_message)
        return 1

    _log_report(snapshot, elapsed_seconds)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real end-to-end final review against the local DB using the app's actual pipeline."
    )
    parser.add_argument("--project-id", help="Explicit project UUID to run.")
    parser.add_argument(
        "--project-name",
        help='Optional project name filter. If omitted, the script prefers a single project named "Test".',
    )
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds for run status.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        LOGGER.error("Interrupted.")
        return 130
    except Exception as exc:
        LOGGER.exception("End-to-end review test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
