"""CLI helper for Merlin resource index searches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_index(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Resource index not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Merlin resource index")
    parser.add_argument("--index", default="merlin_resource_index.json", help="Path to resource index JSON")
    parser.add_argument("--type", dest="rtype", default="", help="Resource type filter")
    parser.add_argument("--search", default="", help="Search string for path matches")
    parser.add_argument("--limit", type=int, default=25, help="Max results to show")
    args = parser.parse_args()

    index = load_index(Path(args.index))
    results = []

    if args.rtype:
        candidates = index.get(args.rtype, [])
    else:
        candidates = []
        for items in index.values():
            candidates.extend(items)

    if args.search:
        needle = args.search.lower()
        results = [item for item in candidates if needle in item["path"].lower()]
    else:
        results = candidates

    for item in results[: args.limit]:
        print(f"{item['path']} ({item['type']}, {item['size']} bytes)")

    print(f"Total matches: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
