import os
import subprocess
import sys


LIMIT_BYTES = 100 * 1024 * 1024  # 100MB


def _run_git(args):
    return subprocess.check_output(["git", *args], text=False)


def _repo_root():
    return (
        _run_git(["rev-parse", "--show-toplevel"])
        .decode("utf-8", errors="replace")
        .strip()
    )


def _staged_paths():
    out = _run_git(["diff", "--cached", "--name-only", "-z"])
    if not out:
        return []
    parts = out.split(b"\x00")
    return [p.decode("utf-8", errors="replace") for p in parts if p]


def main():
    try:
        root = _repo_root()
    except Exception:
        # Don't block commits if git isn't available.
        return 0

    oversized = []
    for rel in _staged_paths():
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > LIMIT_BYTES:
            oversized.append((rel, size))

    if not oversized:
        return 0

    sys.stderr.write("Error: staged files exceed 100MB limit:\n")
    for rel, size in sorted(oversized, key=lambda x: x[1], reverse=True):
        sys.stderr.write(f"  - {rel} ({size} bytes)\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
