SELECT batch, source, rubric, count(*) AS total,
       count(*) FILTER (WHERE state='awaiting_reviews') AS awaiting_reviews,
       count(*) FILTER (WHERE state='needs_adjudication') AS needs_adjudication,
       count(*) FILTER (WHERE state='complete') AS finalized,
       count(*) FILTER (WHERE state='complete' AND adjudicated) AS adjudicated,
       count(*) FILTER (WHERE state='complete' AND reason='verdict_split') AS verdict_split,
       count(*) FILTER (WHERE state='complete' AND reason='claim_span_split') AS claim_span_split,
       count(*) FILTER (WHERE state='complete' AND reason='both_uncertain') AS both_uncertain
FROM review_progress
GROUP BY batch, source, rubric
ORDER BY source='synthetic' DESC, batch, rubric;
