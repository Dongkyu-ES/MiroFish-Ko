"""Hybrid node/edge ranking overlay for parity tests."""

from __future__ import annotations

import re

from .summaries import build_node_summary, summarize_candidate
from .temporal import preserve_temporal_fields


class HybridSearchOverlay:
    def rank(self, query: str, node_candidates: list[dict], edge_candidates: list[dict]) -> dict:
        query_tokens = self._tokenize(query)
        query_text = query.strip().lower()
        ranked_nodes = sorted(
            (self._with_score(candidate, query_tokens, query_text) for candidate in node_candidates),
            key=lambda item: item["_score"],
            reverse=True,
        )
        ranked_edges = sorted(
            (self._with_score(preserve_temporal_fields(candidate), query_tokens, query_text) for candidate in edge_candidates),
            key=lambda item: item["_score"],
            reverse=True,
        )

        for collection in (ranked_nodes, ranked_edges):
            for item in collection:
                item.pop("_score", None)

        return {
            "nodes": ranked_nodes,
            "edges": ranked_edges,
        }

    def _with_score(self, candidate: dict, query_tokens: set[str], query_text: str) -> dict:
        scored = dict(candidate)
        if "fact" not in scored:
            scored["summary"] = build_node_summary(scored)
        searchable_text = summarize_candidate(candidate).lower()
        candidate_tokens = self._tokenize(searchable_text)
        score = len(query_tokens & candidate_tokens)

        if query_text and query_text in searchable_text:
            score += 10

        candidate_name = str(candidate.get("name", "")).lower()
        if query_text and candidate_name == query_text:
            score += 12
        elif query_text and candidate_name and query_text in candidate_name:
            score += 6

        attributes = candidate.get("attributes", {}) or {}
        alias_values = attributes.get("aliases", [])
        if isinstance(alias_values, str):
            alias_values = [alias_values]
        alias_hits = [alias for alias in alias_values if query_text and query_text == str(alias).lower()]
        if alias_hits:
            score += 8

        scored["_score"] = score
        return scored

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"[A-Za-z0-9가-힣]+", text)}
