from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

from .config import load_settings
from .db import build_session_factory
from .events import JobEventBus
from .jobs import ClaimedJob, UploadPipelineService
from .logging_utils import configure_logging, log_event
from .storage import ArtifactStore


configure_logging()

settings = load_settings()
session_factory = build_session_factory(settings.database_url)
storage = ArtifactStore.from_settings(settings)
service = UploadPipelineService(
    settings=settings,
    session_factory=session_factory,
    storage=storage,
    event_bus=JobEventBus(),
)

JOB_TYPE_ORDER = ("parse", "checklist", "analysis")


async def _execute_job(claimed: ClaimedJob) -> None:
    started = time.perf_counter()
    try:
        await service.execute_claimed_job(claimed, worker_id=settings.worker_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            logging.WARNING,
            severity="warning",
            event="worker_job_failed",
            worker_id=settings.worker_id,
            job_type=claimed.job_type,
            job_id=str(claimed.job_id),
            project_id=str(claimed.project_id),
            attempt_count=claimed.attempt_count,
            duration_ms=duration_ms,
            error_code=exc.__class__.__name__,
            error_message=str(exc),
        )
        return

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log_event(
        logging.INFO,
        severity="info",
        event="worker_job_completed",
        worker_id=settings.worker_id,
        job_type=claimed.job_type,
        job_id=str(claimed.job_id),
        project_id=str(claimed.project_id),
        attempt_count=claimed.attempt_count,
        duration_ms=duration_ms,
    )


async def run_worker() -> None:
    active: set[asyncio.Task] = set()
    stop_event = asyncio.Event()
    next_recovery = 0.0
    round_robin_index = 0

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    log_event(
        logging.INFO,
        severity="info",
        event="worker_started",
        worker_id=settings.worker_id,
        concurrency=settings.worker_concurrency,
    )

    while not stop_event.is_set():
        now_monotonic = time.monotonic()
        if now_monotonic >= next_recovery:
            reclaimed = await asyncio.to_thread(service.recover_stale_leases)
            if reclaimed:
                log_event(
                    logging.INFO,
                    severity="info",
                    event="worker_recovered_stale_jobs",
                    worker_id=settings.worker_id,
                    reclaimed=reclaimed,
                )
            next_recovery = now_monotonic + settings.worker_heartbeat_interval_seconds

        while len(active) < settings.worker_concurrency and not stop_event.is_set():
            ordered_job_types = JOB_TYPE_ORDER[round_robin_index:] + JOB_TYPE_ORDER[:round_robin_index]
            claimed = await asyncio.to_thread(
                service.claim_next_job,
                worker_id=settings.worker_id,
                job_types=ordered_job_types,
            )
            round_robin_index = (round_robin_index + 1) % len(JOB_TYPE_ORDER)
            if claimed is None:
                break
            log_event(
                logging.INFO,
                severity="info",
                event="worker_job_claimed",
                worker_id=settings.worker_id,
                job_type=claimed.job_type,
                job_id=str(claimed.job_id),
                project_id=str(claimed.project_id),
                attempt_count=claimed.attempt_count,
            )
            task = asyncio.create_task(_execute_job(claimed))
            active.add(task)
            task.add_done_callback(active.discard)

        if active:
            done, _ = await asyncio.wait(
                active,
                timeout=settings.worker_poll_interval_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                with contextlib.suppress(asyncio.CancelledError):
                    task.result()
        else:
            await asyncio.sleep(settings.worker_poll_interval_seconds)

    for task in list(active):
        task.cancel()
    if active:
        await asyncio.gather(*active, return_exceptions=True)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
