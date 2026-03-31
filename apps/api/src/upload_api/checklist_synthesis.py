from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from statistics import fmean
from threading import Lock
from typing import Any, Callable

from dpa_checklist import (
    ChecklistCategory,
    ChecklistDraftItem,
    ChecklistDraftMeta,
    ChecklistDraftOutput,
    ChecklistSource,
    checklist_category_values,
)
from dpa_checklist.schema import ChecklistSeverity
from google import genai
from google.genai import types
from openai import OpenAI

from .config import Settings


SynthesisProgressCallback = Callable[[str, str, dict[str, Any] | None, int | None], None]
SynthesisTraceCallback = Callable[[str, dict[str, Any]], None]
SynthesisCancelCallback = Callable[[], bool]

_MAX_RATIONALE_LINES = 3
_MAX_RATIONALE_CHARS = 320
_MAX_SOURCE_EXCERPT_CHARS = 220
_MAX_EVIDENCE_HINT_CHARS = 180
_MAX_CRITERION_CHARS = 180
_MAX_SOURCE_COUNT = 4

_SEVERITY_ORDER = {
    ChecklistSeverity.LOW.value: 0,
    ChecklistSeverity.MEDIUM.value: 1,
    ChecklistSeverity.HIGH.value: 2,
    ChecklistSeverity.MANDATORY.value: 3,
}
_CATEGORY_ENUM_VALUES = checklist_category_values()


class ChecklistSynthesisCanceledError(RuntimeError):
    """Raised when the running checklist synthesis should stop after user cancellation."""


@dataclass(frozen=True)
class SynthesisCandidate:
    candidate_id: str
    ordinal: int
    draft_indexes: tuple[int, ...]
    represented_candidate_ids: tuple[str, ...]
    draft_confidences: tuple[float, ...]
    item: ChecklistDraftItem
    compact_payload: dict[str, Any]
    embedding_text: str

    @property
    def average_confidence(self) -> float:
        return round(fmean(self.draft_confidences), 2)


@dataclass(frozen=True)
class ResolvedCheck:
    candidate_ids: tuple[str, ...]
    confidence: float
    item: ChecklistDraftItem


