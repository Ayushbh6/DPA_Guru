from __future__ import annotations

import asyncio
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kb_pipeline.config import PipelineConfig
from kb_pipeline.models import EmbedStageResult, TaskPayload

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"
USER_AGENT = "AI-DPA-KB-Pipeline/1.0 (+local-dev)"


def combined_text_for_embedding(task: TaskPayload) -> str:
    if task.structured_json is None:
        raise ValueError("structured_json is required to build combined text")
    return (
        "## RAW_TEXT_CHUNK\n"
        f"{task.raw_text.strip()}\n\n"
        "## STRUCTURED_OUTPUT\n"
        f"{json.dumps(task.structured_json, ensure_ascii=False, indent=2)}\n"
    )


class OpenAIEmbeddingClient:
    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    async def embed(self, task: TaskPayload) -> EmbedStageResult:
        return await asyncio.to_thread(self._embed_sync, task)

    def _embed_sync(self, task: TaskPayload) -> EmbedStageResult:
        combined_text = combined_text_for_embedding(task)
        payload = {"model": self._config.openai_embedding_model, "input": combined_text}

        attempts_used = 0
        last_exc: Exception | None = None
        for attempt in range(self._config.request_retries + 1):
            attempts_used = attempt + 1
            try:
                res = self._json_request(payload)
                embedding = res["data"][0]["embedding"]
                if not isinstance(embedding, list) or not embedding:
                    raise ValueError("Invalid embedding response payload")
                return EmbedStageResult(
                    task_id=task.task_id,
                    embedding=[float(v) for v in embedding],
                    embedding_dim=len(embedding),
                    attempts_used=attempts_used,
                )
            except HTTPError as exc:
                last_exc = exc
                status = getattr(exc, "code", None)
                retryable = status == 429 or (status is not None and 500 <= status < 600)
                if not retryable or attempt >= self._config.request_retries:
                    raise
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if (retry_after and retry_after.isdigit()) else min(10.0, 0.75 * (2**attempt))
                time.sleep(delay)
            except URLError as exc:
                last_exc = exc
                if attempt >= self._config.request_retries:
                    raise
                time.sleep(min(10.0, 0.75 * (2**attempt)))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected embedding request loop exit")

    def _json_request(self, payload: dict) -> dict:
        req = Request(
            OPENAI_EMBED_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.openai_api_key}",
                "User-Agent": USER_AGENT,
            },
        )
        with urlopen(req, timeout=self._config.request_timeout_seconds) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
