"""Explainable review ordering; never changes whether a task needs adjudication."""
from fractions import Fraction


def merged_intervals(spans):
    intervals = sorted((s["start"], s["end"]) for s in spans if s["target"] == "answer")
    result = []
    for start, end in intervals:
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def answer_iou(a, b):
    left, right = merged_intervals(a), merged_intervals(b)
    intersection = i = j = 0
    while i < len(left) and j < len(right):
        a_start, a_end = left[i]
        b_start, b_end = right[j]
        intersection += max(0, min(a_end,b_end)-max(a_start,b_start))
        if a_end <= b_end:
            i += 1
        if b_end <= a_end:
            j += 1
    union = sum(end-start for start,end in left+right)-intersection
    return Fraction(intersection, union) if union else None


def ordering(row):
    if row["state"] != "needs_adjudication":
        return 4, 0
    if row["reason"] == "verdict_split":
        return 0, 0
    if row["reason"] == "claim_span_split":
        overlap = row["overlap_exact"]
        if overlap == 0:
            return 1, 0
        return 3, overlap if overlap is not None else 1
    return 2, 0  # Two uncertain reviews still need a human decision.
