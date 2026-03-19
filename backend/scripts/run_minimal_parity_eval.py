from __future__ import annotations

import argparse
import json

from backend.app.parity_engine.minimal_eval import run_minimal_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight parity evaluation")
    parser.add_argument("--baseline-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--output", default="artifacts/parity/minimal_eval_summary.json")
    args = parser.parse_args()

    summary = run_minimal_evaluation(
        baseline_root=args.baseline_root,
        candidate_root=args.candidate_root,
        output_path=args.output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
