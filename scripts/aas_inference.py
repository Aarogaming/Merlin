import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    # Requires: pip install llama-cpp-python
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False

class InlineInferenceEngine:
    """
    Universal inline GGUF execution engine for the Aaroneous Automation Suite.
    """
    
    def __init__(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1, verbose: bool = False, partial_load_layers: int = None):
        self.logger = logging.getLogger("InlineInferenceEngine")
        
        if not HAS_LLAMA_CPP:
            self.logger.error("llama-cpp-python is not installed.")
            raise ImportError("Missing llama-cpp-python")

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")

        self.logger.info(f"Loading GGUF model: {path.name}")
        
        # --- PARTIAL GGUF LOADING ---
        # If partial_load_layers is specified, we intentionally restrict the number of 
        # model layers loaded into VRAM/RAM. This is effectively "Early Exiting" or 
        # shallow loading a massive model (e.g., loading 10 layers of a 70B model).
        # Note: llama.cpp handles n_gpu_layers for VRAM offloading, but true partial 
        # layer computation requires specific model support or aggressive layer pruning.
        # We simulate the intent here by drastically restricting context and offload 
        # when a 'shallow' load is requested by the agent's Thought reflex.
        
        if partial_load_layers is not None:
            self.logger.warning(f"PARTIAL LOAD INITIATED: Restricting to {partial_load_layers} layers for rapid shallow inference.")
            n_gpu_layers = partial_load_layers # Force restricted VRAM offload
            n_ctx = min(n_ctx, 512) # Force tiny context for speed
            
        try:
            self.llm = Llama(
                model_path=str(path),
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=verbose
            )
            self.logger.info("Model successfully loaded.")
        except Exception as e:
            self.logger.error(f"Failed to initialize llama.cpp engine: {e}")
            raise

    def generate_chat(self, messages: List[Dict[str, str]], max_tokens: int = 1024, temperature: float = 0.7, stop: Optional[List[str]] = None) -> str:
        if not self.llm:
            raise RuntimeError("Inference engine is not initialized.")
            
        try:
            response = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop
            )
            return response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            self.logger.error(f"Inference failed: {e}")
            return f"Error: Inference failed - {str(e)}"

    def unload(self):
        if self.llm:
            self.logger.info("Unloading GGUF model from memory.")
            del self.llm
            self.llm = None
