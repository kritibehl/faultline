from __future__ import annotations

from services.worker.network_profiles import (
    DNSFailure,
    HandshakeFailure,
    NetworkFaultInjector,
    PartialPartition,
    QueryTimeout,
)


class NetworkFaultProxy:
    def __init__(self, profile: str | None = None, seed: int | None = None):
        self.injector = NetworkFaultInjector(profile=profile, seed=seed)

    def on_connect(self):
        return self.injector.before_operation("connect")

    def on_claim(self):
        return self.injector.before_operation("claim")

    def on_heartbeat(self):
        return self.injector.before_operation("heartbeat")

    def on_commit(self):
        return self.injector.before_operation("commit")


__all__ = [
    "NetworkFaultProxy",
    "DNSFailure",
    "HandshakeFailure",
    "PartialPartition",
    "QueryTimeout",
]
