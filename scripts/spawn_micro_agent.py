#!/usr/bin/env python3
"""
Spawn a micro-agent (Huginn/Muninn style) that watches a target repo and reports to a parent Relic.

Unlike full specialists, micro-agents are lightweight watchers that:
- Run with minimal memory footprint
- Subscribe to specific NATS subjects
- Report findings back to a parent entity
- Can be auto-restarted on failure
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

WORKSPACE_ROOT = os.environ.get("AAS_WORKSPACE_ROOT", "D:/")
NATS_URL = os.environ.get("AAS_NATS_URL", "nats://localhost:4222")

try:
    from nats.aio.client import Client as NATS
except ImportError:
    NATS = None


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Spawn a micro-watcher agent.")
    parser.add_argument("micro_name", help="Name: Huginn, Muninn, etc.")
    parser.add_argument("target_repo", help="Repo to watch (e.g., Library, Merlin)")
    parser.add_argument("parent_relic", help="Parent relic to report to (e.g., Draupnir)")
    parser.add_argument("--watch-subject", default=None, help="NATS subject to subscribe to")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between polls")
    parser.add_argument("--report-subject", default=None, help="Subject to publish reports to")
    return parser.parse_args()


async def get_runtime_state(target_repo_path: Path) -> dict:
    """Collect lightweight runtime state from target repo."""
    artifacts = target_repo_path / "artifacts"
    state = {"timestamp": datetime.utcnow().isoformat(), "repo": target_repo_path.name}
    
    if artifacts.exists():
        # Quick snapshot of runtime.json if exists
        runtime = artifacts / "runtime.json"
        if runtime.exists():
            try:
                with open(runtime, "r") as f:
                    state["runtime"] = json.load(f)
            except Exception:
                pass
                
        # Count active processes from .pid files
        pid_files = list(artifacts.glob("*.pid"))
        state["active_processes"] = len(pid_files)
        
    return state


async def main():
    args = parse_args()
    
    if not NATS:
        print("Error: nats-py required for micro-agent communication")
        return
        
    workspace_root = Path(WORKSPACE_ROOT)
    target_repo_path = workspace_root / args.target_repo
    report_subject = args.report_subject or f"federation.entity.{args.parent_relic.lower()}.telemetry"
    watch_subject = args.watch_subject or f"federation.{args.target_repo.lower()}.events"
    
    print(f"=== Spawning micro-agent: {args.micro_name} ===")
    print(f"Target: {args.target_repo}")
    print(f"Parent: {args.parent_relic}")
    print(f"Watch subject: {watch_subject}")
    print(f"Report subject: {report_subject}")
    
    nc = await NATS().connect(NATS_URL)
    
    async def watch_loop():
        print(f"[{args.micro_name}] Watching {args.target_repo}...")
        while True:
            try:
                state = await get_runtime_state(target_repo_path)
                report = {
                    "micro_agent": args.micro_name,
                    "target": args.target_repo,
                    "parent": args.parent_relic,
                    "state": state,
                }
                await nc.publish(report_subject, json.dumps(report).encode())
                print(f"[{args.micro_name}] Reported state at {state['timestamp']}")
            except Exception as e:
                print(f"[{args.micro_name}] Error: {e}")
                
            await asyncio.sleep(args.poll_interval)
    
    # Subscribe to watch subject for external triggers
    async def external_trigger(msg):
        try:
            payload = json.loads(msg.data.decode())
            print(f"[{args.micro_name}] Received external: {payload}")
        except Exception:
            pass
    
    await nc.subscribe(watch_subject, cb=external_trigger)
    
    try:
        await watch_loop()
    finally:
        await nc.close()


if __name__ == "__main__":
    if NATS:
        asyncio.run(main())
    else:
        print("nats-py not installed. Micro-agent requires nats-py.")