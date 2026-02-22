from __future__ import annotations

import argparse
import json
import os
from typing import Any

from dpa_registry.db import RegistryRepository
from dpa_registry.models import ReviewDecision
from dpa_registry.service import RegistryService
from dpa_registry.storage import get_storage_backend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Curated legal source registry CLI")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="Postgres connection string")
    parser.add_argument("--actor-id", default="registry-operator", help="Actor identifier for audit logs")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("seed", help="Seed canonical source definitions")

    fetch = subparsers.add_parser("fetch", help="Fetch source snapshots")
    fetch.add_argument("--source-id", default=None, help="Optional source filter")

    diff = subparsers.add_parser("diff", help="Compute source diffs from latest snapshots")
    diff.add_argument("--source-id", default=None, help="Optional source filter")

    draft = subparsers.add_parser("draft", help="Generate checklist draft from material diffs")
    draft.add_argument("--policy-version", required=True, help="Policy version string")
    draft.add_argument("--from-file", default=None, help="Use local checklist JSON instead of OpenRouter")

    review = subparsers.add_parser("review", help="Mark checklist draft as reviewed/rejected")
    review.add_argument("--version-id", required=True)
    review.add_argument("--decision", choices=[d.value for d in ReviewDecision], required=True)
    review.add_argument("--comment", default=None)

    approve = subparsers.add_parser("approve", help="Approve checklist and auto-promote to active")
    approve.add_argument("--version-id", required=True)
    approve.add_argument("--notes", default=None)

    subparsers.add_parser("status", help="Show registry and checklist status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    repository = RegistryRepository.from_url(args.database_url)
    service = RegistryService(repository=repository, storage=get_storage_backend())

    result: dict[str, Any] | None = None

    if args.command == "seed":
        inserted = service.seed(actor_id=args.actor_id)
        result = {"inserted_sources": inserted}
    elif args.command == "fetch":
        result = service.fetch(actor_id=args.actor_id, source_filter=args.source_id)
    elif args.command == "diff":
        result = service.diff(actor_id=args.actor_id, source_filter=args.source_id)
    elif args.command == "draft":
        result = service.draft(
            actor_id=args.actor_id,
            policy_version=args.policy_version,
            from_file=args.from_file,
        )
    elif args.command == "review":
        service.review(
            actor_id=args.actor_id,
            version_id=args.version_id,
            decision=ReviewDecision(args.decision),
            comment=args.comment,
        )
        result = {"version_id": args.version_id, "decision": args.decision}
    elif args.command == "approve":
        service.approve(actor_id=args.actor_id, version_id=args.version_id, notes=args.notes)
        result = {"version_id": args.version_id, "status": "ACTIVE"}
    elif args.command == "status":
        result = service.status()
    else:  # pragma: no cover
        parser.error(f"Unknown command: {args.command}")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
