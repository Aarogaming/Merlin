import argparse
import asyncio
import json

try:
    from nats.aio.client import Client as NATS
    HAS_NATS = True
except ImportError:
    HAS_NATS = False


def _match_filters(payload: dict, trace_id: str | None, requester: str | None, mode: str | None) -> bool:
    if trace_id and str(payload.get("trace_id", "")) != trace_id:
        return False
    if requester and str(payload.get("requester", "")).lower() != requester.lower():
        return False
    if mode and str(payload.get("execution_mode", "")).lower() != mode.lower():
        return False
    return True


async def run(trace_id: str | None, requester: str | None, mode: str | None, pretty: bool):
    if not HAS_NATS:
        print("Error: nats-py is required. Install with: pip install nats-py")
        return

    nc = NATS()
    await nc.connect("nats://localhost:4222", connect_timeout=5)

    print("Watching federation.triage.trace")
    if trace_id:
        print(f"- filter trace_id: {trace_id}")
    if requester:
        print(f"- filter requester: {requester}")
    if mode:
        print(f"- filter mode: {mode}")

    async def cb(msg):
        try:
            payload = json.loads(msg.data.decode())
        except Exception:
            payload = {"raw": msg.data.decode(errors="replace")}

        if not isinstance(payload, dict):
            return
        if not _match_filters(payload, trace_id, requester, mode):
            return

        if pretty:
            print(json.dumps(payload, indent=2))
        else:
            compact = {
                "trace_id": payload.get("trace_id"),
                "requester": payload.get("requester"),
                "execution_mode": payload.get("execution_mode"),
                "primary_repo": payload.get("primary_repo"),
                "supporting_repos": payload.get("supporting_repos", []),
                "advanced_dispatch_status": payload.get("advanced_dispatch_status"),
                "timestamp": payload.get("timestamp"),
            }
            print(json.dumps(compact))

    await nc.subscribe("federation.triage.trace", cb=cb)

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await nc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch triage delegation traces from Agent-Zero.")
    parser.add_argument("--trace-id", help="Only show traces for this trace id")
    parser.add_argument("--requester", help="Only show traces for this requester")
    parser.add_argument("--mode", choices=["single", "sequential", "parallel", "sequential_parallel_spectrum"], help="Only show traces for this execution mode")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print full JSON payloads")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.trace_id, args.requester, args.mode, args.pretty))
    except KeyboardInterrupt:
        pass
