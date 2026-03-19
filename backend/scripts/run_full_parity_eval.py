from __future__ import annotations

import argparse
import json

from backend.app.parity_engine.full_eval import run_full_parity_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full parity scorecard evaluation")
    parser.add_argument("--baseline-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--verification-manifest")
    args = parser.parse_args()

    summary = run_full_parity_evaluation(
        baseline_root=args.baseline_root,
        candidate_root=args.candidate_root,
        output_root=args.output_root,
        verification_manifest_path=args.verification_manifest,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
