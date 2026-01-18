import glob
import os

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    files = sorted(glob.glob("/app/migrations/*.sql"))
    if not files:
        print("No migration files found.")
        return

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            sql = f.read().strip()
        if sql:
            print(f"Applying {path} ...")
            cur.execute(sql)

    cur.close()
    conn.close()
    print("Migrations applied.")

if __name__ == "__main__":
    main()
