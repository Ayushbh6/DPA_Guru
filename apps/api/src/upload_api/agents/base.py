from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from db.models import AgentRun, AgentRunEvent, AgentRunMessage, AgentRunOutput, AgentRunToolCall

from .schemas import AgentLoopConfig, AgentRunScope


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _serialize_part(part: Any) -> dict[str, Any]:
    if getattr(part, "function_call", None):
        call = part.function_call
        return {
            "type": "function_call",
            "name": call.name,
            "args": dict(call.args) if getattr(call, "args", None) else {},
            "id": getattr(call, "id", None),
        }
    if getattr(part, "function_response", None):
        response = part.function_response
        return {
            "type": "function_response",
            "name": response.name,
            "response": getattr(response, "response", None),
            "id": getattr(response, "id", None),
        }
    if getattr(part, "text", None):
        return {"type": "text", "text": part.text}
    return {"type": "unknown", "value": str(part)}


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    candidates = list(getattr(response, "candidates", []) or [])
    if not candidates:
        return ""
    parts = list(getattr(candidates[0].content, "parts", []) or [])
    return "\n".join(part.text for part in parts if getattr(part, "text", None)).strip()


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    payload = usage.model_dump(mode="python") if hasattr(usage, "model_dump") else dict(vars(usage))
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.input_model.model_json_schema(),
        )


@dataclass(frozen=True)
class AgentRunResult:
    agent_run_id: str
    output: BaseModel


