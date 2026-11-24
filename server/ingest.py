"""Validate an entire local JSONL batch before inserting immutable tasks."""
import hashlib
import json
import re

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 300
EXTERNAL_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
LIMITS = {"question": 800, "passages": 20_000, "answer": 10_000}


class ImportIssue(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def parse(batch, blob):
    batch = " ".join(batch.split())
    if not 1 <= len(batch) <= 70 or any(not c.isprintable() for c in batch) or batch.casefold() in {"demo","ragtruth qa","all batches"}:
        raise ImportIssue(400, "Enter a unique batch name of 1–70 characters (Demo and RAGTruth QA are reserved).")
    try:
        lines = blob.decode("utf-8-sig").split("\n")
    except UnicodeDecodeError as ex:
        raise ImportIssue(400, "The file must be UTF-8 JSONL.") from ex
    rows = {}
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        if len(rows) == MAX_ROWS:
            raise ImportIssue(400, f"Only {MAX_ROWS} rows are allowed in one import.")
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, RecursionError) as ex:
            raise ImportIssue(400, f"Line {number}: invalid JSON.") from ex
        if not isinstance(row, dict) or set(row) != {"id", *LIMITS}:
            raise ImportIssue(400, f"Line {number}: expected exactly id, question, passages, and answer.")
        external = row["id"]
        if not isinstance(external, str) or not EXTERNAL_ID.fullmatch(external):
            raise ImportIssue(400, f"Line {number}: id must be 1–64 letters, digits, underscores or hyphens.")
        if external in rows:
            raise ImportIssue(400, f"Line {number}: duplicate id in this file ({external}).")
        for field, limit in LIMITS.items():
            value = row[field]
            if not isinstance(value, str) or not value.strip() or len(value) > limit or "\0" in value:
                raise ImportIssue(400, f"Line {number}: {field} must be text, max {limit:,} characters.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as ex:
                raise ImportIssue(400, f"Line {number}: {field} contains invalid Unicode.") from ex
        rows[external] = row
    if not rows:
        raise ImportIssue(400, "The file has no tasks.")
    return batch, rows


def import_tasks(cur, batch, blob):
    batch, rows = parse(batch, blob)
    inserted = 0
    # Identical ordering keeps overlapping imports from locking IDs in reverse order.
    for external, row in sorted(rows.items()):
        digest = hashlib.sha256(f"{batch}\n{external}".encode()).hexdigest()
        internal = f"import-{digest}"
        content = tuple(row[field] for field in LIMITS)
        cur.execute("""INSERT INTO task(id,batch,source,external_id,question,passages,answer)
                       VALUES (%s,%s,'user import',%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING RETURNING id""", (internal,batch,external,*content))
        if cur.fetchone():
            inserted += 1
        else:
            cur.execute("SELECT question,passages,answer FROM task WHERE id=%s", (internal,))
            existing = cur.fetchone()
            if tuple(existing[field] for field in LIMITS) != content:
                raise ImportIssue(409, f"Task {external} already exists with different content. No rows were imported. Use a new ID or batch name.")
    return {"batch": batch, "inserted": inserted, "skipped": len(rows)-inserted, "total": len(rows)}
