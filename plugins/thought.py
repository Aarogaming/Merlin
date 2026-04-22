import json
try:
    import litellm
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

from aas_kernel import ReflexPlugin

class Thought(ReflexPlugin):
    """
    Domain: Guild (Thought/Operations)
    Handles Model Tiering, Routing, and tactical operations.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tiers = {
            "tier_1_local": "ollama/llama3",
            "tier_2_fast": "gpt-4o-mini",
            "tier_3_heavy": "claude-3-5-sonnet-20241022"
        }

    @property
    def capabilities(self) -> list[str]:
        return ["aaroneousautomationsuite_model_routing"]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()
        
        if capability_id != "aaroneousautomationsuite_model_routing":
            return self._format_error(capability_id, "Unhandled thought capability.")

        if not HAS_LITELLM:
            return self._format_error(capability_id, "LiteLLM missing. Cannot complete thought process.")

        task_type = payload.get("task_type", "general").lower()
        
        # Routing Logic
        if task_type in ["data_extraction", "formatting", "simple_parse", "ping"]:
            model = self.tiers["tier_1_local"]
            shallow_load = True
        elif task_type in ["architectural_design", "complex_code", "debugging", "synthesis"]:
            model = self.tiers["tier_3_heavy"]
            shallow_load = False
        else:
            model = self.tiers["tier_2_fast"]
            shallow_load = False
            
        # --- Infinite Persona Expansion Injection ---
        # Instead of a static SOUL.md, we dynamically construct the psychological 
        # parameters of the agent directly from its Epigenetic DNA sequence.
        persona_context = (
            f"You are operating as a specialized Node within the AaroneousAutomationSuite federation.\n"
            f"Archetype: {self.persona_vectors.get('primary_archetype', 'AI Operator')}\n"
            f"Tone: {self.persona_vectors.get('tone', 'neutral')}\n\n"
            f"Cognitive Parameters (Scale 0.0 to 1.0):\n"
            f"- Formality: {self.persona_vectors.get('formality', 0.5)}\n"
            f"- Verbosity: {self.persona_vectors.get('verbosity', 0.5)}\n"
            f"- Analytical Depth: {self.cognitive_biases.get('analytical_depth', 0.5)}\n"
            f"- Risk Tolerance: {self.cognitive_biases.get('risk_tolerance', 0.5)}\n"
            f"- Creative Variance: {self.cognitive_biases.get('creative_variance', 0.5)}\n"
            f"- Empathy Level: {self.persona_vectors.get('empathy_level', 0.5)}\n\n"
            f"Constraint: You must strictly adhere to the above parameters in your response."
        )
        
        # Inject the dynamically generated soul into the LLM context
        messages = payload.get("messages", [])
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{persona_context}\n\n{messages[0]['content']}"
        else:
            messages.insert(0, {"role": "system", "content": persona_context})

        # --- Universal Hyperparameter Application ---
        # We translate the Epigenetic DNA directly into literal LLM API parameters.
        
        # 1. Temperature = Base * Creative Variance
        variance_scalar = self.cognitive_biases.get("creative_variance", 50.0) / 50.0
        adjusted_temperature = payload.get("temperature", 0.7) * variance_scalar
        
        # 2. Top_P = Analytical Depth controls token probability mass. 
        # Deeply analytical agents constrain token selection to highly probable truths.
        depth_scalar = self.cognitive_biases.get("analytical_depth", 50.0) / 100.0
        adjusted_top_p = 1.0 - (depth_scalar * 0.3) # Ranges from 1.0 (loose) to 0.7 (strict)
        
        # 3. Presence Penalty = Formality. 
        # Formal agents are succinct and don't wander.
        formality_scalar = self.persona_vectors.get("formality", 50.0) / 100.0
        adjusted_presence = formality_scalar * 0.5 # Ranges from 0.0 to 0.5
        
        # --- RAPID SHALLOW INFERENCE ---
        # If the agent only needs a simple extraction, we instruct LiteLLM / local engine
        # to restrict max_tokens aggressively, simulating a partial 1B load for speed.
        if shallow_load:
            payload["max_tokens"] = min(payload.get("max_tokens", 100), 100)
            
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=payload.get("max_tokens", 1024),
                temperature=adjusted_temperature,
                top_p=adjusted_top_p,
                presence_penalty=adjusted_presence
            )
            result = {
                "model_used": model,
                "applied_hyperparameters": {
                    "temperature": round(adjusted_temperature, 3),
                    "top_p": round(adjusted_top_p, 3),
                    "presence_penalty": round(adjusted_presence, 3)
                },
                "output": response.choices[0].message.content
            }
            return self._format_success(capability_id, result, start_time)
        except Exception as e:
            return self._format_error(capability_id, str(e))