def _category_value(value: ChecklistCategory | str) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _clip_text(value: str, *, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _clip_lines(value: str, *, max_lines: int, max_chars: int) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    text = "\n".join(lines[:max_lines]) if lines else value.strip()
    return _clip_text(text, max_chars=max_chars)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = " ".join(value.split()).strip()
        if not clean:
            continue
        marker = clean.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        output.append(clean)
    return output


def _normalize_source(source: ChecklistSource) -> ChecklistSource:
    payload = source.model_dump(mode="python")
    payload["source_excerpt"] = _clip_text(payload["source_excerpt"], max_chars=_MAX_SOURCE_EXCERPT_CHARS)
    if payload.get("interpretation_notes"):
        payload["interpretation_notes"] = _clip_text(str(payload["interpretation_notes"]), max_chars=160)
    return ChecklistSource.model_validate(payload)


def normalize_check_item(item: ChecklistDraftItem) -> ChecklistDraftItem:
    payload = item.model_dump(mode="python")
    payload["title"] = _clip_text(payload["title"], max_chars=120)
    payload["category"] = _clip_text(_category_value(payload["category"]), max_chars=80)
    payload["legal_basis"] = _dedupe_preserve_order(list(payload["legal_basis"]))
    payload["evidence_hint"] = _clip_text(payload["evidence_hint"], max_chars=_MAX_EVIDENCE_HINT_CHARS)
    payload["pass_criteria"] = [
        _clip_text(value, max_chars=_MAX_CRITERION_CHARS)
        for value in _dedupe_preserve_order(list(payload["pass_criteria"]))
    ]
    payload["fail_criteria"] = [
        _clip_text(value, max_chars=_MAX_CRITERION_CHARS)
        for value in _dedupe_preserve_order(list(payload["fail_criteria"]))
    ]
    payload["sources"] = [
        _normalize_source(ChecklistSource.model_validate(source)).model_dump(mode="python")
        for source in list(payload["sources"])
    ]
    payload["draft_rationale"] = _clip_lines(
        payload["draft_rationale"],
        max_lines=_MAX_RATIONALE_LINES,
        max_chars=_MAX_RATIONALE_CHARS,
    )
    return ChecklistDraftItem.model_validate(payload)


def normalize_draft_output(payload: ChecklistDraftOutput) -> ChecklistDraftOutput:
    normalized_checks = [normalize_check_item(check) for check in payload.checks]
    meta_payload = payload.meta.model_dump(mode="python")
    meta_payload["selected_source_ids"] = sorted(_dedupe_preserve_order(list(meta_payload["selected_source_ids"])))
    meta_payload["open_questions"] = _dedupe_preserve_order(list(meta_payload["open_questions"]))
    if meta_payload.get("generation_summary"):
        meta_payload["generation_summary"] = _clip_text(str(meta_payload["generation_summary"]), max_chars=240)
    return ChecklistDraftOutput(
        version=payload.version,
        meta=ChecklistDraftMeta.model_validate(meta_payload),
        checks=normalized_checks,
    )


def _normalize_fingerprint_text(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _check_fingerprint(item: ChecklistDraftItem) -> tuple[Any, ...]:
    normalized = normalize_check_item(item)
    severity = normalized.severity.value if hasattr(normalized.severity, "value") else str(normalized.severity)
    return (
        _normalize_fingerprint_text(normalized.title),
        _normalize_fingerprint_text(_category_value(normalized.category)),
        tuple(sorted(_normalize_fingerprint_text(value) for value in normalized.legal_basis)),
        bool(normalized.required),
        severity,
        tuple(sorted(_normalize_fingerprint_text(value) for value in normalized.pass_criteria)),
        tuple(sorted(_normalize_fingerprint_text(value) for value in normalized.fail_criteria)),
    )


def _compact_source_payload(source: ChecklistSource) -> dict[str, Any]:
    return {
        "source_type": source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type),
        "authority": source.authority,
        "source_ref": source.source_ref,
        "source_url": str(source.source_url),
        "source_excerpt": _clip_text(source.source_excerpt, max_chars=_MAX_SOURCE_EXCERPT_CHARS),
    }


def _candidate_embedding_text(item: ChecklistDraftItem) -> str:
    source_refs = ", ".join(source.source_ref for source in item.sources[:_MAX_SOURCE_COUNT])
    severity = item.severity.value if hasattr(item.severity, "value") else str(item.severity)
    return "\n".join(
        [
            f"Title: {item.title}",
            f"Category: {_category_value(item.category)}",
            f"Legal Basis: {', '.join(item.legal_basis)}",
            f"Required: {item.required}",
            f"Severity: {severity}",
            f"Evidence Hint: {item.evidence_hint}",
            f"Pass Criteria: {' | '.join(item.pass_criteria)}",
            f"Fail Criteria: {' | '.join(item.fail_criteria)}",
            f"Source Refs: {source_refs}",
        ]
    )


def _candidate_payload(candidate: SynthesisCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "title": candidate.item.title,
        "category": _category_value(candidate.item.category),
        "legal_basis": list(candidate.item.legal_basis),
        "required": candidate.item.required,
        "severity": candidate.item.severity.value if hasattr(candidate.item.severity, "value") else str(candidate.item.severity),
        "evidence_hint": candidate.item.evidence_hint,
        "pass_criteria": list(candidate.item.pass_criteria),
        "fail_criteria": list(candidate.item.fail_criteria),
        "sources": [_compact_source_payload(source) for source in candidate.item.sources[:_MAX_SOURCE_COUNT]],
        "draft_rationale": candidate.item.draft_rationale,
    }


def _build_candidate(
    *,
    candidate_id: str,
    ordinal: int,
    draft_indexes: tuple[int, ...],
    represented_candidate_ids: tuple[str, ...],
    draft_confidences: tuple[float, ...],
    item: ChecklistDraftItem,
) -> SynthesisCandidate:
    compact_item = normalize_check_item(item)
    candidate = SynthesisCandidate(
        candidate_id=candidate_id,
        ordinal=ordinal,
        draft_indexes=draft_indexes,
        represented_candidate_ids=represented_candidate_ids,
        draft_confidences=draft_confidences,
        item=compact_item,
        compact_payload={},
        embedding_text="",
    )
    return SynthesisCandidate(
        candidate_id=candidate.candidate_id,
        ordinal=candidate.ordinal,
        draft_indexes=candidate.draft_indexes,
        represented_candidate_ids=candidate.represented_candidate_ids,
        draft_confidences=candidate.draft_confidences,
        item=candidate.item,
        compact_payload=_candidate_payload(candidate),
        embedding_text=_candidate_embedding_text(candidate.item),
    )


def build_synthesis_candidates(drafts: list[ChecklistDraftOutput]) -> list[SynthesisCandidate]:
    candidates: list[SynthesisCandidate] = []
    ordinal = 0
    for draft_index, draft in enumerate(drafts, start=1):
        normalized_draft = normalize_draft_output(draft)
        for check_index, item in enumerate(normalized_draft.checks, start=1):
            candidate_id = f"D{draft_index:02d}_C{check_index:03d}"
            candidates.append(
                _build_candidate(
                    candidate_id=candidate_id,
                    ordinal=ordinal,
                    draft_indexes=(draft_index,),
                    represented_candidate_ids=(candidate_id,),
                    draft_confidences=(normalized_draft.meta.confidence,),
                    item=item,
                )
            )
            ordinal += 1
    return candidates


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(l * r for l, r in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)


def _merge_items_deterministically(
    model_item: ChecklistDraftItem,
    original_items: list[ChecklistDraftItem],
) -> ChecklistDraftItem:
    payload = model_item.model_dump(mode="python")
    payload["required"] = bool(payload["required"]) or any(item.required for item in original_items)
    payload["severity"] = max(
        [
            payload["severity"],
            *[
                item.severity.value if hasattr(item.severity, "value") else str(item.severity)
                for item in original_items
            ],
        ],
        key=lambda value: _SEVERITY_ORDER.get(value, -1),
    )
    payload["legal_basis"] = _dedupe_preserve_order(
        [basis for item in original_items for basis in item.legal_basis] + list(payload["legal_basis"])
    )
    payload["pass_criteria"] = _dedupe_preserve_order(
        [criterion for item in original_items for criterion in item.pass_criteria] + list(payload["pass_criteria"])
    )
    payload["fail_criteria"] = _dedupe_preserve_order(
        [criterion for item in original_items for criterion in item.fail_criteria] + list(payload["fail_criteria"])
    )
    source_rows: list[dict[str, Any]] = []
    for item in original_items:
        source_rows.extend(source.model_dump(mode="python") for source in item.sources)
    source_rows.extend(source.model_dump(mode="python") for source in model_item.sources)

    unique_sources: list[ChecklistSource] = []
    seen_sources: set[tuple[str, str, str]] = set()
    for row in source_rows:
        source = _normalize_source(ChecklistSource.model_validate(row))
        key = (source.authority.casefold(), source.source_ref.casefold(), str(source.source_url))
        if key in seen_sources:
            continue
        seen_sources.add(key)
        unique_sources.append(source)
    payload["sources"] = [source.model_dump(mode="python") for source in unique_sources]
    return normalize_check_item(ChecklistDraftItem.model_validate(payload))


def collapse_exact_duplicate_candidates(
    candidates: list[SynthesisCandidate],
) -> tuple[list[SynthesisCandidate], int, list[list[str]]]:
    deduped: list[SynthesisCandidate] = []
    collapsed_groups: list[list[str]] = []
    index_by_fingerprint: dict[tuple[Any, ...], int] = {}

    for candidate in candidates:
        fingerprint = _check_fingerprint(candidate.item)
        existing_index = index_by_fingerprint.get(fingerprint)
        if existing_index is None:
            index_by_fingerprint[fingerprint] = len(deduped)
            deduped.append(candidate)
            continue

        existing = deduped[existing_index]
        merged_item = _merge_items_deterministically(existing.item, [existing.item, candidate.item])
        merged = _build_candidate(
            candidate_id=existing.candidate_id,
            ordinal=min(existing.ordinal, candidate.ordinal),
            draft_indexes=tuple(sorted(set(existing.draft_indexes + candidate.draft_indexes))),
            represented_candidate_ids=tuple(existing.represented_candidate_ids + candidate.represented_candidate_ids),
            draft_confidences=tuple(existing.draft_confidences + candidate.draft_confidences),
            item=merged_item,
        )
        deduped[existing_index] = merged
        if len(existing.represented_candidate_ids) == 1:
            collapsed_groups.append([existing.represented_candidate_ids[0], candidate.candidate_id])
        else:
            collapsed_groups.append([*existing.represented_candidate_ids, candidate.candidate_id])

    removed_count = max(0, len(candidates) - len(deduped))
    return deduped, removed_count, collapsed_groups


def build_semantic_candidate_edges(
    candidates: list[SynthesisCandidate],
    embeddings: list[list[float]],
    *,
    similarity_threshold: float,
    max_neighbors: int,
) -> list[tuple[int, int, float]]:
    if len(candidates) != len(embeddings):
        raise ValueError("candidate and embedding counts must match")

    pair_scores: dict[tuple[int, int], float] = {}
    for index, embedding in enumerate(embeddings):
        scored_neighbors: list[tuple[int, float]] = []
        for other_index, other_embedding in enumerate(embeddings):
            if other_index == index:
                continue
            if set(candidates[index].draft_indexes) & set(candidates[other_index].draft_indexes):
                continue
            score = _cosine_similarity(embedding, other_embedding)
            if score < similarity_threshold:
                continue
            scored_neighbors.append((other_index, score))

        scored_neighbors.sort(key=lambda item: item[1], reverse=True)
        for other_index, score in scored_neighbors[: max(0, max_neighbors)]:
            pair = (min(index, other_index), max(index, other_index))
            existing = pair_scores.get(pair)
            if existing is None or score > existing:
                pair_scores[pair] = score

    return sorted(
        [(left, right, score) for (left, right), score in pair_scores.items()],
        key=lambda item: item[2],
        reverse=True,
    )


def build_semantic_groups(
    candidates: list[SynthesisCandidate],
    edges: list[tuple[int, int, float]],
    *,
    merge_threshold: float,
    max_group_size: int,
) -> list[list[int]]:
    parent = list(range(len(candidates)))
    size = [1] * len(candidates)
    draft_sets = [set(candidate.draft_indexes) for candidate in candidates]

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if size[left_root] < size[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        size[left_root] += size[right_root]
        draft_sets[left_root].update(draft_sets[right_root])

    for left, right, score in edges:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            continue
        if size[left_root] + size[right_root] > max_group_size:
            continue
        if draft_sets[left_root] & draft_sets[right_root]:
            continue
        if size[left_root] > 1 and size[right_root] > 1 and score < merge_threshold:
            continue
        union(left_root, right_root)

    groups: dict[int, list[int]] = {}
    for index in range(len(candidates)):
        groups.setdefault(find(index), []).append(index)
    return sorted(groups.values(), key=lambda group: min(candidates[index].ordinal for index in group))


def build_category_groups(candidates: list[SynthesisCandidate]) -> list[tuple[str, list[int]]]:
    groups: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        category = _category_value(candidate.item.category)
        groups.setdefault(category, []).append(index)
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: min(candidates[index].ordinal for index in item[1]),
    )
    return [(category, indexes) for category, indexes in ordered_groups]


def dedupe_resolved_checks(resolved_checks: list[ResolvedCheck]) -> tuple[list[ResolvedCheck], int]:
    deduped: list[ResolvedCheck] = []
    index_by_fingerprint: dict[tuple[Any, ...], int] = {}

    for resolved in resolved_checks:
        fingerprint = _check_fingerprint(resolved.item)
        existing_index = index_by_fingerprint.get(fingerprint)
        if existing_index is None:
            index_by_fingerprint[fingerprint] = len(deduped)
            deduped.append(resolved)
            continue

        existing = deduped[existing_index]
        merged_item = _merge_items_deterministically(existing.item, [existing.item, resolved.item])
        merged_confidence = round(fmean([existing.confidence, resolved.confidence]), 2)
        deduped[existing_index] = ResolvedCheck(
            candidate_ids=tuple(existing.candidate_ids + resolved.candidate_ids),
            confidence=merged_confidence,
            item=merged_item,
        )

    return deduped, max(0, len(resolved_checks) - len(deduped))


class SemanticGroupChecklistSynthesizer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def synthesize(
        self,
        *,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: SynthesisProgressCallback | None = None,
        trace_cb: SynthesisTraceCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        normalized_drafts = [normalize_draft_output(draft) for draft in drafts]
        candidates = build_synthesis_candidates(normalized_drafts)
        if not candidates:
            raise RuntimeError("Semantic checklist synthesis requires at least one candidate check.")

        deduped_candidates, exact_removed, collapsed_groups = collapse_exact_duplicate_candidates(candidates)
        self._trace(
            trace_cb,
            "exact_duplicates_collapsed",
            {
                "candidate_checks_total": len(candidates),
                "candidate_checks_after_dedupe": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "collapsed_groups": collapsed_groups,
            },
        )
        self._raise_if_cancelled(cancel_check)
        self._progress(
            progress_cb,
            "EMBEDDING_CHECKS",
            "Embedding deduplicated checklist candidates.",
            {
                "current_substage": "EMBEDDING_CHECKS",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
            },
            80,
        )

        embeddings = self._embed_texts([candidate.embedding_text for candidate in deduped_candidates])
        self._raise_if_cancelled(cancel_check)

        edges = build_semantic_candidate_edges(
            deduped_candidates,
            embeddings,
            similarity_threshold=self._settings.checklist_synthesis_group_similarity_threshold,
            max_neighbors=self._settings.checklist_synthesis_group_max_neighbors,
        )
        groups = build_semantic_groups(
            deduped_candidates,
            edges,
            merge_threshold=self._settings.checklist_synthesis_group_merge_threshold,
            max_group_size=self._settings.checklist_synthesis_group_max_size,
        )
        self._trace(
            trace_cb,
            "semantic_groups_formed",
            {
                "candidate_checks_total": len(deduped_candidates),
                "semantic_groups_total": len(groups),
                "edges": [
                    {
                        "left_candidate_id": deduped_candidates[left].candidate_id,
                        "right_candidate_id": deduped_candidates[right].candidate_id,
                        "similarity": round(score, 6),
                    }
                    for left, right, score in edges
                ],
                "groups": [
                    [deduped_candidates[index].candidate_id for index in group]
                    for group in groups
                ],
            },
        )
        self._progress(
            progress_cb,
            "FORMING_SEMANTIC_GROUPS",
            "Formed semantic groups for checklist synthesis.",
            {
                "current_substage": "FORMING_SEMANTIC_GROUPS",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "semantic_groups_total": len(groups),
                "semantic_groups_resolved": 0,
            },
            84,
        )

        resolved_checks: list[ResolvedCheck] = []
        self._progress(
            progress_cb,
            "RESOLVING_GROUPS",
            "Resolving semantic checklist groups.",
            {
                "current_substage": "RESOLVING_GROUPS",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "semantic_groups_total": len(groups),
                "semantic_groups_resolved": 0,
            },
            88,
        )

        batch_size = max(1, self._settings.checklist_synthesis_group_max_parallel)
        for batch_start in range(0, len(groups), batch_size):
            self._raise_if_cancelled(cancel_check)
            batch = groups[batch_start : batch_start + batch_size]
            batch_results = self._resolve_group_batch(
                batch,
                deduped_candidates,
                user_instruction=user_instruction,
                trace_cb=trace_cb,
            )
            for result in batch_results:
                resolved_checks.extend(result)
            completed = min(len(groups), batch_start + len(batch))
            self._progress(
                progress_cb,
                "RESOLVING_GROUPS",
                f"Resolved {completed}/{len(groups)} semantic groups.",
                {
                    "current_substage": "RESOLVING_GROUPS",
                    "partial_drafts_total": len(normalized_drafts),
                    "candidate_checks_total": len(deduped_candidates),
                    "exact_duplicates_removed": exact_removed,
                    "semantic_groups_total": len(groups),
                    "semantic_groups_resolved": completed,
                },
                88 + int((completed / max(1, len(groups))) * 6),
            )
            self._raise_if_cancelled(cancel_check)

        final_resolved_checks, final_exact_removed = dedupe_resolved_checks(resolved_checks)
        self._progress(
            progress_cb,
            "FINALIZING_OUTPUT",
            "Finalizing the synthesized checklist output.",
            {
                "current_substage": "FINALIZING_OUTPUT",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "semantic_groups_total": len(groups),
                "semantic_groups_resolved": len(groups),
            },
            95,
        )
        self._raise_if_cancelled(cancel_check)

        selected_source_ids = sorted(
            _dedupe_preserve_order(
                [source_id for draft in normalized_drafts for source_id in draft.meta.selected_source_ids]
            )
        )
        open_questions = _dedupe_preserve_order(
            [question for draft in normalized_drafts for question in draft.meta.open_questions]
        )
        draft_confidence = fmean([draft.meta.confidence for draft in normalized_drafts])
        group_confidence = fmean([resolved.confidence for resolved in final_resolved_checks]) if final_resolved_checks else draft_confidence
        confidence = round(min(draft_confidence, group_confidence), 2)
        final_items = [normalize_check_item(resolved.item) for resolved in final_resolved_checks]

        payload = ChecklistDraftOutput(
            version=normalized_drafts[0].version,
            meta=ChecklistDraftMeta(
                selected_source_ids=selected_source_ids,
                confidence=confidence,
                open_questions=open_questions,
                generation_summary=(
                    f"Synthesized {len(candidates)} candidate checks into {len(deduped_candidates)} deduped checks "
                    f"across {len(groups)} semantic groups, producing {len(final_items)} final checks using semantic_groups_v2."
                ),
            ),
            checks=final_items,
        )
        result = normalize_draft_output(payload)
        self._trace(
            trace_cb,
            "finalized",
            {
                "final_check_count": len(result.checks),
                "selected_source_ids": list(result.meta.selected_source_ids),
                "confidence": result.meta.confidence,
                "open_questions": list(result.meta.open_questions),
                "generation_summary": result.meta.generation_summary,
                "final_exact_duplicates_removed": final_exact_removed,
            },
        )
        return result

    def _resolve_group_batch(
        self,
        groups: list[list[int]],
        candidates: list[SynthesisCandidate],
        *,
        user_instruction: str | None,
        trace_cb: SynthesisTraceCallback | None,
    ) -> list[list[ResolvedCheck]]:
        locked_trace_cb = trace_cb
        if trace_cb is not None:
            trace_lock = Lock()

            def locked_trace_cb(event_type: str, payload: dict[str, Any]) -> None:
                with trace_lock:
                    trace_cb(event_type, payload)

        max_workers = max(1, min(self._settings.checklist_synthesis_group_max_parallel, len(groups)))
        if max_workers == 1:
            return [
                self._resolve_group_with_retry(group, candidates, user_instruction=user_instruction, trace_cb=locked_trace_cb)
                for group in groups
            ]

        ordered_results: list[list[ResolvedCheck]] = [[] for _ in groups]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                (
                    index,
                    executor.submit(
                        self._resolve_group_with_retry,
                        group,
                        candidates,
                        user_instruction=user_instruction,
                        trace_cb=locked_trace_cb,
                    ),
                )
                for index, group in enumerate(groups)
            ]
            for index, future in futures:
                ordered_results[index] = future.result()
        return ordered_results

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for semantic checklist synthesis.")
        client = OpenAI(api_key=self._settings.openai_api_key)
        response = client.embeddings.create(model=self._settings.openai_embedding_model, input=texts)
        return [[float(value) for value in row.embedding] for row in response.data]

    def _resolve_group_with_retry(
        self,
        group: list[int],
        candidates: list[SynthesisCandidate],
        *,
        user_instruction: str | None,
        trace_cb: SynthesisTraceCallback | None,
    ) -> list[ResolvedCheck]:
        if len(group) == 1:
            candidate = candidates[group[0]]
            self._trace(
                trace_cb,
                "singleton_retained",
                {
                    "candidate_id": candidate.candidate_id,
                    "payload": candidate.compact_payload,
                    "confidence": candidate.average_confidence,
                },
            )
            return [
                ResolvedCheck(
                    candidate_ids=(candidate.candidate_id,),
                    confidence=candidate.average_confidence,
                    item=normalize_check_item(candidate.item),
                )
            ]

        last_exc: Exception | None = None
        for attempt in range(1, 3):
            try:
                return self._resolve_group(group, candidates, user_instruction=user_instruction, trace_cb=trace_cb)
            except Exception as exc:  # noqa: PERF203 - bounded retries
                last_exc = exc
                self._trace(
                    trace_cb,
                    "group_resolution_retry",
                    {
                        "attempt": attempt,
                        "candidate_ids": [candidates[index].candidate_id for index in group],
                        "error": str(exc),
                    },
                )
        raise RuntimeError(f"Failed to resolve semantic checklist group after retries: {last_exc}")

    def _resolve_group(
        self,
        group: list[int],
        candidates: list[SynthesisCandidate],
        *,
        user_instruction: str | None,
        trace_cb: SynthesisTraceCallback | None,
    ) -> list[ResolvedCheck]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for semantic checklist group resolution.")

        payload = [candidates[index].compact_payload for index in group]
        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            response = client.models.generate_content(
                model=self._settings.gemini_checklist_model,
                contents="\n\n".join(
                    [
                        "Resolve these potentially overlapping DPA checklist items into the minimum correct set of final checks.",
                        f"User instruction: {(user_instruction or '').strip() or 'None provided'}",
                        "These are candidate overlaps, not guaranteed duplicates.",
                        "Merge only true duplicate or near-duplicate obligations. If obligations are materially distinct, keep them separate.",
                        json.dumps(payload, indent=2),
                    ]
                ),
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are resolving a small semantic group of DPA checklist items.\n"
                        "Return the minimum number of final checklist checks needed to preserve all materially distinct obligations.\n"
                        "Every input candidate_id must be represented exactly once across the output.\n"
                        "Only merge checks when they are truly the same obligation."
                    ),
                    response_mime_type="application/json",
                    response_schema=_group_resolution_schema(),
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=768),
                ),
            )
        if not response.text:
            raise RuntimeError("Gemini did not return semantic group resolution output.")

        parsed = json.loads(response.text)
        rows = parsed.get("resolved_checks")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Semantic group resolution returned no checks.")

        candidate_by_id = {candidates[index].candidate_id: candidates[index] for index in group}
        expected_ids = set(candidate_by_id)
        seen_ids: set[str] = set()
        resolved: list[ResolvedCheck] = []

        for row in rows:
            candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
            if not candidate_ids:
                raise RuntimeError("Resolved check row is missing candidate_ids.")
            if any(candidate_id not in candidate_by_id for candidate_id in candidate_ids):
                raise RuntimeError("Semantic group resolution returned unknown candidate ids.")
            overlap = seen_ids & set(candidate_ids)
            if overlap:
                raise RuntimeError(f"Semantic group resolution returned duplicate candidate ids: {sorted(overlap)}")
            seen_ids.update(candidate_ids)

            original_items = [candidate_by_id[candidate_id].item for candidate_id in candidate_ids]
            item = ChecklistDraftItem.model_validate(row["item"])
            merged_item = _merge_items_deterministically(item, original_items)
            confidence = float(row["confidence"])
            resolved.append(
                ResolvedCheck(
                    candidate_ids=tuple(candidate_ids),
                    confidence=round(min(1.0, max(0.0, confidence)), 2),
                    item=merged_item,
                )
            )

        if seen_ids != expected_ids:
            missing = sorted(expected_ids - seen_ids)
            raise RuntimeError(f"Semantic group resolution did not cover every candidate exactly once: {missing}")

        self._trace(
            trace_cb,
            "group_resolved",
            {
                "candidate_ids": [candidates[index].candidate_id for index in group],
                "resolved_checks": [
                    {
                        "candidate_ids": list(check.candidate_ids),
                        "confidence": check.confidence,
                        "item": check.item.model_dump(mode="json"),
                    }
                    for check in resolved
                ],
            },
        )
        return resolved

    @staticmethod
    def _progress(
        progress_cb: SynthesisProgressCallback | None,
        stage: str,
        message: str,
        meta: dict[str, Any] | None,
        progress_pct: int | None,
    ) -> None:
        if progress_cb is not None:
            progress_cb(stage, message, meta, progress_pct)

    @staticmethod
    def _trace(trace_cb: SynthesisTraceCallback | None, event_type: str, payload: dict[str, Any]) -> None:
        if trace_cb is not None:
            trace_cb(event_type, payload)

    @staticmethod
    def _raise_if_cancelled(cancel_check: SynthesisCancelCallback | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ChecklistSynthesisCanceledError("Checklist generation was stopped by the user.")


class CategoryGroupChecklistSynthesizer(SemanticGroupChecklistSynthesizer):
    def synthesize(
        self,
        *,
        drafts: list[ChecklistDraftOutput],
        user_instruction: str | None = None,
        progress_cb: SynthesisProgressCallback | None = None,
        trace_cb: SynthesisTraceCallback | None = None,
        cancel_check: SynthesisCancelCallback | None = None,
    ) -> ChecklistDraftOutput:
        normalized_drafts = [normalize_draft_output(draft) for draft in drafts]
        candidates = build_synthesis_candidates(normalized_drafts)
        if not candidates:
            raise RuntimeError("Category checklist synthesis requires at least one candidate check.")

        deduped_candidates, exact_removed, collapsed_groups = collapse_exact_duplicate_candidates(candidates)
        self._trace(
            trace_cb,
            "exact_duplicates_collapsed",
            {
                "candidate_checks_total": len(candidates),
                "candidate_checks_after_dedupe": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "collapsed_groups": collapsed_groups,
            },
        )
        self._raise_if_cancelled(cancel_check)

        groups = build_category_groups(deduped_candidates)
        self._trace(
            trace_cb,
            "category_groups_formed",
            {
                "candidate_checks_total": len(deduped_candidates),
                "merge_groups_total": len(groups),
                "groups": [
                    {
                        "category": category,
                        "candidate_ids": [deduped_candidates[index].candidate_id for index in group],
                    }
                    for category, group in groups
                ],
            },
        )
        self._progress(
            progress_cb,
            "GROUPING_CATEGORIES",
            "Grouped checklist candidates by fixed category.",
            {
                "current_substage": "GROUPING_CATEGORIES",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "merge_groups_total": len(groups),
                "merge_groups_completed": 0,
            },
            82,
        )

        resolved_checks: list[ResolvedCheck] = []
        self._progress(
            progress_cb,
            "RESOLVING_GROUPS",
            "Resolving category groups into final checklist checks.",
            {
                "current_substage": "RESOLVING_GROUPS",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "merge_groups_total": len(groups),
                "merge_groups_completed": 0,
            },
            88,
        )

        batch_size = max(1, self._settings.checklist_synthesis_group_max_parallel)
        category_group_indexes = [group for _category, group in groups]
        for batch_start in range(0, len(category_group_indexes), batch_size):
            self._raise_if_cancelled(cancel_check)
            batch = category_group_indexes[batch_start : batch_start + batch_size]
            batch_results = self._resolve_group_batch(
                batch,
                deduped_candidates,
                user_instruction=user_instruction,
                trace_cb=trace_cb,
            )
            for result in batch_results:
                resolved_checks.extend(result)
            completed = min(len(category_group_indexes), batch_start + len(batch))
            self._progress(
                progress_cb,
                "RESOLVING_GROUPS",
                f"Resolved {completed}/{len(category_group_indexes)} category groups.",
                {
                    "current_substage": "RESOLVING_GROUPS",
                    "partial_drafts_total": len(normalized_drafts),
                    "candidate_checks_total": len(deduped_candidates),
                    "exact_duplicates_removed": exact_removed,
                    "merge_groups_total": len(category_group_indexes),
                    "merge_groups_completed": completed,
                },
                88 + int((completed / max(1, len(category_group_indexes))) * 6),
            )
            self._raise_if_cancelled(cancel_check)

        final_resolved_checks, final_exact_removed = dedupe_resolved_checks(resolved_checks)
        self._progress(
            progress_cb,
            "FINALIZING_OUTPUT",
            "Finalizing the synthesized checklist output.",
            {
                "current_substage": "FINALIZING_OUTPUT",
                "partial_drafts_total": len(normalized_drafts),
                "candidate_checks_total": len(deduped_candidates),
                "exact_duplicates_removed": exact_removed,
                "merge_groups_total": len(category_group_indexes),
                "merge_groups_completed": len(category_group_indexes),
            },
            95,
        )
        self._raise_if_cancelled(cancel_check)

        selected_source_ids = sorted(
            _dedupe_preserve_order(
                [source_id for draft in normalized_drafts for source_id in draft.meta.selected_source_ids]
            )
        )
        open_questions = _dedupe_preserve_order(
            [question for draft in normalized_drafts for question in draft.meta.open_questions]
        )
        draft_confidence = fmean([draft.meta.confidence for draft in normalized_drafts])
        group_confidence = fmean([resolved.confidence for resolved in final_resolved_checks]) if final_resolved_checks else draft_confidence
        confidence = round(min(draft_confidence, group_confidence), 2)
        final_items = [normalize_check_item(resolved.item) for resolved in final_resolved_checks]

        payload = ChecklistDraftOutput(
            version=normalized_drafts[0].version,
            meta=ChecklistDraftMeta(
                selected_source_ids=selected_source_ids,
                confidence=confidence,
                open_questions=open_questions,
                generation_summary=(
                    f"Synthesized {len(candidates)} candidate checks into {len(deduped_candidates)} deduped checks "
                    f"across {len(category_group_indexes)} category groups, producing {len(final_items)} final checks using category_groups_v1."
                ),
            ),
            checks=final_items,
        )
        result = normalize_draft_output(payload)
        self._trace(
            trace_cb,
            "finalized",
            {
                "final_check_count": len(result.checks),
                "selected_source_ids": list(result.meta.selected_source_ids),
                "confidence": result.meta.confidence,
                "open_questions": list(result.meta.open_questions),
                "generation_summary": result.meta.generation_summary,
                "final_exact_duplicates_removed": final_exact_removed,
            },
        )
        return result

    def _resolve_group(
        self,
        group: list[int],
        candidates: list[SynthesisCandidate],
        *,
        user_instruction: str | None,
        trace_cb: SynthesisTraceCallback | None,
    ) -> list[ResolvedCheck]:
        if not self._settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for category checklist group resolution.")

        category = _category_value(candidates[group[0]].item.category)
        payload = [candidates[index].compact_payload for index in group]
        with genai.Client(api_key=self._settings.gemini_api_key) as client:
            response = client.models.generate_content(
                model=self._settings.gemini_checklist_model,
                contents="\n\n".join(
                    [
                        "Resolve these DPA checklist items from the same fixed category into the minimum correct set of final checks.",
                        f"Category: {category}",
                        f"User instruction: {(user_instruction or '').strip() or 'None provided'}",
                        "These items may overlap because they were drafted from different source subsets.",
                        "Merge checks that represent the same underlying legal obligation even if wording, pass criteria, or source citations differ.",
                        "Keep materially distinct obligations separate.",
                        json.dumps(payload, indent=2),
                    ]
                ),
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are resolving a small category-specific group of DPA checklist items.\n"
                        "Return the minimum number of final checklist checks needed to preserve all materially distinct obligations within this category.\n"
                        "Every input candidate_id must be represented exactly once across the output.\n"
                        "Prefer merging near-duplicate formulations of the same obligation instead of keeping redundant variants."
                    ),
                    response_mime_type="application/json",
                    response_schema=_group_resolution_schema(),
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=768),
                ),
            )
        if not response.text:
            raise RuntimeError("Gemini did not return category group resolution output.")

        parsed = json.loads(response.text)
        rows = parsed.get("resolved_checks")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Category group resolution returned no checks.")

        candidate_by_id = {candidates[index].candidate_id: candidates[index] for index in group}
        expected_ids = set(candidate_by_id)
        seen_ids: set[str] = set()
        resolved: list[ResolvedCheck] = []

        for row in rows:
            candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
            if not candidate_ids:
                raise RuntimeError("Resolved check row is missing candidate_ids.")
            if any(candidate_id not in candidate_by_id for candidate_id in candidate_ids):
                raise RuntimeError("Category group resolution returned unknown candidate ids.")
            overlap = seen_ids & set(candidate_ids)
            if overlap:
                raise RuntimeError(f"Category group resolution returned duplicate candidate ids: {sorted(overlap)}")
            seen_ids.update(candidate_ids)

            original_items = [candidate_by_id[candidate_id].item for candidate_id in candidate_ids]
            item = ChecklistDraftItem.model_validate(row["item"])
            merged_item = _merge_items_deterministically(item, original_items)
            confidence = float(row["confidence"])
            resolved.append(
                ResolvedCheck(
                    candidate_ids=tuple(candidate_ids),
                    confidence=round(min(1.0, max(0.0, confidence)), 2),
                    item=merged_item,
                )
            )

        if seen_ids != expected_ids:
            missing = sorted(expected_ids - seen_ids)
            raise RuntimeError(f"Category group resolution did not cover every candidate exactly once: {missing}")

        self._trace(
            trace_cb,
            "group_resolved",
            {
                "category": category,
                "candidate_ids": [candidates[index].candidate_id for index in group],
                "resolved_checks": [
                    {
                        "candidate_ids": list(check.candidate_ids),
                        "confidence": check.confidence,
                        "item": check.item.model_dump(mode="json"),
                    }
                    for check in resolved
                ],
            },
        )
        return resolved


