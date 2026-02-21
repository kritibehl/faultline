import os
from pathlib import Path

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")


def repo_root() -> Path:
    # services/api/migrate.py -> repo root is 2 levels up from services/api
    return Path(__file__).resolve().parents[2]


def migrations_dir() -> Path:
    return repo_root() / "migrations"


def list_sql_migrations(dirpath: Path) -> list[Path]:
    return sorted([p for p in dirpath.glob("*.sql") if p.is_file()])


def main():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    mdir = migrations_dir()
    files = list_sql_migrations(mdir)

    if not files:
        print(f"No migration files found in {mdir}")
        return

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  filename TEXT PRIMARY KEY,
                  applied_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute("SELECT filename FROM schema_migrations;")
            applied = {r[0] for r in cur.fetchall()}

            applied_now = 0
            for path in files:
                name = path.name
                if name in applied:
                    continue

                sql = path.read_text(encoding="utf-8")
                print(f"Applying {name}...")
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations(filename) VALUES (%s)", (name,))
                applied_now += 1

            print(f"Done. Applied {applied_now} migrations.")


if __name__ == "__main__":
    main()
