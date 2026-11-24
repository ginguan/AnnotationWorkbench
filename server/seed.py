import json
from pathlib import Path

from psycopg2.extras import Json

from app import ROOT, cursor


def seed(paths):
    with cursor() as cur:
        cur.execute((ROOT / "server" / "schema.sql").read_text())
        for path in paths:
            if not path.is_file():
                continue
            for line in path.read_text().splitlines():
                row = json.loads(line)
                cur.execute("""INSERT INTO task(id,batch,source,question,passages,answer)
                               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                            tuple(row[k] for k in ("id", "batch", "source", "question", "passages", "answer")))
                if cur.fetchone() and "reference" in row:
                    cur.execute("INSERT INTO reference_label(task_id,tags) VALUES (%s,%s)",
                                (row["id"], Json(row["reference"])))


if __name__ == "__main__":
    seed([ROOT / "data" / "demo.jsonl", ROOT / "data" / "ragtruth.jsonl"])
