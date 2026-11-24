CREATE TABLE IF NOT EXISTS task (
 id text PRIMARY KEY,
 batch text NOT NULL,
 source text NOT NULL,
 question text NOT NULL,
 passages text NOT NULL,
 answer text NOT NULL,
 rubric text NOT NULL DEFAULT 'grounding-v1'
);
CREATE TABLE IF NOT EXISTS reference_label (
 task_id text PRIMARY KEY REFERENCES task(id),
 tags jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS review (
 task_id text REFERENCES task(id),
 actor text NOT NULL CHECK (actor IN ('reviewer-a','reviewer-b','adjudicator')),
 verdict text NOT NULL CHECK (verdict IN ('supported','unsupported','uncertain')),
 rationale text NOT NULL,
 spans jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (task_id, actor)
);

ALTER TABLE task ADD COLUMN IF NOT EXISTS external_id text;

-- The queue, task transitions, export, and batch metrics share these rules.
CREATE OR REPLACE VIEW review_progress AS
WITH pairs AS (
 SELECT t.id,t.batch,t.source,t.rubric,
        j.actor IS NOT NULL AS adjudicated,
        CASE
          WHEN a.actor IS NULL OR b.actor IS NULL THEN 'awaiting_pair'
          WHEN a.verdict <> b.verdict THEN 'verdict_split'
          WHEN a.verdict = 'uncertain' THEN 'both_uncertain'
          WHEN a.verdict = 'unsupported' AND
            jsonb_path_query_array(a.spans, '$[*] ? (@.target == "answer")') <>
            jsonb_path_query_array(b.spans, '$[*] ? (@.target == "answer")') THEN 'claim_span_split'
          ELSE 'consensus'
        END AS reason
 FROM task t
 LEFT JOIN review a ON a.task_id=t.id AND a.actor='reviewer-a'
 LEFT JOIN review b ON b.task_id=t.id AND b.actor='reviewer-b'
 LEFT JOIN review j ON j.task_id=t.id AND j.actor='adjudicator'
)
SELECT id,batch,source,rubric,reason,adjudicated,
       CASE WHEN reason='awaiting_pair' THEN 'awaiting_reviews'
            WHEN reason='consensus' OR adjudicated THEN 'complete'
            ELSE 'needs_adjudication' END AS state
FROM pairs;
