from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.parity_engine.local_measurement import run_local_candidate_capture, running_local_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture local Graphiti candidate artifacts")
    parser.add_argument("--manifest", default="backend/tests/parity_engine/fixtures/corpus_manifest.json")
    parser.add_argument("--fixtures-root", default="backend/tests/parity_engine/fixtures")
    parser.add_argument("--output-root", default="artifacts/parity/local-candidate")
    parser.add_argument("--db-path", default="tmp/local-candidate-graphiti.kuzu")
    parser.add_argument("--mode", choices=["inline", "provider"], default="inline")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with running_local_engine(db_path=db_path, mode=args.mode) as _:
        summary = run_local_candidate_capture(
            manifest_path=args.manifest,
            fixtures_root=args.fixtures_root,
            output_root=args.output_root,
            db_path=db_path,
            mode=args.mode,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
