import argparse
import json
from pathlib import Path


ALLOWED = {
    "birth": ["training", "stabilization"],
    "training": ["stabilization", "evolution"],
    "stabilization": ["specialization", "federation", "evolution"],
    "specialization": ["federation", "evolution"],
    "federation": ["evolution", "specialization"],
    "evolution": ["training", "stabilization", "specialization", "federation"],
}


def _load(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Validate lifecycle stage transition legality.")
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--from-stage", required=True)
    parser.add_argument("--to-stage", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    lifecycle_path = repo_root / "lifecycle_state.json"
    if not lifecycle_path.exists():
        print(f"Missing lifecycle_state.json: {lifecycle_path}")
        raise SystemExit(1)

    lifecycle = _load(lifecycle_path)
    current = lifecycle.get("current_stage")
    if current != args.from_stage:
        print(f"Transition mismatch: lifecycle current_stage={current}, expected from-stage={args.from_stage}")
        raise SystemExit(1)

    allowed = ALLOWED.get(args.from_stage, [])
    if args.to_stage not in allowed:
        print(f"Invalid lifecycle transition: {args.from_stage} -> {args.to_stage}")
        raise SystemExit(1)

    print(f"Lifecycle transition valid: {args.from_stage} -> {args.to_stage}")


if __name__ == "__main__":
    main()
