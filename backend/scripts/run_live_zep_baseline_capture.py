from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.parity_engine.live_measurement import run_live_zep_baseline_capture


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live Zep baseline capture with API call budget")
    parser.add_argument(
        "--manifest",
        default="backend/tests/parity_engine/fixtures/corpus_manifest.json",
    )
    parser.add_argument(
        "--fixtures-root",
        default="backend/tests/parity_engine/fixtures",
    )
    parser.add_argument(
        "--output-root",
        default=f"artifacts/parity/live-zep-{Path('.').resolve().name}",
    )
    parser.add_argument("--max-calls", type=int, default=100)
    args = parser.parse_args()

    summary = run_live_zep_baseline_capture(
        manifest_path=args.manifest,
        fixtures_root=args.fixtures_root,
        output_root=args.output_root,
        max_calls=args.max_calls,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
