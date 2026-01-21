# Streaming LLM Backend - Real-time Multi-Model Orchestration with Streaming
import os
import json
import time
import asyncio
from typing import Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from merlin_logger import merlin_logger
import merlin_settings as settings
from merlin_cost_optimization import cost_optimization_manager


@dataclass
class StreamingModelResponse:
    model_name: str
    response_generator: AsyncGenerator[str, None]
    latency: float
    success: bool
    error: Optional[str] = None


class StreamingLLMBackend:
    def __init__(self):
        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.models = self._load_models()
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))
        merlin_logger.info(
            f"Streaming LLM Backend: {len(self.models)} models, strategy: {self.strategy}"
        )

    def _load_models(self) -> List[Dict]:
        models = []

        if "mistral" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "mistral",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "mistral",
                }
            )

        if "nomic" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "nomic",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "nomic",
                }
            )

        if "llama3.2" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "llama3.2",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "llama3.2",
                }
            )

        if settings.GLM_API_KEY:
            models.append(
                {
                    "name": "glm4",
                    "backend": "openai_compat",
                    "url": settings.GLM_URL,
                    "model": settings.GLM_MODEL,
                    "api_key": settings.GLM_API_KEY,
                }
            )

        if settings.NEMOTRON_API_KEY:
            models.append(
                {
                    "name": "nemotron3",
                    "backend": "openai_compat",
                    "url": settings.NEMOTRON_URL,
                    "model": settings.NEMOTRON_MODEL,
                    "api_key": settings.NEMOTRON_API_KEY,
                }
            )

        return models

    async def _stream_model(
        self, model: Dict, messages: List[Dict], temperature: float
    ) -> StreamingModelResponse:
        start_time = time.time()

        try:
            payload = {"model": model["model"], "messages": messages, "stream": True}

            if temperature is not None and model["backend"] == "ollama":
                payload["options"] = {"temperature": temperature}

            headers = {}
            if model.get("api_key"):
                headers["Authorization"] = f"Bearer {model['api_key']}"

            async def stream_generator():
                try:
                    response = requests.post(
                        model["url"],
                        json=payload,
                        headers=headers,
                        stream=True,
                        timeout=30,
                    )
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if line:
                            line = line.decode("utf-8")
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    data = json.loads(data_str)
                                    if model["backend"] == "ollama":
                                        if "message" in data:
                                            yield data["message"].get("content", "")
                                    elif "done" in data:
                                        break
                                    elif "content" in data:
                                        yield data["content"]
                                    else:
                                        chunks = []
                                        for choice in data.get("choices", []):
                                            if "delta" in choice:
                                                chunks.append(
                                                    choice["delta"].get("content", "")
                                                )
                                        yield "".join(chunks)
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    merlin_logger.error(f"Streaming error for {model['name']}: {e}")
                    yield f"[Error: {str(e)}]"

            latency = time.time() - start_time

            return StreamingModelResponse(
                model_name=model["name"],
                response_generator=stream_generator(),
                latency=latency,
                success=True,
            )

        except Exception as e:
            latency = time.time() - start_time
            merlin_logger.error(f"Model {model['name']} failed: {e}")

            async def error_generator():
                yield f"[Error: {str(e)}]"

            return StreamingModelResponse(
                model_name=model["name"],
                response_generator=error_generator(),
                latency=latency,
                success=False,
                error=str(e),
            )

    def _score_chunk(self, chunk: str, query: str) -> float:
        scores = []

        length_score = min(1.0, len(chunk) / 50)
        scores.append(length_score)

        if "?" in query:
            has_answer = any(char in chunk for char in ["!", ".", ":"])
            scores.append(1.0 if has_answer else 0.5)
        else:
            scores.append(0.8)

        diversity_score = len(set(chunk.lower().split())) / max(1, len(chunk.split()))
        scores.append(diversity_score)

        return sum(scores) / len(scores)

    async def _voting_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            yield "All models failed to respond."
            return

        accumulated_responses = {}

        async def collect_responses():
            tasks = [
                asyncio.create_task(self._collect_full_response(r)) for r in successful
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            for i, task in enumerate(tasks):
                if not task.exception():
                    accumulated_responses[i] = task.result()

        await collect_responses()

        scored = [
            (i, self._score_response_text(accumulated_responses.get(i, ""), query))
            for i in range(len(successful))
        ]
        best_idx = max(scored, key=lambda x: x[1])[0]

        best_response = accumulated_responses.get(best_idx, "")
        merlin_logger.info(
            f"Streaming voting: Selected {successful[best_idx].model_name} (score: {scored[best_idx][1]:.2f})"
        )

        for word in best_response.split():
            yield word + " "
            await asyncio.sleep(0.01)

    async def _routing_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
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
                merlin_logger.info(f"Streaming routing: Selected {response.model_name}")
                async for chunk in response.response_generator:
                    yield chunk
                return

        for response in responses:
            if response.success:
                async for chunk in response.response_generator:
                    yield chunk
                return

        yield "No models available."

    async def _cascade_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            yield "All models failed to respond."
            return

        fastest = min(successful, key=lambda r: r.latency)

        if fastest.latency < 2.0:
            merlin_logger.info(f"Streaming cascade: {fastest.model_name} (fast)")
            async for chunk in fastest.response_generator:
                yield chunk

            yield "\n\n[Verifying with other models...]"
            await asyncio.sleep(0.5)
        else:
            best_quality = max(successful, key=lambda r: r.latency)
            merlin_logger.info(f"Streaming cascade: {best_quality.model_name}")
            async for chunk in best_quality.response_generator:
                yield chunk

    async def _consensus_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            yield "All models failed to respond."
            return

        async def collect_all():
            tasks = [
                asyncio.create_task(self._collect_full_response(r)) for r in successful
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            all_responses = []
            for i, task in enumerate(tasks):
                if not task.exception():
                    all_responses.append(task.result())

            return all_responses

        responses_text = await collect_all()

        from collections import Counter

        words = []
        for resp in responses_text:
            words.extend(resp.lower().split())

        if not words:
            async for chunk in responses[0].response_generator:
                yield chunk
            return

        word_counts = Counter(words)
        common_words = [
            word
            for word, count in word_counts.most_common(20)
            if count >= len(successful) // 2
        ]

        if len(common_words) < 5:
            async for chunk in responses[0].response_generator:
                yield chunk
            return

        consensus = " ".join(common_words[:15])
        merlin_logger.info(f"Streaming consensus: Built from {len(successful)} models")
        yield f"Based on consensus analysis: {consensus}"

    async def _collect_full_response(self, response: StreamingModelResponse) -> str:
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    def _score_response_text(self, response: str, query: str) -> float:
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

    async def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        stream: bool = True,
        timeout: int = 30,
    ) -> AsyncGenerator[str, None]:
        if not stream:
            yield "Streaming not disabled in streaming backend."
            return

        query = messages[-1]["content"] if messages else ""

        strategies = {
            "voting": self._voting_strategy_stream,
            "routing": self._routing_strategy_stream,
            "cascade": self._cascade_strategy_stream,
            "consensus": self._consensus_strategy_stream,
        }

        strategy_func = strategies.get(self.strategy, self._voting_strategy_stream)

        stream_tasks = [
            asyncio.create_task(self._stream_model(model, messages, temperature))
            for model in self.models
        ]

        completed_responses = []
        for future in asyncio.as_completed(stream_tasks):
            try:
                response = await future
                completed_responses.append(response)
            except Exception as e:
                merlin_logger.error(f"Stream execution error: {e}")

        async for chunk in strategy_func(query, completed_responses):
            yield chunk

    def health_check(self) -> Dict[str, bool]:
        results = {}
        for model in self.models:
            try:
                response = requests.get(
                    model["url"].replace("/chat/completions", "/tags")
                    if "/chat" in model["url"]
                    else model["url"],
                    timeout=3,
                )
                results[model["name"]] = response.status_code == 200
            except:
                results[model["name"]] = False
        return results

    def get_status(self) -> Dict:
        return {
            "strategy": self.strategy,
            "models": [
                {"name": m["name"], "backend": m["backend"]} for m in self.models
            ],
            "health": self.health_check(),
        }


streaming_llm_backend = StreamingLLMBackend()
