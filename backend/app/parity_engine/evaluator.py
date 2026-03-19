"""Downstream parity scoring helpers."""

from __future__ import annotations

import json


class DownstreamParityEvaluator:
    def compare(
        self,
        zep_profile: dict,
        local_profile: dict,
        zep_report: dict,
        local_report: dict,
    ) -> dict[str, float]:
        return {
            "profile_score": self.score_profile(zep_profile, local_profile),
            "report_score": self.score_report_tools(zep_report, local_report),
        }

    def score_profile(self, zep_profile: dict, local_profile: dict) -> float:
        return self._exact_or_overlap_score(zep_profile, local_profile)

    def compare_profile_outputs(self, zep_profile: dict, local_profile: dict) -> float:
        return self.score_profile(zep_profile, local_profile)

    def score_report_tools(self, zep_report: dict, local_report: dict) -> float:
        return self._exact_or_overlap_score(zep_report, local_report)

    def compare_report_outputs(self, zep_report: dict, local_report: dict) -> float:
        return self.score_report_tools(zep_report, local_report)

    def score_simulation_prepare(self, zep_prepare: dict, local_prepare: dict) -> float:
        if not zep_prepare.get("success") or not local_prepare.get("success"):
            return 0.0
        zep_files = zep_prepare.get("files", zep_prepare.get("artifacts", []))
        local_files = local_prepare.get("files", local_prepare.get("artifacts", []))
        return 1.0 if zep_files == local_files else 0.0

    def compare_simulation_prepare(self, zep_prepare: dict, local_prepare: dict) -> float:
        return self.score_simulation_prepare(zep_prepare, local_prepare)

    def score_simulation_run(self, zep_run: dict, local_run: dict) -> float:
        return 1.0 if zep_run.get("statuses", []) == local_run.get("statuses", []) else 0.0

    def compare_simulation_run(self, zep_run: dict, local_run: dict) -> float:
        return self.score_simulation_run(zep_run, local_run)

    def score_multilingual_flow(self, flows: dict[str, dict]) -> float:
        required = ("ko", "en")
        return 1.0 if all(flows.get(language, {}).get("success") for language in required) else 0.0

    def compare_multilingual_flow(self, zep_flow: dict[str, dict], local_flow: dict[str, dict]) -> float:
        merged = {
            language: {
                "success": bool(zep_flow.get(language, {}).get("success"))
                and bool(local_flow.get(language, {}).get("success"))
            }
            for language in {"ko", "en"}
        }
        return self.score_multilingual_flow(merged)

    def _exact_or_overlap_score(self, left: dict, right: dict) -> float:
        if left == right:
            return 1.0

        left_tokens = self._tokenize(left)
        right_tokens = self._tokenize(right)
        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0

        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union if union else 0.0

    def _tokenize(self, payload: dict) -> set[str]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return {token for token in serialized.replace('"', " ").replace(",", " ").split() if token}
