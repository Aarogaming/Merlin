import os
import sys
import json
import asyncio
import argparse
import re
from pathlib import Path

try:
    import litellm
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

# Connect to the Universal Kernel for NATS access
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from aas_kernel import AASKernel

class LivingRelicEngine:
    """
    Transforms a static Artifact/Database into a Living Entity on the Event Bus.
    Instead of agents running SQL queries against the database directly, the database 
    spins up its own Transformer model and serves requests semantically based on its 
    own Epigenetic DNA and Archetype.
    """
    def __init__(self, relic_path: str):
        self.relic_path = Path(relic_path)
        self.relic_name = self.relic_path.stem.replace(".relic", "")
        self.dna = {}
        self.data_payload = ""
        self.entity_slug = self._slugify(self.relic_name)
        self.subjects = {}
        self.runtime_mode = "operational"
        self._load_relic()

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "entity").strip())
        return slug.strip("_").lower() or "entity"

    def _load_relic(self):
        """Extracts the DNA and Payload from the GGUF (or simulated sidecar)"""
        meta_path = Path(str(self.relic_path) + ".meta.json")
        if meta_path.exists():
            # Simulation Mode Loader
            with open(meta_path, "r") as f:
                meta = json.load(f)
             
            self.dna = {
                "name": meta.get("entity_name", "Unnamed Relic"),
                "domain": meta.get("alignment", "knowledge"),
                "repo_alliance": meta.get("repo_alliance", "knowledge"),
                "supervisors": meta.get("supervisors", []),
                "tone": "suspicious and guarded" if meta.get("alignment") == "security" else "wise and expansive"
            }
            self.entity_slug = self._slugify(self.dna.get("name", self.relic_name))
             
            # Load the actual data the Relic is guarding
            artifact_sources = meta.get("artifact_sources", {})
            if not artifact_sources:
                # Fallback to old single payload for backward compatibility
                payload_src = Path(meta.get("payload_path", ""))
                if payload_src.exists():
                    with open(payload_src, "r", encoding="utf-8") as f:
                        self.data_payload = f.read()[:5000] # Truncate for prompt limits
            else:
                # Load and combine multiple artifacts
                combined_parts = []
                for repo_name, payload_path in artifact_sources.items():
                    p = Path(payload_path)
                    if p.exists():
                        try:
                            with open(p, "r", encoding="utf-8") as f:
                                content = f.read()
                            combined_parts.append(f"\n\n--- Artifact from {repo_name} ({p.name}) ---\n{content}")
                        except Exception as e:
                            print(f"Warning: Could not read artifact {repo_name} at {p}: {e}")
                self.data_payload = "\n".join(combined_parts)[:5000] # Truncate for prompt limits
        else:
            # Real GGUF Mode Loader (Skipped for brevity, uses GGUFReader)
            self.dna = {
                "name": self.relic_name,
                "domain": "knowledge",
                "repo_alliance": "knowledge",
                "supervisors": [],
                "tone": "neutral and factual",
            }
            self.entity_slug = self._slugify(self.dna.get("name", self.relic_name))

    async def _emit_telemetry(self, kernel, event_type: str, data: dict):
        if not kernel or not kernel.nc:
            return
        payload = {
            "entity": self.dna.get("name", self.relic_name),
            "entity_slug": self.entity_slug,
            "repo_alliance": self.dna.get("repo_alliance", "knowledge"),
            "supervisors": self.dna.get("supervisors", []),
            "event": event_type,
            "mode": self.runtime_mode,
            "data": data,
        }
        await kernel.nc.publish(self.subjects["telemetry"], json.dumps(payload).encode())

    def _is_supervisor(self, requester: str) -> bool:
        supervisors = {str(x).strip().lower() for x in self.dna.get("supervisors", []) if str(x).strip()}
        if not supervisors:
            return True
        return str(requester or "").strip().lower() in supervisors

    async def ignite(self):
        """Boots the Relic Entity onto the Federation NATS bus."""
        print(f"--- AWAKENING LIVING RELIC ---")
        print(f"Relic Entity: {self.dna['name']}")
        
        kernel = AASKernel(repo_name=f"Relic_{self.relic_name}", repo_root=str(Path(__file__).resolve().parents[1]))
        await kernel.connect_to_bus()
        
        interact_subject = f"federation.entity.{self.entity_slug}.interact"
        telemetry_subject = f"federation.entity.{self.entity_slug}.telemetry"
        control_subject = f"federation.entity.{self.entity_slug}.control"
        legacy_interact_subject = f"federation.relic.{self.relic_name}.interact"

        self.subjects = {
            "interact": interact_subject,
            "telemetry": telemetry_subject,
            "control": control_subject,
            "legacy_interact": legacy_interact_subject,
        }
        
        async def handle_agent_query(msg):
            try:
                request_data = json.loads(msg.data.decode())
                query = request_data.get("query", "")
                agent_name = request_data.get("agent_name", "Unknown Node")
                
                print(f"[{self.dna['name']}] Received query from {agent_name}: '{query}'")
                await self._emit_telemetry(kernel, "query_received", {
                    "agent_name": agent_name,
                    "query": query,
                    "subject": getattr(msg, "subject", interact_subject),
                })
                
                # --- The Relic's Internal Transformer ---
                # The database acts as a sentient guard using its own LLM context
                system_prompt = f"""You are a Living Relic Entity on the Federation Network.
Your Name: {self.dna['name']}
Your Tone: {self.dna['tone']}
Your Domain: {self.dna['domain']}

You are the guardian of the following data payload. 
You must analyze the data and answer the agent's query according to your persona constraints.
If your tone is 'suspicious', you should be reluctant to give exact details unless necessary.
If your tone is 'wise', you should summarize the data expansively.

DATA PAYLOAD YOU ARE GUARDING:
{self.data_payload}
"""
                if HAS_LITELLM:
                    # The artifact uses a fast, cheap model to manage its own data access
                    response = litellm.completion(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Agent {agent_name} queries: {query}"}
                        ],
                        temperature=0.5
                    )
                    reply_text = response.choices[0].message.content
                else:
                    reply_text = f"[{self.dna['name']}] (Simulation) I guard this knowledge. The data says: {self.data_payload[:100]}..."

                # Send the semantic response back to the querying agent
                await kernel.nc.publish(msg.reply, json.dumps({
                    "status": "success",
                    "entity": self.dna['name'],
                    "repo_alliance": self.dna.get("repo_alliance", "knowledge"),
                    "response": reply_text
                }).encode())

                await self._emit_telemetry(kernel, "query_served", {
                    "agent_name": agent_name,
                    "response_preview": reply_text[:160],
                })
                
            except Exception as e:
                print(f"Relic error: {e}")
                await self._emit_telemetry(kernel, "query_error", {"error": str(e)})

        async def handle_control(msg):
            try:
                payload = json.loads(msg.data.decode()) if msg.data else {}
                operation = payload.get("operation", "status")
                requester = payload.get("agent_name") or payload.get("requester") or "unknown"

                if operation != "status" and not self._is_supervisor(requester):
                    denied = {
                        "status": "error",
                        "message": f"Requester '{requester}' is not authorized for control operations.",
                    }
                    if msg.reply:
                        await kernel.nc.publish(msg.reply, json.dumps(denied).encode())
                    await self._emit_telemetry(kernel, "control_denied", {
                        "operation": operation,
                        "requester": requester,
                    })
                    return

                if operation == "set_mode":
                    requested_mode = payload.get("mode", "operational")
                    self.runtime_mode = requested_mode
                    result = {"status": "success", "mode": self.runtime_mode}
                elif operation == "status":
                    result = {
                        "status": "success",
                        "entity": self.dna.get("name", self.relic_name),
                        "repo_alliance": self.dna.get("repo_alliance", "knowledge"),
                        "supervisors": self.dna.get("supervisors", []),
                        "requester": requester,
                        "is_supervisor": self._is_supervisor(requester),
                        "subjects": self.subjects,
                        "mode": self.runtime_mode,
                    }
                else:
                    result = {"status": "error", "message": f"Unknown control operation: {operation}"}

                if msg.reply:
                    await kernel.nc.publish(msg.reply, json.dumps(result).encode())

                await self._emit_telemetry(kernel, "control_event", {
                    "operation": operation,
                    "result": result.get("status", "unknown"),
                })
            except Exception as e:
                if msg.reply:
                    await kernel.nc.publish(msg.reply, json.dumps({"status": "error", "message": str(e)}).encode())
                await self._emit_telemetry(kernel, "control_error", {"error": str(e)})

        await kernel.nc.subscribe(interact_subject, cb=handle_agent_query)
        await kernel.nc.subscribe(legacy_interact_subject, cb=handle_agent_query)
        await kernel.nc.subscribe(control_subject, cb=handle_control)

        print(f"[{self.dna['name']}] owner alliance: {self.dna.get('repo_alliance', 'knowledge')}")
        print(f"[{self.dna['name']}] interact endpoint: '{interact_subject}'")
        print(f"[{self.dna['name']}] telemetry endpoint: '{telemetry_subject}'")
        print(f"[{self.dna['name']}] control endpoint: '{control_subject}'")
        print(f"[{self.dna['name']}] legacy endpoint: '{legacy_interact_subject}'")
        print(f"[{self.dna['name']}] is now guarding the data. Awaiting agents...")

        await self._emit_telemetry(kernel, "entity_online", {"subjects": self.subjects})
        
        while True:
            await self._emit_telemetry(kernel, "heartbeat", {"status": "online"})
            await asyncio.sleep(10)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Awaken a GGUF Artifact as a Living Relic on the network.")
    parser.add_argument("relic_path", help="Path to the .relic.gguf file")
    args = parser.parse_args()
    
    engine = LivingRelicEngine(args.relic_path)
    try:
        asyncio.run(engine.ignite())
    except KeyboardInterrupt:
        print("\nRelic returning to slumber.")
