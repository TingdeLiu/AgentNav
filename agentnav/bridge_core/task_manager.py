# agentnav/bridge_core/task_manager.py
"""
Streaming task lifecycle manager.

Usage (factory pattern — supports retries):
    task_id = task_mgr.start(lambda: some_coroutine(), instruction="go to chair")
    status  = task_mgr.get_status(task_id)
    task_mgr.cancel(task_id)
    task_mgr.update(task_id, phase="moving", distance_to_goal_m=1.2)

Bare coroutine (one attempt only, no retries):
    task_id = task_mgr.start(some_coroutine(), instruction="go to chair")

Retry behaviour:
    - Only Exception retries; CancelledError is never retried (preserves robot_stop correctness).
    - status="retrying" is visible via get_status() during backoff sleep.
    - Jitter adds random delay variation to avoid thundering-herd on external services.
"""
import asyncio
import inspect
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    task_id: str
    instruction: str
    status: str = "running"          # running | retrying | completed | failed | cancelled
    phase: str = "planning"          # planning | moving | arrived | failed
    distance_to_goal_m: float = 0.0
    elapsed_s: float = 0.0
    s2_interpretation: str = ""
    retries: int = 0
    error: str = ""
    last_retry_reason: str = ""
    start_time: float = field(default_factory=time.time)
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)


class TaskManager:
    def __init__(
        self,
        state,
        max_retries: int = 3,
        retry_delay_s: float = 2.0,
        backoff: str = "fixed",      # "fixed" | "exponential"
        jitter_s: float = 0.0,
    ):
        self._state = state
        self._tasks: Dict[str, TaskInfo] = {}
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._backoff = backoff
        self._jitter_s = jitter_s

    def start(self, coro_or_factory, instruction: str = "", max_retries: int | None = None) -> str:
        """
        Schedule a coroutine (or factory) as a background asyncio task.
        Returns a task_id usable with get_status / cancel / update.

        For retry support, pass a callable (factory) that returns a fresh
        coroutine on each call:
            task_mgr.start(lambda: navigate(pose), instruction="go to chair")

        Passing a bare coroutine works but limits to one attempt (no retries).
        """
        task_id = uuid.uuid4().hex[:8]
        info = TaskInfo(task_id=task_id, instruction=instruction)
        self._tasks[task_id] = info

        effective_max = max_retries if max_retries is not None else self._max_retries

        # Bare coroutines are exhausted after first await; warn and disable retries.
        if inspect.iscoroutine(coro_or_factory) and effective_max > 0:
            logger.warning(
                "Task %s: retry requested (max_retries=%d) but a bare coroutine was passed. "
                "Only one attempt will run. Pass a callable factory for retry support.",
                task_id, effective_max,
            )
            effective_max = 0

        async def _run() -> None:
            attempt = 0
            while True:
                coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
                try:
                    await coro
                    info.status = "completed"
                    info.phase = "arrived"
                    return
                except asyncio.CancelledError:
                    info.status = "cancelled"
                    info.phase = "failed"
                    raise
                except Exception as exc:
                    attempt += 1
                    info.retries = attempt
                    info.last_retry_reason = str(exc)
                    if attempt > effective_max:
                        info.status = "failed"
                        info.phase = "failed"
                        info.error = str(exc)
                        return
                    # Compute backoff delay
                    if self._backoff == "exponential":
                        delay = self._retry_delay_s * (2 ** (attempt - 1))
                    else:
                        delay = self._retry_delay_s
                    if self._jitter_s > 0:
                        delay += random.uniform(0, self._jitter_s)
                    info.status = "retrying"
                    info.phase = "planning"
                    logger.info(
                        "Task %s attempt %d/%d failed (%s); retrying in %.1fs",
                        task_id, attempt, effective_max, exc, delay,
                    )
                    await asyncio.sleep(delay)

        loop = asyncio.get_event_loop()
        asyncio_task = loop.create_task(_run())
        info._asyncio_task = asyncio_task
        return task_id

    def get_status(self, task_id: str) -> dict:
        """Return rich status dict for the given task_id."""
        info = self._tasks.get(task_id)
        if info is None:
            return {"status": "not_found", "task_id": task_id}
        elapsed = time.time() - info.start_time
        result = {
            "status": info.status,
            "phase": info.phase,
            "distance_to_goal_m": info.distance_to_goal_m,
            "elapsed_s": round(elapsed, 1),
            "s2_interpretation": info.s2_interpretation,
            "retries": info.retries,
        }
        if info.error:
            result["error"] = info.error
        if info.last_retry_reason:
            result["last_retry_reason"] = info.last_retry_reason
        return result

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task. Returns True if cancellation was requested."""
        info = self._tasks.get(task_id)
        if info is None or info._asyncio_task is None:
            return False
        cancelled = info._asyncio_task.cancel()
        if cancelled:
            info.status = "cancelled"
        return cancelled

    def update(self, task_id: str, **kwargs) -> None:
        """
        Allow drivers / S1 client to push status updates into a running task.
        Only known TaskInfo fields are accepted.
        """
        info = self._tasks.get(task_id)
        if info is None:
            return
        for key, value in kwargs.items():
            if hasattr(info, key) and not key.startswith("_"):
                setattr(info, key, value)
