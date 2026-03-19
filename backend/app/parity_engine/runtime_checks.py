"""Runtime health checks for the standalone parity engine service."""

from __future__ import annotations

from dataclasses import dataclass
import os
import time

import httpx


@dataclass(slots=True)
class EngineStatus:
    base_url: str
    engine_status: str
    ready: bool
    detail: str | None = None


class EngineUnavailableError(RuntimeError):
    def __init__(self, status: EngineStatus):
        self.status = status
        detail = f": {status.detail}" if status.detail else ""
        super().__init__(f"Parity engine is unavailable ({status.engine_status}){detail}")


def probe_engine(base_url: str | None = None, timeout_seconds: int | None = None) -> EngineStatus:
    resolved_base_url = (base_url or os.environ.get("ENGINE_BASE_URL", "http://127.0.0.1:8123")).rstrip("/")
    resolved_timeout = timeout_seconds or int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30"))

    try:
        with httpx.Client(base_url=resolved_base_url, timeout=resolved_timeout) as client:
            health_response = client.get("/health")
            health_response.raise_for_status()
            ready_response = client.get("/ready")
    except httpx.HTTPError as exc:
        return EngineStatus(
            base_url=resolved_base_url,
            engine_status="unavailable",
            ready=False,
            detail=str(exc),
        )

    if ready_response.status_code != 200:
        payload = ready_response.json()
        return EngineStatus(
            base_url=resolved_base_url,
            engine_status=str(payload.get("status", "unready")),
            ready=False,
            detail=payload.get("error"),
        )

    payload = ready_response.json()
    return EngineStatus(
        base_url=resolved_base_url,
        engine_status=str(payload.get("status", "ready")),
        ready=True,
        detail=None,
    )


def ensure_engine_ready(
    base_url: str | None = None,
    timeout_seconds: int | None = None,
    poll_interval: float = 0.5,
) -> EngineStatus:
    resolved_timeout = timeout_seconds or int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30"))
    deadline = time.monotonic() + max(resolved_timeout, poll_interval)
    last_status: EngineStatus | None = None

    while time.monotonic() < deadline:
        last_status = probe_engine(base_url=base_url, timeout_seconds=resolved_timeout)
        if last_status.ready:
            return last_status
        time.sleep(poll_interval)

    last_status = last_status or probe_engine(base_url=base_url, timeout_seconds=resolved_timeout)
    raise EngineUnavailableError(last_status)
