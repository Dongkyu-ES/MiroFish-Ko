"""Metric helpers for parity evaluation."""

from __future__ import annotations

import math
from collections.abc import Iterable


def overlap_at_k(left: list[str], right: list[str], k: int) -> float:
    """Return top-k overlap ratio using the candidate slice length as denominator."""

    if k <= 0:
        return 0.0

    left_top_k = left[:k]
    right_top_k = right[:k]
    if not left_top_k or not right_top_k:
        return 0.0

    overlap = len(set(left_top_k).intersection(right_top_k))
    denominator = min(k, len(left_top_k), len(right_top_k))
    return overlap / denominator if denominator else 0.0


def relative_delta(baseline: float | int, candidate: float | int) -> float:
    """Return the absolute relative difference between baseline and candidate."""

    baseline_value = float(baseline)
    candidate_value = float(candidate)

    if baseline_value == 0:
        return 0.0 if candidate_value == 0 else math.inf

    return abs(candidate_value - baseline_value) / abs(baseline_value)


def ndcg_at_k(reference: list[str], candidate: list[str], k: int) -> float:
    """Binary-relevance nDCG with the reference ranking as ground truth."""

    if k <= 0:
        return 0.0

    reference_top_k = reference[:k]
    candidate_top_k = candidate[:k]
    if not reference_top_k or not candidate_top_k:
        return 0.0

    relevant = set(reference_top_k)
    dcg = _dcg(1.0 if item in relevant else 0.0 for item in candidate_top_k)
    ideal = _dcg(1.0 for _ in reference_top_k)
    return dcg / ideal if ideal else 0.0


def f1_from_sets(reference: Iterable[str], candidate: Iterable[str]) -> float:
    """Return F1 score for two label/id sets."""

    reference_set = set(reference)
    candidate_set = set(candidate)
    if not reference_set and not candidate_set:
        return 1.0
    if not reference_set or not candidate_set:
        return 0.0

    intersection = len(reference_set & candidate_set)
    precision = intersection / len(candidate_set)
    recall = intersection / len(reference_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def attribute_fill_rate(records: list[dict], fields: Iterable[str]) -> float:
    """Measure how often the listed fields are populated in the given records."""

    field_list = list(fields)
    if not records or not field_list:
        return 0.0

    filled = 0
    total = len(records) * len(field_list)
    for record in records:
        for field in field_list:
            value = record.get(field)
            if value not in (None, "", [], {}):
                filled += 1
    return filled / total if total else 0.0


def _dcg(relevances: Iterable[float]) -> float:
    score = 0.0
    for index, relevance in enumerate(relevances, start=1):
        score += relevance / math.log2(index + 1)
    return score
