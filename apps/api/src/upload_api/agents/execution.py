from __future__ import annotations

import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from upload_api.config import Settings

from .schemas import CriteriaResearchPayload, CriteriaResearchResult, StartCriteriaResearchInput


@dataclass
class _ResearchTask:
    research_id: str
    parent_agent_run_id: str
    query: str
    future: Future[tuple[str, CriteriaResearchPayload]]


class CriteriaResearchExecutor:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.agent_child_concurrency),
            thread_name_prefix="criteria-research",
        )
        self._tasks: dict[str, _ResearchTask] = {}
        self._canceled_parent_ids: set[str] = set()

    def start(
        self,
        *,
        parent_agent_run_id: str,
        payload: StartCriteriaResearchInput,
        launch_fn: Callable[[str, StartCriteriaResearchInput], tuple[str, CriteriaResearchPayload]],
    ) -> CriteriaResearchResult:
        research_id = str(uuid.uuid4())
        future = self._executor.submit(launch_fn, research_id, payload)
        task = _ResearchTask(
            research_id=research_id,
            parent_agent_run_id=parent_agent_run_id,
            query=payload.query,
            future=future,
        )
        with self._lock:
            self._tasks[research_id] = task
        return CriteriaResearchResult(
            research_id=research_id,
            query=payload.query,
            status="queued",
        )

    def collect(
        self,
        *,
        parent_agent_run_id: str,
        research_ids: list[str] | None = None,
        wait_seconds: int = 0,
    ) -> list[CriteriaResearchResult]:
        tasks = self._tasks_for_parent(parent_agent_run_id, research_ids)
        if wait_seconds > 0 and tasks:
            wait([task.future for task in tasks], timeout=max(0, wait_seconds))

        results: list[CriteriaResearchResult] = []
        for task in tasks:
            if task.future.cancelled():
                results.append(
                    CriteriaResearchResult(
                        research_id=task.research_id,
                        query=task.query,
                        status="canceled",
                    )
                )
                continue
            if not task.future.done():
                results.append(
                    CriteriaResearchResult(
                        research_id=task.research_id,
                        query=task.query,
                        status="running" if task.future.running() else "queued",
                    )
                )
                continue
            try:
                agent_run_id, payload = task.future.result()
                results.append(
                    CriteriaResearchResult(
                        research_id=task.research_id,
                        query=task.query,
                        status="completed",
                        agent_run_id=agent_run_id,
                        payload=payload,
                    )
                )
            except Exception as exc:
                results.append(
                    CriteriaResearchResult(
                        research_id=task.research_id,
                        query=task.query,
                        status="failed",
                        error_message=str(exc),
                    )
                )
        return results

    def cancel_parent(self, *, parent_agent_run_id: str) -> None:
        for task in self._tasks_for_parent(parent_agent_run_id, None):
            self._request_task_cancel(task)

    def finish_parent(self, *, parent_agent_run_id: str) -> None:
        for task in self._tasks_for_parent(parent_agent_run_id, None):
            if task.future.done() or task.future.cancelled():
                self._remove_task(task.research_id)
            else:
                self._request_task_cancel(task)

    def is_parent_cancelled(self, *, parent_agent_run_id: str) -> bool:
        with self._lock:
            return parent_agent_run_id in self._canceled_parent_ids

    def _request_task_cancel(self, task: _ResearchTask) -> None:
        with self._lock:
            self._canceled_parent_ids.add(task.parent_agent_run_id)
        if task.future.cancel():
            self._remove_task(task.research_id)
            return
        task.future.add_done_callback(lambda _future, research_id=task.research_id: self._remove_task(research_id))

    def _remove_task(self, research_id: str) -> None:
        with self._lock:
            task = self._tasks.pop(research_id, None)
            if task is None:
                return
            has_parent_tasks = any(
                item.parent_agent_run_id == task.parent_agent_run_id
                for item in self._tasks.values()
            )
            if not has_parent_tasks:
                self._canceled_parent_ids.discard(task.parent_agent_run_id)

    def _tasks_for_parent(self, parent_agent_run_id: str, research_ids: list[str] | None) -> list[_ResearchTask]:
        requested = set(research_ids or [])
        with self._lock:
            tasks = [
                task
                for task in self._tasks.values()
                if task.parent_agent_run_id == parent_agent_run_id
                and (not requested or task.research_id in requested)
            ]
        tasks.sort(key=lambda item: item.research_id)
        return tasks


def build_criteria_research_executor(settings: Settings) -> CriteriaResearchExecutor:
    if settings.agent_execution_backend == "celery_redis":
        raise RuntimeError("AGENT_EXECUTION_BACKEND=celery_redis is not implemented yet.")
    return CriteriaResearchExecutor(settings=settings)
