from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kb_pipeline.config import PipelineConfig
from kb_pipeline.models import KbStructureOutput, LlmStageResult, TaskPayload
from kb_pipeline.prompts import system_prompt, user_prompt

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
USER_AGENT = "AI-DPA-KB-Pipeline/1.0 (+local-dev)"


class OpenRouterClient:
    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    async def extract(self, task: TaskPayload) -> LlmStageResult:
        return await asyncio.to_thread(self._extract_sync, task)

    def _extract_sync(self, task: TaskPayload) -> LlmStageResult:
        payload = {
            "model": self._config.openrouter_model,
            "temperature": 0,
            "reasoning": {"enabled": False},
            "messages": [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": user_prompt(task)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "KbStructureOutput",
                    "strict": True,
                    "schema": KbStructureOutput.model_json_schema(),
                },
            },
        }

        attempts_used = 0
        last_exc: Exception | None = None
        for attempt in range(self._config.request_retries + 1):
            attempts_used = attempt + 1
            try:
                response = self._json_request(payload)
                raw_content = response["choices"][0]["message"]["content"]
                if isinstance(raw_content, list):
                    raw_content = "".join(
                        part.get("text", "") for part in raw_content if isinstance(part, dict)
                    )
                if not isinstance(raw_content, str):
                    raise ValueError(f"Unexpected OpenRouter response content type: {type(raw_content)}")

                parsed = None
                validation_attempts = max(1, self._config.llm_validation_retries + 1)
                validation_errors: list[str] = []
                for _ in range(validation_attempts):
                    try:
                        parsed = json.loads(raw_content)
                        model_obj = KbStructureOutput.model_validate(parsed)
                        out = model_obj.model_dump()
                        out["source_title"] = task.source_title
                        out["source_url"] = task.source_url
                        return LlmStageResult(
                            task_id=task.task_id,
                            structured_json=out,
                            structured_text=json.dumps(out, ensure_ascii=False),
                            attempts_used=attempts_used,
                        )
                    except Exception as exc:  # schema/json validation failure
                        validation_errors.append(str(exc))
                        break
                raise ValueError("LLM structured output validation failed: " + " | ".join(validation_errors))
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
            except Exception as exc:
                last_exc = exc
                # Validation and non-network errors are not retried by default.
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected LLM request loop exit")

    def _json_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.openrouter_api_key}",
                "User-Agent": USER_AGENT,
            },
        )
        with urlopen(req, timeout=self._config.request_timeout_seconds) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
