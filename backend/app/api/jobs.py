"""In-memory job store for long-running trip planning requests."""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict


class TripJobStore:
    """Runs planning jobs in background threads and exposes pollable state."""

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, worker: Callable[[Callable[[dict], None]], dict]) -> str:
        job_id = uuid.uuid4().hex
        now = _now()
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "steps": [],
                "content": "",
                "step_count": 0,
                "progress": 0,
                "stage": "queued",
                "current_city": "",
                "warning": None,
                "error": None,
                "cancel_requested": False,
            }

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, worker),
            daemon=True,
        )
        thread.start()
        return job_id

    def get(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return _copy_job(job)

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job["status"] in {"completed", "failed", "cancelled"}:
                return _copy_job(job)
            job["cancel_requested"] = True
            job["status"] = "cancelling"
            job["updated_at"] = _now()
            return _copy_job(job)

    def _run_job(self, job_id: str, worker: Callable[[Callable[[dict], None]], dict]) -> None:
        self._update(job_id, status="running")

        def on_step(step: dict) -> None:
            with self._lock:
                job = self._jobs[job_id]
                if job.get("cancel_requested"):
                    raise JobCancelled("Trip planning job was cancelled")
                job["steps"].append(step)
                job["step_count"] = len(job["steps"])
                job["progress"] = min(96, 8 + len(job["steps"]) * 8)
                job["stage"] = _stage_for_step(step)
                job["current_city"] = step.get("city") or (step.get("metadata") or {}).get("city") or ""
                job["updated_at"] = _now()

        try:
            result = worker(on_step)
            self._update(
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                content=result.get("content", ""),
                step_count=result.get("step_count", 0),
                warning=result.get("warning"),
                steps=result.get("raw_steps") or self.get(job_id)["steps"],
                structured_plan=result.get("structured_plan"),
                knowledge_graph=result.get("knowledge_graph"),
            )
        except Exception as error:
            if isinstance(error, JobCancelled):
                self._update(job_id, status="cancelled", progress=0, stage="cancelled", error=str(error))
            else:
                self._update(job_id, status="failed", progress=0, stage="failed", error=str(error))

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = _now()


def _copy_job(job: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(job)
    copied["steps"] = list(job.get("steps") or [])
    return copied


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


trip_job_store = TripJobStore()


class JobCancelled(RuntimeError):
    """Raised when a background job is cancelled by the user."""


def _stage_for_step(step: dict) -> str:
    labels = {
        "search_poi": "正在检索真实地点",
        "get_weather_forecast": "正在读取天气趋势",
        "estimate_route": "正在估算路线耗时",
        "estimate_trip_budget": "正在核算预算",
        "check_budget_limit": "正在检查预算约束",
        "check_itinerary_constraints": "正在检查路线约束",
        "generate_packing_and_outfits": "正在生成行李与穿搭",
        "search_travel_notes": "正在检索公开旅行攻略",
        "fallback_decision": "正在整理最终方案",
    }
    city = step.get("city") or (step.get("metadata") or {}).get("city")
    label = labels.get(step.get("tool_name"), "正在生成旅行方案")
    return f"{city}：{label}" if city else label
