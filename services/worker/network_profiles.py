from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass


@dataclass
class FaultConfig:
    drop_rate: float = 0.0
    latency_ms: tuple[int, int] | int = 0
    timeout_rate: float = 0.0
    seed: int = 0
    enabled: bool = True


class NetworkImpairment(Exception):
    pass


class DNSFailure(NetworkImpairment):
    pass


class HandshakeFailure(NetworkImpairment):
    pass


class PartialPartition(NetworkImpairment):
    pass


class QueryTimeout(NetworkImpairment):
    pass


@dataclass
class NetworkEvent:
    profile: str
    operation: str
    duration_seconds: float
    impaired: bool
    detail: str


class NetworkFaultInjector:
    def __init__(self, profile: str | None = None, seed: int | None = None):
        self.profile = (profile or os.getenv("FAULTLINE_NETWORK_PROFILE") or "healthy").strip()
        self.rng = random.Random(seed if seed is not None else int(os.getenv("FAULTLINE_NETWORK_SEED", "7")))

    def before_operation(self, operation: str) -> NetworkEvent:
        start = time.perf_counter()
        impaired = False
        detail = "ok"

        if self.profile == "healthy":
            pass

        elif self.profile == "packet_loss":
            if self.rng.random() < 0.15:
                impaired = True
                detail = "simulated packet loss"
                raise QueryTimeout(detail)

        elif self.profile == "asymmetric_latency":
            if operation in {"connect", "claim", "commit"}:
                delay = 0.15 if operation == "connect" else 0.35
                time.sleep(delay)
                impaired = True
                detail = f"asymmetric latency {delay:.2f}s"

        elif self.profile == "bursty_link_degradation":
            if self.rng.random() < 0.35:
                delay = self.rng.uniform(0.2, 0.8)
                time.sleep(delay)
                impaired = True
                detail = f"bursty degradation {delay:.2f}s"
                if self.rng.random() < 0.25:
                    raise QueryTimeout("timeout during burst degradation")

        elif self.profile == "dns_failure":
            if operation == "connect":
                impaired = True
                detail = "dns resolution failed"
                raise DNSFailure(detail)

        elif self.profile == "partial_partition":
            if operation in {"claim", "commit", "heartbeat"} and self.rng.random() < 0.4:
                impaired = True
                detail = "partial partition between worker and db"
                raise PartialPartition(detail)

        elif self.profile == "intermittent_handshake":
            if operation == "connect" and self.rng.random() < 0.5:
                impaired = True
                detail = "intermittent handshake/connectivity failure"
                raise HandshakeFailure(detail)

        end = time.perf_counter()
        return NetworkEvent(
            profile=self.profile,
            operation=operation,
            duration_seconds=end - start,
            impaired=impaired,
            detail=detail,
        )


__all__ = [
    "FaultConfig",
    "NetworkImpairment",
    "DNSFailure",
    "HandshakeFailure",
    "PartialPartition",
    "QueryTimeout",
    "NetworkEvent",
    "NetworkFaultInjector",
]