class AgentLoopRunner:
    def __init__(
        self,
        *,
        api_key: str,
        session_factory: sessionmaker[Session],
        scope: AgentRunScope,
        prompt_path: Path,
        loop_config: AgentLoopConfig,
        response_model: type[BaseModel],
        tools: list[AgentTool],
        task_input: dict[str, Any],
        user_message: str,
        cancel_check: Callable[[], bool] | None = None,
        run_started_cb: Callable[[str], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._session_factory = session_factory
        self._scope = scope
        self._prompt_path = prompt_path
        self._loop_config = loop_config
        self._response_model = response_model
        self._tools = tools
        self._task_input = task_input
        self._user_message = user_message
        self._cancel_check = cancel_check
        self._run_started_cb = run_started_cb
        self._message_seq = 0
        self._tool_seq = 0
        self._event_seq = 0

    def run(self) -> AgentRunResult:
        if self._cancel_check and self._cancel_check():
            raise RuntimeError("Agent run canceled before model execution.")

        system_prompt = self._prompt_path.read_text(encoding="utf-8")
        run_id = self._create_run(system_prompt)
        if self._run_started_cb is not None:
            self._run_started_cb(str(run_id))
        self._append_message(run_id, role="system", content=system_prompt)
        self._append_message(run_id, role="user", content=self._user_message, content_json=self._task_input)
        self._append_event(run_id, "agent_started", {"input": self._task_input})

        history: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=self._user_message)])
        ]
        tool_map = {tool.name: tool for tool in self._tools}
        tool_budget_used = 0
        last_response: Any | None = None

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=self._response_model,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tools=[types.Tool(function_declarations=[tool.declaration() for tool in self._tools])] if self._tools else None,
        )

        try:
            with genai.Client(api_key=self._api_key) as client:
                while True:
                    if self._cancel_check and self._cancel_check():
                        raise RuntimeError("Agent run canceled during execution.")

                    response = client.models.generate_content(
                        model=self._loop_config.model_name,
                        contents=history,
                        config=config,
                    )
                    last_response = response
                    assistant_content = response.candidates[0].content
                    assistant_parts = list(getattr(assistant_content, "parts", []) or [])
                    function_parts = [part for part in assistant_parts if getattr(part, "function_call", None)]

                    self._append_message(
                        run_id,
                        role="assistant",
                        content=_extract_text(response) or None,
                        content_json={"parts": [_serialize_part(part) for part in assistant_parts]},
                    )

                    if function_parts:
                        history.append(assistant_content)
                        tool_response_parts: list[types.Part] = []
                        for part in function_parts:
                            if tool_budget_used >= self._loop_config.max_tool_calls:
                                self._append_event(
                                    run_id,
                                    "tool_budget_exceeded",
                                    {"max_tool_calls": self._loop_config.max_tool_calls},
                                )
                                raise RuntimeError("Agent exceeded max tool-call budget.")
                            function_call = part.function_call
                            tool_budget_used += 1
                            tool_name = function_call.name
                            raw_args = dict(function_call.args) if getattr(function_call, "args", None) else {}
                            tool_row_id = self._start_tool_call(run_id, tool_name, raw_args)
                            tool = tool_map.get(tool_name)
                            if tool is None:
                                tool_output = {"error": f"Unknown tool: {tool_name}"}
                                self._finish_tool_call(run_id, tool_row_id, status="failed", output_json=tool_output, error_message=tool_output["error"])
                            else:
                                try:
                                    parsed_args = tool.input_model.model_validate(raw_args)
                                    result = tool.handler(parsed_args)
                                    tool_output = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
                                    self._finish_tool_call(run_id, tool_row_id, status="completed", output_json=tool_output)
                                except Exception as exc:
                                    tool_output = {"error": str(exc)}
                                    self._finish_tool_call(run_id, tool_row_id, status="failed", output_json=tool_output, error_message=str(exc))
                            tool_response_parts.append(
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name=tool_name,
                                        response={"result": tool_output},
                                        id=getattr(function_call, "id", None),
                                    )
                                )
                            )

                        history.append(types.Content(role="tool", parts=tool_response_parts))
                        self._append_message(
                            run_id,
                            role="tool",
                            content_json={"parts": [_serialize_part(part) for part in tool_response_parts]},
                        )
                        continue

                    response_text = _extract_text(response)
                    if not response_text:
                        raise RuntimeError("Model returned no final structured output.")
                    parsed_output = self._response_model.model_validate_json(response_text)
                    self._save_output(run_id, parsed_output)
                    self._complete_run(run_id, status="completed", response=response, output=parsed_output)
                    self._append_event(run_id, "agent_completed", {"tool_calls": tool_budget_used})
                    return AgentRunResult(agent_run_id=str(run_id), output=parsed_output)
        except ValidationError as exc:
            self._append_event(run_id, "output_validation_failed", {"error": str(exc)})
            self._fail_run(run_id, error_code="ValidationError", error_message=str(exc), response=last_response)
            raise
        except Exception as exc:
            self._append_event(run_id, "agent_failed", {"error": str(exc)})
            self._fail_run(run_id, error_code=exc.__class__.__name__, error_message=str(exc), response=last_response)
            raise

    def _create_run(self, system_prompt: str) -> uuid.UUID:
        with self._session_factory() as session:
            row = AgentRun(
                tenant_id=self._scope.tenant_id,
                project_id=self._scope.project_id,
                analysis_run_id=self._scope.analysis_run_id,
                approval_pack_id=self._scope.approval_pack_id,
                parent_agent_run_id=self._scope.parent_agent_run_id,
                agent_name=self._loop_config.agent_name,
                agent_role=self._loop_config.agent_role,
                agent_version=self._loop_config.agent_version,
                status="running",
                model_provider="google",
                model_name=self._loop_config.model_name,
                prompt_version=self._loop_config.prompt_version,
                system_prompt_hash=_sha256_text(system_prompt),
                input_hash=_sha256_text(_json_dumps(self._task_input)),
                started_at=_utcnow(),
            )
            session.add(row)
            session.commit()
            return row.id

    def _append_message(
        self,
        run_id: uuid.UUID,
        *,
        role: str,
        content: str | None = None,
        content_json: dict[str, Any] | None = None,
    ) -> None:
        self._message_seq += 1
        with self._session_factory() as session:
            session.add(
                AgentRunMessage(
                    tenant_id=self._scope.tenant_id,
                    agent_run_id=run_id,
                    sequence_no=self._message_seq,
                    role=role,
                    content=content,
                    content_json=content_json,
                    content_hash=_sha256_text(content or _json_dumps(content_json or {})),
                )
            )
            session.commit()

    def _append_event(self, run_id: uuid.UUID, event_type: str, payload_json: dict[str, Any] | None = None) -> None:
        self._event_seq += 1
        with self._session_factory() as session:
            session.add(
                AgentRunEvent(
                    tenant_id=self._scope.tenant_id,
                    agent_run_id=run_id,
                    sequence_no=self._event_seq,
                    event_type=event_type,
                    payload_json=payload_json,
                )
            )
            session.commit()

    def _start_tool_call(self, run_id: uuid.UUID, tool_name: str, input_json: dict[str, Any]) -> uuid.UUID:
        self._tool_seq += 1
        with self._session_factory() as session:
            row = AgentRunToolCall(
                tenant_id=self._scope.tenant_id,
                agent_run_id=run_id,
                sequence_no=self._tool_seq,
                tool_name=tool_name,
                input_json=input_json,
                status="running",
                started_at=_utcnow(),
            )
            session.add(row)
            session.commit()
            return row.id

    def _finish_tool_call(
        self,
        run_id: uuid.UUID,
        tool_call_id: uuid.UUID,
        *,
        status: str,
        output_json: Any,
        error_message: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            row = session.get(AgentRunToolCall, tool_call_id)
            if row is None or row.agent_run_id != run_id:
                return
            row.status = status
            row.output_json = output_json if isinstance(output_json, dict) else {"value": output_json}
            row.error_message = error_message
            row.error_code = "tool_error" if error_message else None
            row.completed_at = _utcnow()
            session.commit()

    def _save_output(self, run_id: uuid.UUID, output: BaseModel) -> None:
        with self._session_factory() as session:
            session.add(
                AgentRunOutput(
                    tenant_id=self._scope.tenant_id,
                    agent_run_id=run_id,
                    output_type=self._loop_config.output_type,
                    schema_version=self._loop_config.output_schema_version,
                    output_json=output.model_dump(mode="json"),
                    validation_status="valid",
                )
            )
            session.commit()

    def _complete_run(self, run_id: uuid.UUID, *, status: str, response: Any, output: BaseModel) -> None:
        usage = _extract_usage(response)
        with self._session_factory() as session:
            row = session.get(AgentRun, run_id)
            if row is None:
                return
            row.status = status
            row.completed_at = _utcnow()
            if row.started_at is not None and row.completed_at is not None:
                row.latency_ms = int((row.completed_at - row.started_at).total_seconds() * 1000)
            row.output_hash = _sha256_text(_json_dumps(output.model_dump(mode="json")))
            row.input_tokens = usage.get("prompt_token_count") or usage.get("input_token_count")
            row.output_tokens = usage.get("candidates_token_count") or usage.get("output_token_count")
            row.total_tokens = usage.get("total_token_count")
            session.commit()

    def _fail_run(self, run_id: uuid.UUID, *, error_code: str, error_message: str, response: Any | None) -> None:
        usage = _extract_usage(response) if response is not None else {}
        with self._session_factory() as session:
            row = session.get(AgentRun, run_id)
            if row is None:
                return
            row.status = "failed"
            row.error_code = error_code
            row.error_message = error_message
            row.completed_at = _utcnow()
            if row.started_at is not None and row.completed_at is not None:
                row.latency_ms = int((row.completed_at - row.started_at).total_seconds() * 1000)
            row.input_tokens = usage.get("prompt_token_count") or usage.get("input_token_count")
            row.output_tokens = usage.get("candidates_token_count") or usage.get("output_token_count")
            row.total_tokens = usage.get("total_token_count")
            session.commit()
