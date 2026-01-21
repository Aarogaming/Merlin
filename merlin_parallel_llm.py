# Merlin Parallel LLM Backend - Multi-Model Orchestration
import os
import asyncio
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
from merlin_logger import merlin_logger
import merlin_settings as settings


@dataclass
class ModelResponse:
    model_name: str
    response: str
    latency: float
    success: bool
    error: Optional[str] = None


@dataclass
class ModelConfig:
    name: str
    backend: str
    url: str
    model: str
    api_key: Optional[str] = None


class ParallelLLMBackend:
    def __init__(self):
        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.models = self._load_models()
        merlin_logger.info(
            f"Parallel LLM Backend initialized with {len(self.models)} models, strategy: {self.strategy}"
        )
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))

    def _load_models(self) -> List[ModelConfig]:
        models = []

        # Mistral via Ollama
        if "mistral" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="mistral",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="mistral",
                )
            )

        # Nomic via Ollama
        if "nomic" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="nomic",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="nomic",
                )
            )

        # GLM (external API)
        if settings.GLM_API_KEY:
            models.append(
                ModelConfig(
                    name="glm4",
                    backend="openai_compat",
                    url=settings.GLM_URL,
                    model=settings.GLM_MODEL,
                    api_key=settings.GLM_API_KEY,
                )
            )

        # Nemotron 3 (external API)
        if settings.NEMOTRON_API_KEY:
            models.append(
                ModelConfig(
                    name="nemotron3",
                    backend="openai_compat",
                    url=settings.NEMOTRON_URL,
                    model=settings.NEMOTRON_MODEL,
                    api_key=settings.NEMOTRON_API_KEY,
                )
            )

        # Llama 3.2 via Ollama
        if "llama3.2" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="llama3.2",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="llama3.2",
                )
            )

        merlin_logger.info(f"Loaded {len(models)} models: {[m.name for m in models]}")
        return models

    def _call_model(
        self, model: ModelConfig, messages: List[Dict], temperature: float, timeout: int
    ) -> ModelResponse:
        import time

        start_time = time.time()

        try:
            payload = {"model": model.model, "messages": messages, "stream": False}

            if temperature is not None:
                payload["options"] = {"temperature": temperature}

            headers = {}
            if model.api_key:
                headers["Authorization"] = f"Bearer {model.api_key}"

            response = requests.post(
                model.url, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()

            data = response.json()
            latency = time.time() - start_time

            if model.backend == "ollama":
                content = data.get("message", {}).get("content", "")
            elif model.backend == "openai_compat":
                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
            else:
                content = str(data)

            return ModelResponse(
                model_name=model.name, response=content, latency=latency, success=True
            )

        except Exception as e:
            latency = time.time() - start_time
            merlin_logger.error(f"Model {model.name} failed: {e}")
            return ModelResponse(
                model_name=model.name,
                response="",
                latency=latency,
                success=False,
                error=str(e),
            )

    def _score_response(self, response: str, query: str) -> float:
        try:
            scores = []

            length_score = min(1.0, len(response) / 100)
            scores.append(length_score)

            if "?" in query:
                has_answer = any(char in response for char in ["!", ".", ":"])
                scores.append(1.0 if has_answer else 0.5)
            else:
                scores.append(0.8)

            diversity_score = len(set(response.lower().split())) / max(
                1, len(response.split())
            )
            scores.append(diversity_score)

            return sum(scores) / len(scores)
        except:
            return 0.5

    def _voting_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            return "All models failed to respond."

        scored = [(r, self._score_response(r.response, query)) for r in successful]
        best = max(scored, key=lambda x: x[1])

        merlin_logger.info(
            f"Voting: Selected {best[0].model_name} (score: {best[1]:.2f})"
        )
        return best[0].response

    def _routing_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        query_lower = query.lower()

        routing_rules = {
            "code": [
                "code",
                "program",
                "function",
                "script",
                "debug",
                "fix",
                "nemotron3",
            ],
            "creative": ["story", "creative", "write", "poem", "imagine", "mistral"],
            "fast": ["quick", "short", "brief", "llama3.2"],
            "embedding": ["search", "find", "vector", "semantic", "nomic"],
            "analysis": ["analyze", "compare", "evaluate", "assess", "glm4"],
        }

        selected_model = "llama3.2"
        for category, keywords in routing_rules.items():
            if any(kw in query_lower for kw in keywords):
                selected_model = keywords[-1]
                break

        for response in responses:
            if response.success and response.model_name == selected_model:
                merlin_logger.info(f"Routing: Selected {response.model_name} for query")
                return response.response

        successful = [r for r in responses if r.success]
        return successful[0].response if successful else "No models available."

    def _cascade_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            return "All models failed to respond."

        fastest = min(successful, key=lambda r: r.latency)
        best_quality = max(
            successful, key=lambda r: self._score_response(r.response, query)
        )

        if fastest.latency < 2.0:
            refined = f"{fastest.response}\n\n[Refined by {best_quality.model_name}]"
            merlin_logger.info(
                f"Cascade: {fastest.model_name} → {best_quality.model_name}"
            )
            return refined
        else:
            merlin_logger.info(f"Cascade: Direct to {best_quality.model_name}")
            return best_quality.response

    def _consensus_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            return "All models failed to respond."

        responses_text = [r.response for r in successful]

        from collections import Counter

        words = []
        for resp in responses_text:
            words.extend(resp.lower().split())

        if not words:
            return successful[0].response

        word_counts = Counter(words)
        common_words = [
            word
            for word, count in word_counts.most_common(20)
            if count >= len(successful)
        ]

        if len(common_words) < 5:
            return self._voting_strategy(query, responses)

        consensus = " ".join(common_words[:15])
        merlin_logger.info(f"Consensus: Built from {len(successful)} models")
        return f"Based on consensus analysis: {consensus}"

    def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int = 30,
    ) -> Dict:
        if stream:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Streaming not supported in parallel mode yet."
                        }
                    }
                ]
            }

        query = messages[-1]["content"] if messages else ""

        futures = []
        for model in self.models:
            future = self.executor.submit(
                self._call_model, model, messages, temperature, timeout
            )
            futures.append(future)

        responses = []
        for future in as_completed(futures):
            try:
                response = future.result()
                responses.append(response)
            except Exception as e:
                merlin_logger.error(f"Parallel execution error: {e}")

        strategies = {
            "voting": self._voting_strategy,
            "routing": self._routing_strategy,
            "cascade": self._cascade_strategy,
            "consensus": self._consensus_strategy,
        }

        strategy_func = strategies.get(self.strategy, self._voting_strategy)
        final_response = strategy_func(query, responses)

        return {"choices": [{"message": {"content": final_response}}]}

    def health_check(self) -> Dict[str, bool]:
        results = {}
        for model in self.models:
            try:
                response = requests.get(
                    model.url.replace("/chat/completions", "/tags")
                    if "/chat" in model.url
                    else model.url,
                    timeout=3,
                )
                results[model.name] = response.status_code == 200
            except:
                results[model.name] = False
        return results

    def get_status(self) -> Dict:
        return {
            "strategy": self.strategy,
            "models": [{"name": m.name, "backend": m.backend} for m in self.models],
            "health": self.health_check(),
        }


parallel_llm_backend = ParallelLLMBackend()