VerifiedChecklistSynthesizer = CategoryGroupChecklistSynthesizer


def _checklist_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "check_id": {"type": "string"},
            "title": {"type": "string"},
            "category": {
                "type": "string",
                "enum": _CATEGORY_ENUM_VALUES,
                "description": "Choose exactly one approved DPA checklist category from the fixed taxonomy.",
            },
            "legal_basis": {"type": "array", "items": {"type": "string"}},
            "required": {"type": "boolean"},
            "severity": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "MANDATORY"],
            },
            "evidence_hint": {"type": "string"},
            "pass_criteria": {"type": "array", "items": {"type": "string"}},
            "fail_criteria": {"type": "array", "items": {"type": "string"}},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_type": {"type": "string", "enum": ["LAW", "GUIDELINE", "INTERNAL_POLICY"]},
                        "authority": {"type": "string"},
                        "source_ref": {"type": "string"},
                        "source_url": {"type": "string"},
                        "source_excerpt": {"type": "string"},
                        "interpretation_notes": {"type": "string"},
                    },
                    "required": ["source_type", "authority", "source_ref", "source_url", "source_excerpt"],
                },
            },
            "draft_rationale": {"type": "string"},
        },
        "required": [
            "check_id",
            "title",
            "category",
            "legal_basis",
            "required",
            "severity",
            "evidence_hint",
            "pass_criteria",
            "fail_criteria",
            "sources",
            "draft_rationale",
        ],
    }


def _group_resolution_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "resolved_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_ids": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                        "item": _checklist_item_schema(),
                    },
                    "required": ["candidate_ids", "confidence", "item"],
                },
            },
        },
        "required": ["resolved_checks"],
    }
