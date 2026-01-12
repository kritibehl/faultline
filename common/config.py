import os

def env(key: str, default: str | None = None) -> str:
    v = os.getenv(key, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {key}")
    return v

POSTGRES_DSN = env("POSTGRES_DSN", "postgresql+psycopg2://faultline:faultline@localhost:5432/faultline")
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

STREAM_KEY = env("STREAM_KEY", "faultline.jobs")
CONSUMER_GROUP = env("CONSUMER_GROUP", "workers")
CONSUMER_NAME = env("CONSUMER_NAME", "worker-1")

LEASE_SECONDS = int(env("LEASE_SECONDS", "30"))
MAX_ATTEMPTS_DEFAULT = int(env("MAX_ATTEMPTS_DEFAULT", "3"))
