"""Summary helpers for parity overlays."""

from __future__ import annotations


def summarize_candidate(candidate: dict) -> str:
    return candidate.get("summary") or candidate.get("fact") or candidate.get("name", "")


def build_node_summary(candidate: dict) -> str:
    summary = candidate.get("summary")
    if summary:
        return summary

    name = candidate.get("name", "Unknown")
    labels = ", ".join(candidate.get("labels", []))
    attributes = candidate.get("attributes", {})
    detail = ", ".join(f"{key}: {value}" for key, value in attributes.items() if value)
    parts = [name]
    if labels:
        parts.append(labels)
    if detail:
        parts.append(detail)
    return " | ".join(parts)
