from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import requests
from pydantic import ValidationError

from dpa_checklist.schema import ChecklistDocument
from dpa_registry.constants import DEFAULT_OPENROUTER_BASE_URL, DEFAULT_OPENROUTER_MODEL


class DraftGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DraftContext:
    policy_version: str
    changed_sections: list[str]
    prior_checklist_json: dict[str, Any] | None


def generate_candidate_checklist(
    context: DraftContext,
    *,
    transport: Callable[[str], str] | None = None,
    retries: int = 2,
) -> ChecklistDocument:
    if transport is None:
        transport = _openrouter_transport

    prompt = _build_prompt(context)
    last_error: Exception | None = None

    for _ in range(retries + 1):
        try:
            raw = transport(prompt)
            payload = json.loads(raw)
            checklist = ChecklistDocument.model_validate(payload)
            _assert_strict_source_requirements(checklist)
            return checklist
        except (json.JSONDecodeError, ValidationError, DraftGenerationError) as exc:
            last_error = exc

    raise DraftGenerationError(f"Checklist draft generation failed closed after retries: {last_error}")


def _assert_strict_source_requirements(checklist: ChecklistDocument) -> None:
    for check in checklist.checks:
        if not check.sources:
            raise DraftGenerationError(f"Check {check.check_id} has no authoritative source entries.")
        for source in check.sources:
            if not source.source_ref or not source.source_url:
                raise DraftGenerationError(f"Check {check.check_id} has incomplete source metadata.")


def _build_prompt(context: DraftContext) -> str:
    prior = json.dumps(context.prior_checklist_json or {}, ensure_ascii=True)
    sections = json.dumps(context.changed_sections[:60], ensure_ascii=True)
    schema = json.dumps(ChecklistDocument.model_json_schema(), ensure_ascii=True)
    return (
        "You generate compliance checklist drafts. "
        "Return strict JSON only and nothing else.\n"
        f"Target policy_version: {context.policy_version}\n"
        f"Changed tracked sections: {sections}\n"
        "Rules:\n"
        "- only include in-force/final/adopted obligations\n"
        "- each check must include at least one authoritative source\n"
        "- include governance block and checks array\n"
        "- no markdown, no comments, output must parse as JSON\n"
        f"Prior checklist context: {prior}\n"
        f"JSON schema: {schema}\n"
    )


def _openrouter_transport(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise DraftGenerationError("OPENROUTER_API_KEY is required for draft generation.")

    model = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    response = requests.post(
        DEFAULT_OPENROUTER_BASE_URL,
        timeout=90,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        },
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise DraftGenerationError("OpenRouter response missing choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "".join(text_parts)
    if not isinstance(content, str) or not content.strip():
        raise DraftGenerationError("OpenRouter response missing textual JSON content.")

    return content
