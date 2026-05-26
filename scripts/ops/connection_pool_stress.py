from __future__ import annotations

import os
import time
import threading
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
CONNECTIONS = int(os.getenv("POOL_STRESS_CONNECTIONS", "16"))
HOLD_SECONDS = float(os.getenv("POOL_STRESS_HOLD_SECONDS", "2"))

results = []
lock = threading.Lock()


def worker(i: int) -> None:
    started = time.time()
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT pg_backend_pid(), now();")
        row = cur.fetchone()
        time.sleep(HOLD_SECONDS)
        cur.close()
        conn.close()

        with lock:
            results.append({"worker": i, "status": "ok", "backend_pid": row[0], "latency_ms": round((time.time() - started) * 1000, 2)})
    except Exception as exc:
        with lock:
            results.append({"worker": i, "status": "error", "error": str(exc), "latency_ms": round((time.time() - started) * 1000, 2)})


threads = [threading.Thread(target=worker, args=(i,)) for i in range(CONNECTIONS)]

for t in threads:
    t.start()

for t in threads:
    t.join()

ok = sum(1 for r in results if r["status"] == "ok")
err = len(results) - ok

print({
    "connections_attempted": CONNECTIONS,
    "successful": ok,
    "failed": err,
    "hold_seconds": HOLD_SECONDS,
    "sample": results[:5],
})
