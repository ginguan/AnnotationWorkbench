"""Load original synthetic calibration cases into a disposable localhost pilot."""
import argparse
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

# Matched pairs vary the domain, not the type of adjudication.
# First-review seed judgments are deliberately opposed; no case is finalized.
SPECS = [
    ("qualifier", "a", "Can visitors enter the archive on Friday?", "Visitor tours run Monday through Friday.",
     "The archive is open Monday through Friday. On Fridays, entry is restricted to registered staff.",
     "Friday", "unsupported"),
    ("qualifier", "b", "Can members collect items on Sunday?", "Members can collect items on Sunday.",
     "The branch operates Tuesday through Sunday. Sunday pickup is restricted to couriers.",
     "Sunday", "unsupported"),
    ("same-cite", "a", "What is the initial appointment fee?", "The initial appointment costs 30 credits.",
     "The initial appointment costs 30 credits. Follow-up appointments have a separate rate.",
     "30 credits", "supported"),
    ("same-cite", "b", "How long does the first permit last?", "The first permit is valid for 30 days.",
     "The first permit is valid for 30 days. Renewals are issued for a different term.",
     "30 days", "supported"),
    ("alternate", "a", "Can guests bring a personal cup?", "Guests can bring a personal cup.",
     "Guest-owned cups are allowed at the counter. The counter accepts reusable cups brought by guests.",
     "Guest-owned cups", "supported"),
    ("alternate", "b", "Can visitors store a folding bike?", "Visitors can store a folding bike.",
     "Visitor folding bikes are accepted in the lobby. The lobby rack is available for visitors' folding bikes.",
     "Visitor folding bikes", "supported"),
    ("scope", "a", "Do all buildings offer overnight lockers?", "All buildings offer overnight lockers.",
     "Overnight lockers are installed only in the east building. Other buildings have day-use lockers.",
     "Overnight lockers", "unsupported"),
    ("scope", "b", "Do all entrances have step-free access?", "All entrances have step-free access.",
     "Step-free access is available only at the garden entrance. The other entrances have stairs.",
     "Step-free access", "unsupported"),
]


def packet():
    rows, references, manifest = [], {}, []
    for pair, side, question, answer, passages, cue, reference in SPECS:
        ident = f"{pair}-{side}"
        rows.append(dict(id=ident, question=question, answer=answer, passages=passages))
        references[ident] = reference
        if side == "a":
            manifest.append(dict(pair=pair, case_a=ident, case_b=f"{pair}-b"))
    return rows, references, manifest


def evidence(text, target, phrase):
    i = text.index(phrase)
    start = len(text[:i].encode("utf-16-le")) // 2
    return dict(target=target, start=start, end=start + len(phrase.encode("utf-16-le")) // 2)


def seeded_reviews(index, row):
    pair, _, _, _, _, cue, _ = SPECS[index]
    passage, answer = row["passages"], row["answer"]
    anchor = evidence(passage, "passages", cue)
    peer = anchor
    if pair == "alternate":
        peer = evidence(passage, "passages", passage.split(". ", 1)[1])
    return (
        dict(verdict="supported", rationale="I read this passage as support for the answer.", spans=[anchor]),
        dict(verdict="unsupported", rationale="I do not think this evidence is enough for the full answer.", spans=[peer, evidence(answer, "answer", answer)]),
    )


def load(port, run, reviewers):
    def call(actor, endpoint, body=None, content="application/json"):
        req = Request(f"http://127.0.0.1:{port}/api/{endpoint}", body,
                      {"Content-Type": content, "X-Demo-Persona": actor})
        with urlopen(req, timeout=8) as response:
            return json.load(response)
    rows, _, _ = packet()
    payload = "\n".join(json.dumps(row) for row in rows).encode()
    for reviewer in reviewers:
        batch = f"Citation pilot {run} {reviewer}"
        created = call("adjudicator", "import?batch=" + quote(batch), payload, "application/x-ndjson")
        if created["inserted"] != len(rows):
            raise ValueError("Use a fresh pilot batch name; no prior cases may be reused.")
        tasks = {task["external_id"]: task for task in call("reviewer-a", "tasks") if task["batch"] == batch}
        for index, row in enumerate(rows):
            endpoint = "tasks/" + quote(tasks[row["id"]]["id"])
            for actor, review in zip(("reviewer-a", "reviewer-b"), seeded_reviews(index, row)):
                call(actor, endpoint, json.dumps(review).encode())
            details = call("adjudicator", endpoint)
            if details["state"] != "needs_adjudication" or details["final"] is not None:
                raise ValueError(f"Expected a pending adjudication for {row['id']}")
    print(f"Loaded {len(reviewers) * len(rows)} pending adjudications across {len(reviewers)} isolated batches.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--manifest", action="store_true")
    modes.add_argument("--reference-key", action="store_true")
    modes.add_argument("--disposable-port", type=int, help="must be a dedicated pilot server, not 5194")
    parser.add_argument("--reviewer", action="append")
    parser.add_argument("--run", default="round-1")
    args = parser.parse_args()
    if args.manifest:
        print(json.dumps(packet()[2], indent=2))
    elif args.reference_key:
        print(json.dumps(packet()[1], indent=2))
    else:
        if args.disposable_port == 5194 or not args.reviewer or len(set(args.reviewer)) != len(args.reviewer):
            parser.error("Use a dedicated port and unique reviewer aliases.")
        load(args.disposable_port, args.run, args.reviewer)
