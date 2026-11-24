"""Run against a disposable local instance: python3 tests/api_smoke.py 5195."""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5195
BASE = f"http://127.0.0.1:{PORT}"
A, B, J = "reviewer-a", "reviewer-b", "adjudicator"


def http(persona, path, payload=None):
    req = Request(f"{BASE}/api/{path}", headers={"X-Demo-Persona": persona})
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(payload).encode()
    try:
        response = urlopen(req, timeout=6)
    except HTTPError as err:
        response = err
    data = response.read()
    return response.code, data.decode() if path == "export" and response.code == 200 else json.loads(data)


def span(task, target, snippet):
    i = task[target].index(snippet)
    start = len(task[target][:i].encode("utf-16-le")) // 2
    return {"target": target, "start": start, "end": start + len(snippet.encode("utf-16-le")) // 2}


def rv(verdict, evidence, rationale):
    return {"verdict": verdict, "rationale": rationale, "spans": evidence}


def test_import():
    row = {"id": "zz-listed", "question": "When is pickup?", "passages": "Pickup opens at noon.", "answer": "At noon."}

    def send(rows=None, payload=None, actor=J):
        body = payload if payload is not None else "\n".join(json.dumps(r) for r in rows).encode()
        req = Request(BASE + "/api/import?batch=Intake%20check", body,
                      {"X-Demo-Persona": actor, "Content-Type": "application/x-ndjson"})
        try:
            result = urlopen(req, timeout=8)
        except HTTPError as err:
            result = err
        return result.code, json.loads(result.read())

    def imported():
        return [t for t in http(A, "tasks")[1] if t["batch"] == "Intake check"]

    assert send([row], actor=A)[0] == 403
    status, error = send(payload=json.dumps(row).encode() + b"\n{broken")
    assert status == 400 and "Line 2" in error["error"] and not imported()
    assert send([row, row])[0] == 400 and not imported()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [job.result() for job in [pool.submit(send, [row]) for _ in range(2)]]
    assert all(code == 200 for code, _ in responses)
    assert sorted(result["inserted"] for _, result in responses) == [0, 1]

    task, = imported()
    assert task["external_id"] == "zz-listed"
    path = "tasks/" + task["id"]
    _, detail = http(A, path)
    annotation = rv("supported", [span(detail, "passages", "opens at noon")], "The opening time matches.")
    assert http(A, path, annotation)[0] == 200
    assert send([row])[1]["skipped"] == 1
    assert send([{**row, "id": "aa-rolled-back"}, {**row, "answer": "At midnight."}])[0] == 409
    assert len(imported()) == 1
    assert http(A, path)[1]["reviews"][0]["rationale"] == annotation["rationale"]
    assert http(B, path)[1]["reviews"] == []


def main():
    status, tasks = http(A, "tasks")
    assert status == 200 and len(tasks) == 33
    assert len([t for t in tasks if t["source"] == "RAGTruth"]) == 30
    assert http(A, "export")[0] == 403
    assert http(B, "batch-metrics")[0] == 403

    def metrics(batch="Demo"):
        status, rows = http(J, "batch-metrics")
        assert status == 200
        return next(row for row in rows if row["batch"] == batch)

    assert metrics()["awaiting_reviews"] == 3
    assert metrics()["finalized"] == 0
    assert metrics("RAGTruth QA")["total"] == 30

    assert http(J, "tasks/demo-01")[0] == 404
    _, task = http(A, "tasks/demo-01")
    one = rv("unsupported", [span(task, "answer", "Tuesdays through Fridays")], "The answer adds days.")
    two = rv("supported", [span(task, "passages", "Tuesdays and Thursdays")], "I considered the booking hours.")
    final = rv("unsupported", one["spans"], "Only Tuesdays and Thursdays are supported.")
    assert http(A, "tasks/demo-01", rv("unsupported", [], "Missing highlight."))[0] == 400
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(http, A, "tasks/demo-01", one) for _ in range(2)]]
    assert sorted((status, res["replayed"]) for status, res in results) == [(200, False), (200, True)]
    _, peer = http(B, "tasks/demo-01")
    assert peer["reference"] is None and peer["reviews"] == [] and peer["canSubmit"]
    assert http(A, "tasks/demo-01", {**one, "rationale": "Changed text."})[0] == 409
    assert http(B, "tasks/demo-01", two)[0] == 200
    assert http(A, "tasks/demo-01")[1]["state"] == "needs_adjudication"
    pending = metrics()
    assert (pending["needs_adjudication"], pending["finalized"], pending["verdict_split"]) == (1, 0, 0)
    assert http(J, "export") == (200, "")
    queue = http(J, "tasks")[1]
    assert len(queue) == 1 and queue[0]["triage"] == {"reason":"verdict_split","overlap":None}
    assert "triage" not in next(t for t in http(A, "tasks")[1] if t["id"] == "demo-01")
    assert len(http(J, "tasks/demo-01")[1]["reviews"]) == 2
    assert http(J, "tasks/demo-01", final)[0] == 200
    assert http(B, "tasks/demo-01")[1]["final"]["verdict"] == "unsupported"
    export_rows = [json.loads(line) for line in http(J, "export")[1].splitlines()]
    assert len(export_rows) == 1
    row = export_rows[0]
    assert row["resolution"] == "adjudicated" and len(row["original_reviews"]) == 3
    assert row["spans"][0]["text"] == "Tuesdays through Fridays"
    assert row["offset_unit"] == "utf16-code-units" and row["rubric_version"] == "grounding-v1"
    assert "reference" not in row
    closed = metrics()
    assert (closed["awaiting_reviews"], closed["needs_adjudication"], closed["finalized"], closed["verdict_split"]) == (2, 0, 1, 1)

    ras = next(t["id"] for t in tasks if t["source"] == "RAGTruth")
    _, real = http(A, "tasks/"+ras)
    assert real["reference"] is None and real["reviews"] == [] and real["question"] and real["passages"]
    agreed = rv("supported", [{"target": "passages", "start": 0, "end": 8}], "This selection is the fixed test fixture.")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [f.result() for f in [pool.submit(http, who, "tasks/"+ras, agreed) for who in (A, B)]]
        assert a[0] == b[0] == 200, (a, b)
    agreed_detail = http(A, "tasks/"+ras)[1]
    assert agreed_detail["state"] == "complete" and agreed_detail["reference"] is not None
    assert metrics("RAGTruth QA")["finalized"] == 1
    assert metrics()["finalized"] == 1

    ras_ids = [t["id"] for t in tasks if t["source"] == "RAGTruth"]
    diff = "tasks/" + ras_ids[1]
    for actor, end in [(A, 12), (B, 15)]:
        record = rv("unsupported", [{"target": "answer", "start":0, "end":end}], "Distinct claim selection fixture.")
        assert http(actor, diff, record)[0] == 200
    assert http(J, diff)[1]["state"] == "needs_adjudication"
    assert metrics("RAGTruth QA")["claim_span_split"] == 0
    queue = http(J, "tasks")[1]
    assert queue[0]["id"] == ras_ids[1] and queue[0]["triage"] == {"reason":"claim_span_split","overlap":0.8}
    assert http(J, diff, record)[0] == 200

    unsure = "tasks/" + ras_ids[2]
    record = rv("uncertain", [], "Uncertainty fixture for batch quality.")
    for actor in (A, B):
        assert http(actor, unsure, record)[0] == 200
    assert metrics("RAGTruth QA")["both_uncertain"] == 0
    assert http(J, unsure, record)[0] == 200
    qa = metrics("RAGTruth QA")
    assert (qa["total"], qa["awaiting_reviews"], qa["needs_adjudication"], qa["finalized"], qa["adjudicated"]) == (30, 27, 0, 3, 2)
    assert (qa["verdict_split"], qa["claim_span_split"], qa["both_uncertain"]) == (0, 1, 1)
    test_import()
    print("PASS: atomic JSONL import, role check, concurrent dedupe, conflict rollback, review preservation.")
    print("PASS: 30 RAGTruth samples; blind reviews; concurrent writes; consensus/adjudication; JSONL; batch metric denominators and reason breakdown.")


if __name__ == "__main__":
    main()
