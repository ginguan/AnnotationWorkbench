"""Loopback-only portfolio demo; the persona switch is not production authentication."""
import argparse
import json
import os
import re
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ingest import ImportIssue, MAX_BYTES, import_tasks
from triage import answer_iou, ordering

import psycopg2
from psycopg2.extras import Json, RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = {"reviewer-a", "reviewer-b", "adjudicator"}
VERDICTS = {"supported", "unsupported", "uncertain"}
ID = re.compile(r"[a-zA-Z0-9_-]{1,80}")
BATCH_METRICS_SQL = (ROOT / "server" / "batch_metrics.sql").read_text()


class Problem(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@contextmanager
def cursor(read_only=False):
    conn = psycopg2.connect(os.environ["ANNOTATION_DSN"], cursor_factory=RealDictCursor)
    try:
        if read_only:
            conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn, conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def task_progress(cur, task_id):
    cur.execute("SELECT state, reason, adjudicated FROM review_progress WHERE id=%s", (task_id,))
    return cur.fetchone()


def fetch_reviews(cur, task_id):
    cur.execute("SELECT actor, verdict, rationale, spans, created_at FROM review WHERE task_id=%s", (task_id,))
    return {r["actor"]: dict(r) for r in cur}


def utf16_slice(value, start, end):
    raw = value.encode("utf-16-le")
    if not 0 <= start < end <= len(raw) // 2:
        raise Problem(400, "A selection is outside the text.")
    try:
        return raw[2*start:2*end].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise Problem(400, "A selection splits a character.") from exc


def validated_review(task, payload):
    if not isinstance(payload, dict):
        raise Problem(400, "Invalid submission.")
    verdict, rationale, spans = (payload.get(k) for k in ("verdict", "rationale", "spans"))
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise Problem(400, "Choose a verdict.")
    if not isinstance(rationale, str) or not 3 <= len(rationale.strip()) <= 1500 or "\0" in rationale:
        raise Problem(400, "Enter a rationale of 3–1,500 characters.")
    if not isinstance(spans, list) or len(spans) > 10:
        raise Problem(400, "Add at most ten selections.")
    cleaned = []
    for span in spans:
        if not isinstance(span, dict):
            raise Problem(400, "Invalid selection.")
        target, start, end = (span.get(k) for k in ("target", "start", "end"))
        if target not in ("answer", "passages") or type(start) is not int or type(end) is not int:
            raise Problem(400, "Invalid selection.")
        exact = utf16_slice(task[target], start, end)
        if not exact.strip():
            raise Problem(400, "Select actual text.")
        cleaned.append({"target": target, "start": start, "end": end, "text": exact})
    cleaned.sort(key=lambda s: (s["target"], s["start"], s["end"]))
    if len({(s["target"], s["start"], s["end"]) for s in cleaned}) != len(cleaned):
        raise Problem(400, "Remove duplicate selections.")
    required = {"supported": "passages", "unsupported": "answer"}.get(verdict)
    if required and not any(s["target"] == required for s in cleaned):
        raise Problem(400, "Highlight a supporting passage." if required == "passages" else "Highlight an unsupported claim in the answer.")
    return verdict, rationale.strip(), cleaned


def task_detail(cur, task_id, actor):
    cur.execute("SELECT * FROM task WHERE id=%s", (task_id,))
    task = cur.fetchone()
    if not task:
        raise Problem(404, "Task not found.")
    reviews = fetch_reviews(cur, task_id)
    progress = task_progress(cur, task_id)
    state = progress["state"]
    final = reviews["adjudicator" if progress["adjudicated"] else "reviewer-a"] if state == "complete" else None
    if actor == "adjudicator" and state == "awaiting_reviews":
        raise Problem(404, "No adjudication available.")
    # Server-side blinding: peers receive only their own submission until completion.
    visible = list(reviews.values()) if state == "complete" or actor == "adjudicator" else [reviews[actor]] if actor in reviews else []
    reference = None
    if state == "complete":
        cur.execute("SELECT tags FROM reference_label WHERE task_id=%s", (task_id,))
        row = cur.fetchone()
        reference = row["tags"] if row else None
    return {**task, "state": state, "reviews": visible, "final": final, "reference": reference,
            "canSubmit": actor not in reviews and (state == "needs_adjudication" if actor == "adjudicator" else state == "awaiting_reviews")}


def submit(cur, task_id, actor, payload):
    cur.execute("SELECT * FROM task WHERE id=%s FOR UPDATE", (task_id,))
    task = cur.fetchone()
    if not task:
        raise Problem(404, "Task not found.")
    verdict, rationale, spans = validated_review(task, payload)
    reviews = fetch_reviews(cur, task_id)
    if existing := reviews.get(actor):
        if (existing["verdict"], existing["rationale"], existing["spans"]) == (verdict, rationale, spans):
            return {"saved": True, "replayed": True}
        raise Problem(409, "You already submitted this task. The original review is preserved.")
    state = task_progress(cur, task_id)["state"]
    if actor == "adjudicator" and state != "needs_adjudication":
        raise Problem(409, "Only completed reviewer pairs with a disagreement or uncertainty can be adjudicated.")
    if actor != "adjudicator" and state != "awaiting_reviews":
        raise Problem(409, "This review is closed.")
    cur.execute("INSERT INTO review(task_id,actor,verdict,rationale,spans) VALUES (%s,%s,%s,%s,%s)",
                (task_id, actor, verdict, rationale, Json(spans)))
    return {"saved": True, "replayed": False}


def task_list(cur, actor):
    cur.execute("""
        SELECT p.id,p.batch,p.source,t.question,t.external_id,p.rubric,p.state,(r.actor IS NOT NULL) AS submitted
        FROM review_progress p JOIN task t ON t.id=p.id
        LEFT JOIN review r ON r.task_id=p.id AND r.actor=%s
        WHERE %s <> 'adjudicator' OR p.state <> 'awaiting_reviews'
        ORDER BY (p.source='synthetic') DESC,p.id
    """, (actor, actor))
    tasks = cur.fetchall()
    if actor != "adjudicator":
        return tasks
    cur.execute("""
      SELECT p.id, p.reason, a.spans AS left_spans, b.spans AS right_spans
      FROM review_progress p
      JOIN review a ON a.task_id=p.id AND a.actor='reviewer-a'
      JOIN review b ON b.task_id=p.id AND b.actor='reviewer-b'
      WHERE p.state='needs_adjudication'
    """)
    conflicts = {r["id"]: r for r in cur}
    for task in tasks:
        if conflict := conflicts.get(task["id"]):
            task["reason"] = conflict["reason"]
            task["overlap_exact"] = (answer_iou(conflict["left_spans"],conflict["right_spans"])
                                     if conflict["reason"] == "claim_span_split" else None)
    tasks.sort(key=ordering)
    for task in tasks:
        if "reason" in task:
            overlap = task.pop("overlap_exact")
            task["triage"] = {"reason": task.pop("reason"), "overlap": float(overlap) if overlap is not None else None}
    return tasks


def export(cur):
    output = []
    for task in task_list(cur, "adjudicator"):
        if task["state"] != "complete":
            continue
        detail = task_detail(cur, task["id"], "adjudicator")
        selection = detail["final"]
        output.append({
            "task_id": task["id"], "external_id": detail["external_id"], "batch": task["batch"], "source": task["source"], "rubric_version": task["rubric"],
            "question": detail["question"], "passages": detail["passages"], "answer": detail["answer"],
            "verdict": selection["verdict"], "resolution": "adjudicated" if selection["actor"] == "adjudicator" else "consensus",
            "rationale": selection["rationale"], "spans": selection["spans"],
            "original_reviews": detail["reviews"], "offset_unit": "utf16-code-units",
        })
    return "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in output)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.api()
        if self.path not in ("/", "/index.html") and not re.fullmatch(r"/assets/[a-zA-Z0-9_.-]+", self.path):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        return self.api()

    def reply(self, code, obj=None, download=None):
        raw = download.encode() if download is not None else json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8" if download is not None else "application/json; charset=utf-8")
        if download is not None:
            self.send_header("Content-Disposition", 'attachment; filename="reviewed-annotations.jsonl"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def api(self):
        try:
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host or self.headers.get("Origin") not in (None, f"http://{host}"):
                raise Problem(403, "Use the local preview URL.")
            actor = self.headers.get("X-Demo-Persona")
            if actor not in PERSONAS:
                raise Problem(403, "Choose a demo persona.")
            url = urlsplit(self.path)
            if self.command == "POST" and url.path == "/api/import":
                if actor != "adjudicator":
                    raise Problem(403, "Only the adjudicator can import batches.")
                if self.headers.get_content_type() != "application/x-ndjson":
                    raise Problem(415, "Upload a JSONL file.")
                length = self.headers.get("Content-Length", "")
                if not length.isdecimal() or not 1 <= int(length) <= MAX_BYTES:
                    raise Problem(413, "Choose a nonempty file up to 2 MiB.")
                names = parse_qs(url.query, keep_blank_values=True).get("batch", [])
                if len(names) != 1:
                    raise Problem(400, "Enter a batch name.")
                self.connection.settimeout(8)
                blob = self.rfile.read(int(length))
                if len(blob) != int(length):
                    raise Problem(400, "Incomplete upload.")
                with cursor() as cur:
                    imported = import_tasks(cur, names[0], blob)
                return self.reply(200, imported)
            with cursor(read_only=self.command == "GET") as cur:
                if self.command == "GET" and self.path == "/api/tasks":
                    return self.reply(200, task_list(cur, actor))
                if self.command == "GET" and self.path == "/api/batch-metrics":
                    if actor != "adjudicator":
                        raise Problem(403, "Only the adjudicator can view batch metrics.")
                    cur.execute(BATCH_METRICS_SQL)
                    return self.reply(200, cur.fetchall())
                if self.command == "GET" and self.path == "/api/export":
                    if actor != "adjudicator":
                        raise Problem(403, "Only the adjudicator can export.")
                    return self.reply(200, download=export(cur))
                parts = self.path.split("/")
                if len(parts) != 4 or parts[1:3] != ["api", "tasks"] or not ID.fullmatch(parts[3]):
                    raise Problem(404, "Route not found.")
                if self.command == "GET":
                    return self.reply(200, task_detail(cur, parts[3], actor))
                if self.headers.get_content_type() != "application/json":
                    raise Problem(415, "Use JSON.")
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdecimal() or not 1 <= int(raw_length) <= 16384:
                    raise Problem(400, "Invalid request size.")
                self.connection.settimeout(8)
                try:
                    payload = json.loads(self.rfile.read(int(raw_length)))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise Problem(400, "Invalid JSON.") from exc
                outcome = submit(cur, parts[3], actor, payload)
            # Commit before acknowledging the write.
            self.reply(200, outcome)
        except (Problem, ImportIssue) as exc:
            self.reply(exc.code, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5194)
    args = parser.parse_args()
    if not (ROOT / "dist" / "index.html").is_file():
        parser.error("Run npm run build first.")
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=ROOT / "dist")) as server:
        print(f"Evidence Desk: http://127.0.0.1:{server.server_port}  (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
