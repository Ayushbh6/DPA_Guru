from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from kb_pipeline.config import PipelineConfig
from kb_pipeline.orchestrator import KbPipelineOrchestrator
from kb_pipeline.repository import KbRepository


def _common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kb-dir", default="kb", help="Path to kb folder (default: kb)")
    parser.add_argument("--source-id", action="append", help="Limit to source_id (repeatable)")
    parser.add_argument("--max-chunks", type=int, default=None, help="Limit total chunks (debug/cost control)")
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument("--full-doc-threshold", type=int, default=None)


def _runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llm-concurrency", type=int, default=None)
    parser.add_argument("--embed-concurrency", type=int, default=None)
    parser.add_argument("--upsert-concurrency", type=int, default=None)
    parser.add_argument("--request-retries", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--queue-maxsize", type=int, default=None)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kb-pipeline", description="Production-grade KB ingestion pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Dry-run planning only (no DB writes, no API calls)")
    _common_args(p_plan)

    p_run = sub.add_parser("run", help="Create and execute a new ingest run")
    _common_args(p_run)
    _runtime_args(p_run)

    p_resume = sub.add_parser("resume", help="Resume an interrupted/failed run")
    p_resume.add_argument("--run-id", required=True)
    _runtime_args(p_resume)

    p_status = sub.add_parser("status", help="Show run status")
    p_status.add_argument("--run-id", required=True)

    p_retry = sub.add_parser("retry-failed", help="Retry only failed chunks for a run")
    p_retry.add_argument("--run-id", required=True)
    _runtime_args(p_retry)

    return parser.parse_args()


def _build_config_from_args(args: argparse.Namespace) -> PipelineConfig:
    cfg = PipelineConfig.from_env()

    def maybe(name: str, value: object) -> None:
        nonlocal cfg
        if value is not None:
            cfg = cfg.__class__(**{**cfg.__dict__, name: value})

    maybe("chunk_size", getattr(args, "chunk_size", None))
    maybe("chunk_overlap", getattr(args, "overlap", None))
    maybe("full_doc_threshold_tokens", getattr(args, "full_doc_threshold", None))
    maybe("llm_concurrency", getattr(args, "llm_concurrency", None))
    maybe("embed_concurrency", getattr(args, "embed_concurrency", None))
    maybe("upsert_concurrency", getattr(args, "upsert_concurrency", None))
    maybe("request_retries", getattr(args, "request_retries", None))
    maybe("request_timeout_seconds", getattr(args, "timeout_seconds", None))
    maybe("queue_maxsize", getattr(args, "queue_maxsize", None))
    return cfg


async def _run_async(args: argparse.Namespace) -> int:
    cfg = _build_config_from_args(args)
    repo = KbRepository(cfg.database_url)
    orchestrator = KbPipelineOrchestrator(cfg, repo)

    if args.command == "plan":
        plan = orchestrator.build_plan(kb_dir=args.kb_dir, source_ids=args.source_id, max_chunks=args.max_chunks)
        out = {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "manifest_sha256": plan.manifest_sha256,
            **plan.summary,
            "config": {
                "chunk_size": cfg.chunk_size,
                "chunk_overlap": cfg.chunk_overlap,
                "full_doc_threshold_tokens": cfg.full_doc_threshold_tokens,
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.command == "status":
        repo.assert_schema_ready()
        status = await asyncio.to_thread(repo.status, args.run_id)
        print(json.dumps(status, indent=2, default=str))
        return 0

    cfg.require_runtime_secrets()
    try:
        if args.command == "run":
            result = await orchestrator.run_new(kb_dir=args.kb_dir, source_ids=args.source_id, max_chunks=args.max_chunks)
        elif args.command == "resume":
            result = await orchestrator.resume(args.run_id, failed_only=False)
        elif args.command == "retry-failed":
            result = await orchestrator.resume(args.run_id, failed_only=True)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
    except KeyboardInterrupt:
        if hasattr(args, "run_id") and args.run_id:
            await asyncio.to_thread(repo.cancel_run, args.run_id, "Interrupted by user")
        raise
    print(json.dumps(result, indent=2, default=str))
    return 0


def main() -> int:
    load_dotenv()
    args = _parse_args()
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
