#!/usr/bin/env python3
"""Deep Discovery evaluation for Merlin submodule."""
import subprocess
import sys
from pathlib import Path

def run_script(path, args=None):
    print(f"--- Running {path.name} ---")
    cmd = [sys.executable, str(path)]
    if args: cmd.extend(args)
    subprocess.run(cmd, check=False)

def main():
    root = Path(__file__).resolve().parents[1]
    print(f"🧙 Starting Deep Discovery for Merlin at {root}\n")
    
    scripts = [
        ("Seeding Watchdog", root / "scripts" / "run_merlin_seed_watchdog.py"),
        ("Log Signatures", root / "scripts" / "verify_smoke_log_signatures.py"),
        ("Dependency Audit", root / "scripts" / "generate_dependency_audit_report.py"),
        ("Benchmarking", root / "scripts" / "run_benchmark_command_pack.py")
    ]
    
    for label, path in scripts:
        if path.exists():
            print(f"🔍 Discovery: {label}")
            run_script(path)
            print("")

    return 0

if __name__ == "__main__":
    sys.exit(main())
