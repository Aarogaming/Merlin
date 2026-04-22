import argparse
from pathlib import Path

try:
    from llama_cpp import Llama
    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False

# We reuse the skill distiller logic we built earlier
import sys
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from skill_distiller import SkillDistiller, AAS_PLUGIN_TEMPLATE

class LocalGGUFDistiller(SkillDistiller):
    """
    Runs a massive local LLM (GGUF) headlessly to batch-extract skills 
    and reflexes into native Python files.
    This allows AAS to siphon capabilities from models without needing
    internet access or expensive API keys.
    """
    
    def __init__(self, model_path: str, n_ctx=4096):
        if not HAS_LLAMA:
            print("Error: llama-cpp-python is required for local distillation.")
            return
            
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            print(f"Error: GGUF model not found at {model_path}")
            return
            
        print(f"--- Local Offline Distiller ---")
        print(f"Loading heavy local GGUF into memory: {self.model_path.name}")
        self.llm = Llama(
            model_path=str(self.model_path), 
            n_ctx=n_ctx,
            n_gpu_layers=-1, # Auto-detect GPU
            verbose=False
        )
        print("Model loaded successfully. Ready to distill.")

    def distill(self, request: str, domain: str, skill_name: str):
        if not hasattr(self, 'llm'):
            return

        domain_lower = domain.lower()
        domain_cap = domain.capitalize()
        class_name = "".join([word.capitalize() for word in skill_name.split("_")])
        
        system_prompt = (
            f"You are the AAS Skill Distiller. You extract your vast trained knowledge into "
            f"tiny, native Python plugins.\n"
            f"Write a Python class using this exact template:\n\n{AAS_PLUGIN_TEMPLATE}\n\n"
            f"Rules:\n"
            f"1. Replace the template placeholders with the requested logic.\n"
            f"2. DO NOT use heavy external frameworks. Use standard python libraries.\n"
            f"3. Return ONLY the raw python code inside a ```python block. Do not explain."
        )

        user_prompt = f"Write the logic for: {request}\nCapability Name: {skill_name}\nClass Name: {class_name}"

        print(f"Distilling '{skill_name}' locally... (This may take a moment)")
        
        # Local Inference via llama.cpp
        try:
            response = self.llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=2048
            )
            
            raw_response = response["choices"][0]["message"]["content"]
            python_code = self.extract_python_code(raw_response)
            
            SKILLS_DIR = Path(__file__).resolve().parents[1] / "plugins" / "skills"
            out_path = SKILLS_DIR / f"skill_{skill_name.lower()}.py"
            SKILLS_DIR.mkdir(parents=True, exist_ok=True)
            
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(python_code)
                
            print(f"[Success] Skill distilled locally and saved to {out_path.name}")
            
        except Exception as e:
            print(f"Local distillation failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distill skills locally from a GGUF file.")
    parser.add_argument("gguf_path", help="Absolute path to the downloaded .gguf file.")
    parser.add_argument("domain", help="Target domain (e.g., Knowledge, Security)")
    parser.add_argument("name", help="Name of the skill (e.g., pdf_parser)")
    parser.add_argument("request", help="Description of what the skill should do.")
    
    args = parser.parse_args()
    distiller = LocalGGUFDistiller(args.gguf_path)
    distiller.distill(args.request, args.domain, args.name)
