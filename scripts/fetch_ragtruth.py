"""Fetch 30 official test examples. No model calls or credentials needed."""
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REV = "c103204b9ce28d6bbad859304bf30de72b8ed8fe"


def stream(name):
    url = f"https://raw.githubusercontent.com/ParticleMedia/RAGTruth/{REV}/dataset/{name}.jsonl"
    with tempfile.TemporaryFile() as f:
        subprocess.run(["curl", "-fsSL", "--max-time", "120", url], stdout=f, check=True)
        f.seek(0)
        for line in f:
            yield json.loads(line)


def main():
    samples, sources, clean, flagged = [], set(), 0, 0
    qa = {x["source_id"]: x["source_info"] for x in stream("source_info") if x["task_type"] == "QA"}
    for response in stream("response"):
        key = response["source_id"]
        if key not in qa or key in sources or response["split"] != "test" or response["quality"] != "good":
            continue
        tags = response["labels"]
        if (tags and flagged == 15) or (not tags and clean == 15):
            continue
        flagged += bool(tags)
        clean += not tags
        sources.add(key)
        samples.append({"id": "rag-" + response["id"], "batch": "RAGTruth QA",
                        "source": "RAGTruth", "question": qa[key]["question"], "passages": qa[key]["passages"],
                        "answer": response["response"], "reference": tags})
        if len(samples) == 30:
            break
    if len(samples) != 30:
        raise RuntimeError("Expected 30 QA samples with unique source IDs.")
    output = ROOT / "data" / "ragtruth.jsonl"
    output.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples))
    print(f"Imported {len(samples)} fixture rows from {REV[:12]} into {output.name}.")


if __name__ == "__main__":
    main()
