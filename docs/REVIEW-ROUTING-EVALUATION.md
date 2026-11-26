# Adaptive review: public-benchmark replay

**Question:** Can better routing reduce follow-up review work without recovering fewer initially missed unsupported answers? This experiment uses authentic annotator votes from the [TRIVIA+ public release](https://github.com/amazon-science/hallucination-benchmark-trivialplus), played back offline. The original workbench remains double blind; this does not change live routing.

## Result on the source-article-disjoint test set

Among 375 cases the first reviewer passed, the published consensus labeled 27 unsupported. A random baseline sent 50% to second review. We chose the risk policy's budget on the validation set, before evaluation. Results are means across 64 fixed audit/random seeds and one frozen assignment of reviewer roles; the seeds do not represent different test cohorts.

| Follow-up metric | Random 50% | Risk + audit |
|---|---:|---:|
| Second reviews assigned | 188 | 102 |
| Disagreements sent to simulated adjudication | 31.42 | 30.06 |
| Initially missed cases recovered | 12.77 | 16.41 |
| Unsupported responses still missed | 14.23 | 10.59 |
| Modeled review-equivalent work (one adjudication costs two second reviews) | 250.84 | 162.13 |

That is **35.4% less modeled follow-up work under this comparison**, not 35.4% less team time. If a second review takes two minutes and adjudication four, the modeled difference is about 177 minutes in this cohort; neither duration is measured here. With adjudication weights of one and four, the comparisons changed to approximately 41% and 25% lower modeled follow-up work respectively. Initial review is shared across both policies and is excluded from these numbers. At the same **188** second reviews instead, risk routing recovered 22.25 cases but increased modeled work to 278.38 because it found more disagreements.

**Important sensitivity:** The published consensus includes the same votes used for the replay. When the reference uses only additional annotators' votes on the 270 eligible cases, the cheap risk policy recovered **12.22** versus **14.02** for random (at the same second-review budget, 21.59 versus 14.02). Those additional ratings are not a random sample, and their consensus is a different reference. The current tuned policy therefore has **not** demonstrated stable, equal-quality workload savings.

## How it works

- Review roles are assigned by a fixed, deterministic shuffle of the available distinct human votes; they are not historical chronological first and second reviewers. Records with repeated annotator IDs, unsupported raw vote encodings or misaligned lists are excluded (180 train, 34 validation, 68 test).
- Fit two logistic regressions on the training split. One predicts recovering an initial miss if reviewed; the other predicts a disagreement requiring adjudication. Features use the source, question, answer, model/source category and first review only. The leading policy ranks by expected recovery divided by expected cost; it reserves every tenth slot for an audit sampled from remaining rows. The published reference and second votes are outcomes, never test-time inputs. Source article hashes prevent overlap across partitions.
- On validation, select the cheapest budget that recovers at least as many misses as the 50%-budget random baseline, then freeze that fraction. A second-review disagreement incurs a modeled adjudication cost, and the already-published reference serves as the offline verdict. No measured reviewer minutes, annotation chronology, or new live adjudications are claimed.
- Before live use, predefine an acceptable missed-unsupported rate, randomly audit skipped cases, and measure active review/correction times as well as final quality in a pilot. Increase the audit or return to double review if the audited miss rate crosses the threshold.

## Reproduce locally

The [publisher's metadata and license](https://github.com/amazon-science/hallucination-benchmark-trivialplus) apply; keep downloaded data out of the public repo. The script verifies the release hash and outputs only counts and cohort-level metrics. Install `pyarrow==26.0.1` and `scikit-learn==1.8.0` in a local Python 3.11 environment for the evaluated setup.

```sh
mkdir -p .local
curl -fL 'https://raw.githubusercontent.com/amazon-science/hallucination-benchmark-trivialplus/main/triviaplus_dataset.parquet' -o .local/triviaplus_dataset.parquet
python3 scripts/evaluate_review_routing.py
python3 -m unittest discover -s tests -p 'test_review_routing_evaluation.py'
```

The machine-readable report is written to `.local/triviaplus-review-report.json`. The in-app synthetic replay remains a separate, reproducible explanation of the mechanics.

## Follow-up: tune the review budget on independent votes

Run `PYTHONHASHSEED=0 python3 scripts/evaluate_independent_routing.py` with the same dependencies and pinned dataset. This follow-up keeps the previously trained scoring method, but sets the budget using only reserved-voter labels on 124 validation cases. The test has 270 first-pass approvals with extra votes and 74 initial misses under that reference. At a 2:1 simulated adjudication cost:

| Test metric | Random half | Risk + audit, validation-tuned | All eligible cases reviewed |
|---|---:|---:|---:|
| Second reviews | 135 | 65 | 270 |
| Misses recovered | 14.02 | 11.47 | 28.00 |
| Modeled follow-up work | 197.97 | 111.25 | 396.00 |

The cheaper policy met the recovery target on validation, but failed it on the held-out test. The result also missed the random baseline when adjudication cost was modeled at 1:1 or 4:1. This does not demonstrate quality-preserving savings. The full second pass applies to first-pass approvals in this cohort only; disagreements are resolved against the reserved-vote reference and even the full pass misses cases both replay reviewers pass. The test cohort was already used to report the earlier sensitivity, so this is a follow-up diagnostic, not a new prospective confirmation. For confirmation, freeze a more conservative budget or guardrail and use a fresh blind cohort; count audit and rework time.

### Plan a blind sample before relying on skipped reviews

`python3 scripts/plan_skip_audit.py 205 --cap 0.05` returns 48: for a fixed batch of 205 skips, a uniform sample of 48 distinct cases with **zero** observed misses rules out 11 or more misses at a one-sided 5% error rate, assuming correct independent audit judgments. The integer threshold is `ceil(batch size × cap)`. This is a planning example, not an audit pass. Do not ignore an observed miss or reuse the threshold while repeatedly checking batches. Record audit labor, adjudication and correction time in the comparison; use a new cohort and lock the policy before inspecting outcomes.

At the independent-label operating point (65 routed and 205 skipped), add the audit sample itself to the modeled 111.25 follow-up units. The zero-hit designs for 10%, 5%, 2% and 1% caps require 26, 48, 92 and 129 blind reviews, for lower-bound totals of 137.25, 159.25, 203.25 and 240.25, before audit adjudication or repairs. Compare with the original half-random policy at 197.97 units, **without** an equivalent audit requirement; this is a cost sensitivity, not an equal-quality comparison. At a 2% cap, audit review alone erases the apparent workload advantage over that baseline. No audit has been run.

For a fresh authorized batch, freeze routing before sampling. A local pilot coordinator can run `python3 scripts/prepare_blind_audit.py INPUT.jsonl .local/blind-batch --cap .05 --controls 10` with unique case IDs, a boolean `skipped`, and question, answer and source passages. The tool uniformly samples skips, mixes in random routed controls and creates `reviewer.jsonl` with only opaque case IDs and task content. Keep the input and coordinator key private; only the reviewer packet is intended for authorized blind reviewers. Check that the source content itself contains no annotation or routing clues. Collect the verdict and active time before unblinding. Tests and the CLI smoke check use synthetic cases; no real audit or timing data has been collected.

## External transfer check: MEMERAG-Ext English

The [MEMERAG paper](https://aclanthology.org/2025.acl-long.1101/) and [publisher release](https://github.com/amazon-science/MEMERAG) provide a separate benchmark. Keep the publisher’s `data/memerag_ext/en.jsonl` in ignored `.local/memerag-ext-en.jsonl`, then run `PYTHONHASHSEED=0 python3 scripts/evaluate_memerag_transfer.py` with the original TRIVIA+ dependencies. Both releases are hash-checked and only aggregate results are written. The 150 question-context groups (226 sentences) remain whole. A vote slot flags a question if it flags any answer sentence. Reserve three slots for majority reference; the first and second slots are separate from those three per row. Because reviewer IDs are missing, slots are not treated as known individual reviewers across sentences or cases.

Freeze the TRIVIA+-trained scorer and its 24.2% review budget; unseen categories have no training column and the unavailable first-review supplementary feature is omitted. Against random review at the same budget, risk plus its existing internal audit slot recovered more misses in three of five slot assignments, tied one, and recovered fewer in one. There were only 1–7 initial misses per assignment. These assignments reuse the same questions, not independent trials. Against random review of half the cases the result is likewise mixed. This external replay is a portability check, not evidence of equal-quality labor savings or a timed operational audit. The additional audit sample, audit adjudication, and repairs are not in the replay cost.

## Prioritize the full queue without skipping

Run `PYTHONHASHSEED=0 python3 scripts/evaluate_review_priority.py` against both pinned local releases. Compare one random queue with the frozen cost-aware ranking (including every tenth random discovery slot). Both eventually review everyone; this changes speed of discovery, not total work or final quality. The simulation charges 2 assumed minutes per review plus 4 for each immediate adjudication, and counts a correction only after both finish. No actual staff times, FIFO arrival order, or parallel reviewers are available.

TRIVIA+ independent votes: at 30 modeled minutes, 2.00 misses recovered vs 0.84 in random order (6.00 vs 10.19 completed reviews); at 120 minutes, 8.20 vs 4.09. MEMERAG-Ext at 30 min was 2 better, 1 tie, 2 worse across reused vote-slot assignments, with 0–3 recoverable cases in each. The former suggests earlier discovery on that cohort, not universal savings. A live paired timing test and a chronological/FIFO baseline are still needed.

## Adjudicator citation navigation pilot

Only a pending adjudication displays citation jumps and descriptive overlap hints. Both reviewers remain blind before submission. A jump highlights the saved anchor in the full source or answer instead of replacing it with a clip; stale or invalid anchors require manual inspection. Different citations can support the same decision, as in the [FEVER task](https://fever.ai/2018/task.html); overlapping citations do not imply agreement. No verdict is suggested or changed.

For a timing pilot, compare the existing cards plus full text to the same view with the citation navigation enabled. Use unfamiliar matched cases and randomized/counterbalanced assignment so each adjudicator never sees the same case twice. Log active time through submission, any rework, and material verdict errors against an independent reference. Include differing valid citations, opposing verdicts on the same citation, qualifiers immediately outside an anchor, and stale anchors. Exploratory UI success does not establish time savings. For example, if 10% of cases reach adjudication, saving 60 seconds there is 6 seconds averaged across all cases before adding any other work.

Use `python3 scripts/score_citation_pilot.py .local/citation-timing.csv` with header `reviewer,pair,case,mode,order,active_s,rework_s,correct`. Use opaque IDs, modes `baseline` or `jump`, pair-local positions 1 or 2 and an independently scored initial verdict (1 = no material error). A pair is two different matched cases assigned to the same reviewer. Start when the case is visible, pause for unrelated interruptions, stop at first submission, and add active correction time separately. If setup or error scoring differs by arm, fix that before treating the results as comparable. The output records the number of reviewers, mode order, paired savings including rework, and error counts side by side. These are descriptive pilot outputs, not proof of equal quality. The scorer's tests use fabricated records; no timed pilot has run.

Prepare an assignment sheet with `python3 scripts/assign_citation_pilot.py .local/matched-cases.json .local/timing-assignment.csv --reviewer r1 --reviewer r2 --reviewer r3 --reviewer r4 --seed 24`. The manifest is an array of objects such as `{"pair":"p01","case_a":"case-17","case_b":"case-31"}`. Choose pairs of comparable passage length and judgment difficulty before assignment, and keep reference verdicts in a separate coordinator file. Each reviewer gets both modes and never sees the same case twice; over each block of four reviewers, each case appears once in each mode and position combination. Run in the generated row order. Append `active_s,rework_s,correct` for the scorer after collecting results. This assigns cases but does not instrument the app or collect timing. Do not treat a four-person exploratory pilot as an equivalence test.

For the local pilot, use the same app build in both arms: default URL for jump mode, and `/#citation-pilot-baseline` for the baseline. Baseline retains the full text, both review records, evidence selection and final submission; only citation jumps and overlap hints are removed. This URL option is not an access or data-isolation control. Use separate pending case IDs assigned to each session so immutable submissions do not collide; do not time a case already finalized in another session.

#### Synthetic practice round

The fixture loader creates four matched pairs (eight short cases): a qualifier outside the citation, opposing interpretations of the same citation, alternate citations and an overbroad claim. These are practice/calibration cases, not representative production evidence. Keep the reference key away from participants, and use fresh, longer cases afterward before interpreting a timing effect.

In one terminal, use a fresh disposable state directory and dedicated port:
```sh
pilot="$(mktemp -d /tmp/evidence-pilot.XXXXXXXX)"
ANNOTATION_STATE_DIR="$pilot" ANNOTATION_PORT=5199 bash scripts/run-local.sh
```
In another terminal, from the same project:
```sh
mkdir -p .local/citation-pilot
python3 scripts/load_citation_pilot.py --manifest > .local/citation-pilot/pairs.json
python3 scripts/load_citation_pilot.py --reference-key > .local/citation-pilot/coordinator-key.json
python3 scripts/load_citation_pilot.py --disposable-port 5199 --reviewer r1 --reviewer r2 --reviewer r3 --reviewer r4
python3 scripts/assign_citation_pilot.py .local/citation-pilot/pairs.json .local/citation-pilot/schedule.csv --reviewer r1 --reviewer r2 --reviewer r3 --reviewer r4
```
Each reviewer uses the corresponding batch in the Adjudicator persona and the assigned mode, on the same machine or in a separately prepared local instance. Batches avoid immutable review collisions; they are not a permission boundary. Do not expose the server on a shared network. Close the disposable instance after use. No human timing data has been collected.
