import subprocess
import sys
import os
import time
import argparse
from merlin_doctor import run_doctor


def launch_merlin(index: bool = False):
    print("=" * 40)
    print("Merlin Merlin - Unified Launcher")
    print("=" * 40)

    # 1. Run Doctor
    print("Step 1: Running environment check...")
    # We'll run it in-process for simplicity
    # In a real app, we might want to capture output
    run_doctor()

    # 2. Optional: Run Indexer
    if index:
        print("\nStep 2: Running Resource Indexer...")
        try:
            subprocess.run([sys.executable, "merlin_resource_indexer.py"], check=True)
            print("Indexing complete.")
        except subprocess.CalledProcessError:
            print("Indexing failed. Continuing anyway...")

    # 3. Start API Server
    print("\nStep 3: Starting Merlin API Server...")
    try:
        # Use uvicorn directly if possible, or subprocess
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "merlin_api_server:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
        print(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nMerlin shutting down...")
    except Exception as e:
        print(f"Failed to start API server: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merlin Merlin Launcher")
    parser.add_argument(
        "--index", action="store_true", help="Run resource indexer before starting"
    )
    args = parser.parse_args()

    launch_merlin(index=args.index)
