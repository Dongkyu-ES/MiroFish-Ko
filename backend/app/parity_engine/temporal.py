"""Temporal field helpers for parity overlays."""

from __future__ import annotations


TEMPORAL_FIELDS = ("created_at", "valid_at", "invalid_at", "expired_at")


def preserve_temporal_fields(record: dict) -> dict:
    preserved = dict(record)
    for field in TEMPORAL_FIELDS:
        preserved.setdefault(field, None)
    return preserved


class TemporalEdgeLifecycleOverlay:
    def supersede(
        self,
        previous_edge: dict,
        replacement_edge: dict,
        invalidated_at: str,
    ) -> tuple[dict, dict]:
        previous = preserve_temporal_fields(previous_edge)
        current = preserve_temporal_fields(replacement_edge)
        previous["invalid_at"] = invalidated_at
        previous["expired_at"] = invalidated_at
        current["valid_at"] = current.get("valid_at") or invalidated_at
        return previous, current
