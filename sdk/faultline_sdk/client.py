from __future__ import annotations

from dataclasses import asdict
from typing import Any

import requests

from .types import (
    ClaimRequest,
    CompleteRequest,
    FailRequest,
    SubmitRequest,
    SubmitResponse,
    WorkerRegistration,
    WorkerRegistrationResponse,
)


class FaultlineClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def submit(self, request: SubmitRequest) -> SubmitResponse:
        resp = requests.post(
            f"{self.base_url}/v1/jobs",
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return SubmitResponse(
            job_id=str(data["job_id"]),
            state=data.get("state", "queued"),
            accepted=bool(data.get("accepted", True)),
        )

    def register_worker(self, request: WorkerRegistration) -> WorkerRegistrationResponse:
        resp = requests.post(
            f"{self.base_url}/v1/workers/register",
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return WorkerRegistrationResponse(
            worker_id=str(data["worker_id"]),
            accepted=bool(data.get("accepted", True)),
        )

    def claim(self, request: ClaimRequest) -> dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/v1/jobs/claim",
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def complete(self, request: CompleteRequest) -> dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/v1/jobs/complete",
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def fail(self, request: FailRequest) -> dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/v1/jobs/fail",
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def reconcile(self) -> dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/v1/admin/reconcile",
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()
