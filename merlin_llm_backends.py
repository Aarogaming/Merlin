# Merlin LLM Backend Abstraction
import os
import requests
from merlin_logger import merlin_logger
import merlin_settings as settings


class LLMBackend:
    def __init__(self):
        self.backend = settings.LLM_BACKEND.lower()
        merlin_logger.info(f"LLM Backend initialized: {self.backend}")

    def chat_completion(
        self,
        messages: list,
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int = 30,
    ):
        if self.backend == "ollama":
            return self._ollama_chat(messages, temperature, stream, timeout)
        elif self.backend == "openai":
            return self._openai_chat(messages, temperature, stream, timeout)
        elif self.backend == "huggingface":
            return self._huggingface_chat(messages, temperature, stream, timeout)
        else:  # lmstudio (default)
            return self._lmstudio_chat(messages, temperature, stream, timeout)

    def _lmstudio_chat(
        self, messages: list, temperature: float, stream: bool, timeout: int
    ):
        try:
            payload = {
                "model": settings.OPENAI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            response = requests.post(
                settings.LM_STUDIO_URL, json=payload, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"LM Studio request failed: {e}")
            raise

    def _ollama_chat(
        self, messages: list, temperature: float, stream: bool, timeout: int
    ):
        try:
            default_model = (
                settings.OLLAMA_MODELS[0] if settings.OLLAMA_MODELS else "llama3.2"
            )
            payload = {"model": default_model, "messages": messages, "stream": stream}
            if temperature is not None:
                payload["options"] = {"temperature": temperature}
            response = requests.post(settings.OLLAMA_URL, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if "message" in data:
                return {"choices": [{"message": data["message"]}]}
            elif "model" in data:
                return {"choices": [{"message": {"content": data.get("response", "")}}]}
            return data
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"Ollama request failed: {e}")
            raise

    def _openai_chat(
        self, messages: list, temperature: float, stream: bool, timeout: int
    ):
        try:
            payload = {
                "model": settings.OPENAI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            response = requests.post(
                settings.OPENAI_URL, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"OpenAI request failed: {e}")
            raise

    def _huggingface_chat(
        self, messages: list, temperature: float, stream: bool, timeout: int
    ):
        try:
            payload = {
                "inputs": messages[-1]["content"],
                "parameters": {"temperature": temperature, "max_new_tokens": 500},
            }
            headers = {"Authorization": f"Bearer {settings.HF_API_KEY}"}
            response = requests.post(
                settings.HF_API_URL, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return {
                    "choices": [
                        {"message": {"content": data[0].get("generated_text", "")}}
                    ]
                }
            return {"choices": [{"message": {"content": str(data)}}]}
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"HuggingFace request failed: {e}")
            raise

    def health_check(self) -> bool:
        try:
            if self.backend == "ollama":
                response = requests.get(
                    settings.OLLAMA_URL.replace("/api/chat", "/api/tags"), timeout=5
                )
            elif self.backend == "lmstudio":
                response = requests.get(
                    settings.LM_STUDIO_URL.replace("/chat/completions", "/models"),
                    timeout=5,
                )
            elif self.backend == "openai":
                response = requests.get(
                    settings.OPENAI_URL.replace("/chat/completions", "/models"),
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    timeout=5,
                )
            elif self.backend == "huggingface":
                if not settings.HF_API_KEY:
                    return False
                response = requests.get(
                    "https://api-inference.huggingface.co/models",
                    headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                    timeout=5,
                )
            else:
                return False
            return response.status_code == 200
        except Exception as e:
            merlin_logger.warning(f"Health check failed for {self.backend}: {e}")
            return False


llm_backend = LLMBackend()
