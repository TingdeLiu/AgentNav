# agentnav/bridge_core/task_manager.py
"""
Streaming task lifecycle manager.

Usage:
    task_id = task_mgr.start(some_coroutine(), instruction="go to chair")
    status  = task_mgr.get_status(task_id)
    task_mgr.cancel(task_id)
    task_mgr.update(task_id, phase="moving", distance_to_goal_m=1.2)
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class TaskInfo:
    task_id: str
    instruction: str
    status: str = "running"          # running | completed | failed | cancelled
    phase: str = "planning"          # planning | moving | arrived | failed
    distance_to_goal_m: float = 0.0
    elapsed_s: float = 0.0
    s2_interpretation: str = ""
    retries: int = 0
    error: str = ""
    start_time: float = field(default_factory=time.time)
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)


class TaskManager:
    def __init__(self, state):
        self._state = state
        self._tasks: Dict[str, TaskInfo] = {}

    def start(self, coro, instruction: str = "") -> str:
        """
        Schedule `coro` as a background asyncio task.
        Returns a task_id that can be used with get_status / cancel / update.
        """
        task_id = uuid.uuid4().hex[:8]
        info = TaskInfo(task_id=task_id, instruction=instruction)
        self._tasks[task_id] = info

        async def _run() -> None:
            try:
                await coro
                info.status = "completed"
                info.phase = "arrived"
            except asyncio.CancelledError:
                info.status = "cancelled"
                info.phase = "failed"
                raise
            except Exception as exc:
                info.status = "failed"
                info.phase = "failed"
                info.error = str(exc)

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
