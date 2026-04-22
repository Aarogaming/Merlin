import json
import argparse
import asyncio

try:
    from nats.aio.client import Client as NATS
    HAS_NATS = True
except ImportError:
    HAS_NATS = False


def _slugify(value: str) -> str:
    import re
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "entity").strip())
    return slug.strip("_").lower() or "entity"


async def run(entity_name: str, requester: str, query: str, watch_seconds: int):
    if not HAS_NATS:
        print("Error: nats-py is required. Install with: pip install nats-py")
        return

    slug = _slugify(entity_name)
    interact_subject = f"federation.entity.{slug}.interact"
    control_subject = f"federation.entity.{slug}.control"
    telemetry_subject = f"federation.entity.{slug}.telemetry"

    nc = NATS()
    await nc.connect("nats://localhost:4222", connect_timeout=5)

    print(f"Entity Probe connected for '{entity_name}' ({slug})")
    print(f"Interact:  {interact_subject}")
    print(f"Control:   {control_subject}")
    print(f"Telemetry: {telemetry_subject}")

    async def telemetry_cb(msg):
        try:
            data = json.loads(msg.data.decode())
        except Exception:
            data = {"raw": msg.data.decode(errors="replace")}
        print(f"[telemetry] {json.dumps(data)}")

    await nc.subscribe(telemetry_subject, cb=telemetry_cb)

    status_payload = {"operation": "status", "requester": requester}
    status_msg = await nc.request(control_subject, json.dumps(status_payload).encode(), timeout=10.0)
    print(f"[control:status] {status_msg.data.decode()}")

    query_payload = {"agent_name": requester, "query": query}
    query_msg = await nc.request(interact_subject, json.dumps(query_payload).encode(), timeout=20.0)
    print(f"[interact] {query_msg.data.decode()}")

    if watch_seconds > 0:
        print(f"Watching telemetry for {watch_seconds}s...")
        await asyncio.sleep(watch_seconds)

    await nc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe a Living Entity interact/control/telemetry channels.")
    parser.add_argument("entity_name", help="Entity name, e.g. Omni")
    parser.add_argument("--requester", default="Supervisor", help="Requester identity for control and query events")
    parser.add_argument("--query", default="Provide current status.", help="Query to send to the entity interact endpoint")
    parser.add_argument("--watch", type=int, default=5, help="Seconds to stream telemetry before exit")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.entity_name, args.requester, args.query, args.watch))
    except KeyboardInterrupt:
        pass
