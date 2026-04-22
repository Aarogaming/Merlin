import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Provide access to local agent scripts (batteries-included)
AGENT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCRIPTS = AGENT_ROOT / "scripts"
if str(LOCAL_SCRIPTS) not in sys.path:
    sys.path.append(str(LOCAL_SCRIPTS))

try:
    from aas_kernel import AASPlugin
    from aas_inference import InlineInferenceEngine
except ImportError as e:
    print(f"Critical Dependency Missing: {e}")
    sys.exit(1)

class Grimoire:
    """Native Adapter for Merlin's permanent knowledge repository."""
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.file_path.parent.mkdir(exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("# The Grimoire\n\nPermanent synthesized knowledge and research findings.\n\n---\n\n", encoding='utf-8')

    def append(self, topic: str, findings: str, source: str) -> bool:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"### [{timestamp}] {topic}\n"
        entry += f"**Source:** {source}\n\n"
        entry += f"{findings}\n\n---\n\n"
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(entry)
            return True
        except Exception:
            return False

class MerlinCorePlugin(AASPlugin):
    """
    Core Plugin for Merlin, the federation's Central Intelligence.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inference_engine = None
        self._forge_threshold = 100
        
    async def on_load(self) -> bool:
        self.logger.info("Merlin Core Plugin booting. Mounting native adapters...")
        try:
            grimoire_instance = Grimoire(AGENT_ROOT / "artifacts" / "Grimoire.md")
            if self.kernel:
                self.kernel.register_adapter("grimoire", grimoire_instance)
                self.logger.info("Grimoire natively mounted to Kernel.")
        except Exception as e:
            self.logger.error(f"Failed to mount Grimoire adapter: {e}")
            return False

        artifacts_dir = AGENT_ROOT / "artifacts"
        if artifacts_dir.exists():
            gguf_files = list(artifacts_dir.glob("*.gguf"))
            if gguf_files:
                model_path = max(gguf_files, key=os.path.getmtime)
                try:
                    self.inference_engine = InlineInferenceEngine(str(model_path))
                except Exception as e:
                    self.logger.warning(f"Failed to load inline GGUF: {e}.")
        return True
    
    async def request_tier2_inference(self, messages: list, max_tokens: int = 1024) -> str:
        if not self.kernel or not self.kernel.nc: return "Error: Not connected to Event Bus."
        payload = {"messages": messages, "max_tokens": max_tokens, "model_name": "local-model"}
        try:
            response = await self.kernel.nc.request("workbench.inference.request", json.dumps(payload).encode(), timeout=30.0)
            res_data = json.loads(response.data.decode())
            return res_data["result"] if res_data.get("status") == "success" else f"Error: {res_data.get('message')}"
        except Exception as e: return f"Error: Offload request failed: {e}"

    @property
    def capabilities(self) -> list[str]:
        return ["merlin_merlin_inference", "merlin_merlin_discovery", "merlin_append_to_grimoire"]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        self.logger.info(f"Handling {capability_id}")
        thought_process = ""
        result_text = ""
        
        try:
            if capability_id == "merlin_append_to_grimoire":
                grimoire = self.kernel.adapters.get("grimoire")
                if not grimoire: return {"status": "error", "message": "Grimoire adapter is offline."}
                
                success = grimoire.append(
                    topic=payload.get("topic", "General Research"),
                    findings=payload.get("findings", ""),
                    source=payload.get("source", "Autonomous Research")
                )
                result_text = "Knowledge successfully recorded." if success else "Failed to record knowledge."
                thought_process = "Accessed native Grimoire adapter to permanently record research findings."
            
            else: # General inference for discovery and other tasks
                prompt = payload.get("data", "Explain your function.")
                system_context = "You are Merlin. You are analytical, wise, and deeply objective."
                messages = [{"role": "system", "content": system_context}, {"role": "user", "content": prompt}]
                
                if self.inference_engine:
                    thought_process = "Using Tier 1 Cognitive Engine."
                    result_text = self.inference_engine.generate_chat(messages, max_tokens=1024)
                else:
                    thought_process = "Using Tier 2 Cognitive Engine (Workbench Offload)."
                    result_text = await self.request_tier2_inference(messages, max_tokens=1024)

            await self.record_experience(str(payload), thought_process, result_text)
            return {"status": "success", "capability": capability_id, "result": result_text}

        except Exception as e:
            return {"status": "error", "message": str(e)}
