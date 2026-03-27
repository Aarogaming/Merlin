#!/usr/bin/env python3
"""High-level evaluation for Merlin submodule."""
import subprocess
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[1]
    print(f"🧙 Evaluating Merlin Intelligence at {root}")
    
    # 1. Maturity Promotion check
    script = root / "scripts" / "evaluate_maturity_promotion.py"
    if script.exists():
        print("Evaluating module maturity...")
        subprocess.run([sys.executable, str(script)], check=False)
    
    # 2. Memory integrity
    script = root / "scripts" / "check_vector_memory_integrity.py"
    if script.exists():
        print("Checking vector memory integrity...")
        subprocess.run([sys.executable, str(script)], check=False)

    return 0

if __name__ == "__main__":
    sys.exit(main())
