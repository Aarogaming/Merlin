from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from merlin_vector_memory import MerlinVectorMemory


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Merlin vector memory storage integrity."
    )
    parser.add_argument(
        "--collection",
        default="merlin_memory",
        help="Collection name (maps to <collection>.json by default).",
    )
    parser.add_argument(
        "--storage-file",
        default=None,
        help="Explicit JSON file path to validate instead of <collection>.json.",
    )
    parser.add_argument(
        "--max-duplicates",
        type=int,
        default=0,
        help="Maximum allowed duplicate entries before failing.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Apply deduplication compaction before integrity validation.",
    )
    parser.add_argument(
        "--trim-to",
        type=int,
        default=None,
        help="Optional max entries when --compact is enabled.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    memory = MerlinVectorMemory(collection_name=args.collection)
    if args.storage_file:
        memory.storage_file = str(Path(args.storage_file))
        memory.memories = memory._load_memories()

    if args.compact:
        memory.compact_memories(max_entries=args.trim_to, deduplicate=True)

    report = memory.integrity_report()
    print(json.dumps(report, indent=2))

    if report["invalid_entries"] > 0:
        return 1
    if report["duplicate_entries"] > max(0, int(args.max_duplicates)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
