import time
from prometheus_client import Counter, start_http_server

heartbeat = Counter(
    "faultline_worker_heartbeat_total",
    "Worker heartbeat ticks"
)

if __name__ == "__main__":
    # Prometheus metrics server
    start_http_server(8000)

    while True:
        heartbeat.inc()
        time.sleep(5)
