# Merlin Adaptive LLM Backend - Self-Optimizing Multi-Model Orchestration
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from merlin_logger import merlin_logger
import merlin_settings as settings


@dataclass
class ModelMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    total_latency: float = 0.0
    user_ratings: List[int] = None
    task_successes: Dict[str, int] = None

    def __post_init__(self):
        if self.user_ratings is None:
            self.user_ratings = []
        if self.task_successes is None:
            self.task_successes = defaultdict(int)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency(self) -> float:
        if self.successful_requests == 0:
            return float("inf")
        return self.total_latency / self.successful_requests

    @property
    def avg_rating(self) -> float:
        if not self.user_ratings:
            return 0.0
        return sum(self.user_ratings) / len(self.user_ratings)

    @property
    def task_success_rate(self, task_type: str) -> float:
        total = sum(self.task_successes.values())
        if total == 0:
            return 0.0
        return self.task_successes.get(task_type, 0) / total

    def record_request(self, success: bool, latency: float, task_type: str = None):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_latency += latency
        if task_type:
            self.task_successes[task_type] += 1

    def record_rating(self, rating: int):
        self.user_ratings.append(rating)
        if len(self.user_ratings) > 100:
            self.user_ratings = self.user_ratings[-50:]

    def get_score(self, task_type: str = None) -> float:
        base_score = 0.5
        base_score += self.success_rate * 0.3
        base_score += min(1.0, 10.0 / max(1.0, self.avg_latency)) * 0.2
        base_score += self.avg_rating / 5.0 * 0.3

        if task_type and task_type in self.task_successes:
            base_score += self.task_success_rate(task_type) * 0.2

        return min(1.0, max(0.0, base_score))


@dataclass
class QueryContext:
    task_type: str
    complexity: str
    urgency: str
    requires_creativity: bool
    requires_accuracy: bool
    keywords: List[str]

    @classmethod
    def analyze(cls, query: str) -> "QueryContext":
        query_lower = query.lower()

        task_types = {
            "code": [
                "code",
                "function",
                "script",
                "debug",
                "fix",
                "program",
                "implement",
            ],
            "creative": ["story", "write", "poem", "creative", "imagine", "draft"],
            "analysis": [
                "analyze",
                "compare",
                "evaluate",
                "assess",
                "review",
                "explain",
            ],
            "search": ["find", "search", "lookup", "what is", "who is"],
            "fact": ["what", "when", "where", "how many", "how much"],
            "planning": ["plan", "schedule", "organize", "how to", "steps"],
            "translation": ["translate", "convert", "language"],
            "summarize": ["summarize", "brief", "summary", "short"],
        }

        task_type = "general"
        for ttype, keywords in task_types.items():
            if any(kw in query_lower for kw in keywords):
                task_type = ttype
                break

        complexity = "medium"
        if any(kw in query_lower for kw in ["simple", "basic", "quick", "just"]):
            complexity = "low"
        elif any(
            kw in query_lower
            for kw in ["complex", "detailed", "thorough", "comprehensive", "advanced"]
        ):
            complexity = "high"

        urgency = "normal"
        if any(
            kw in query_lower
            for kw in ["urgent", "asap", "now", "immediately", "quick"]
        ):
            urgency = "high"
        elif any(kw in query_lower for kw in ["when you can", "eventually", "later"]):
            urgency = "low"

        requires_creativity = any(
            kw in query_lower
            for kw in ["creative", "story", "imagine", "invent", "innovative"]
        )
        requires_accuracy = any(
            kw in query_lower
            for kw in ["accurate", "precise", "exact", "correct", "factual"]
        )

        keywords = [word for word in query_lower.split() if len(word) > 3][:10]

        return cls(
            task_type=task_type,
            complexity=complexity,
            urgency=urgency,
            requires_creativity=requires_creativity,
            requires_accuracy=requires_accuracy,
            keywords=keywords,
        )


class AdaptiveLLMBackend:
    def __init__(self):
        self.metrics_file = "artifacts/adaptive_metrics.json"
        self.model_metrics: Dict[str, ModelMetrics] = {}
        self.load_metrics()

        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.learning_mode = os.getenv("LEARNING_MODE", "enabled").lower() == "enabled"
        self.min_samples = int(os.getenv("MIN_LEARNING_SAMPLES", "5"))

        self.models = self._load_models()
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))

        self.strategies = {
            "voting": self._voting_strategy,
            "routing": self._adaptive_routing_strategy,
            "cascade": self._adaptive_cascade_strategy,
            "consensus": self._consensus_strategy,
            "auto": self._auto_strategy,
        }

        merlin_logger.info(
            f"Adaptive LLM Backend: {len(self.models)} models, learning: {self.learning_mode}"
        )

    def _load_models(self) -> List[Dict]:
        models = []

        for model_name in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": model_name,
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": model_name,
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

        return models

    def load_metrics(self):
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                for name, metrics in data.items():
                    self.model_metrics[name] = ModelMetrics(
                        total_requests=metrics.get("total_requests", 0),
                        successful_requests=metrics.get("successful_requests", 0),
                        total_latency=metrics.get("total_latency", 0.0),
                        user_ratings=metrics.get("user_ratings", []),
                        task_successes=metrics.get("task_successes", {}),
                    )
                merlin_logger.info(
                    f"Loaded metrics for {len(self.model_metrics)} models"
                )
            except Exception as e:
                merlin_logger.error(f"Failed to load metrics: {e}")

    def save_metrics(self):
        try:
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            data = {}
            for name, metrics in self.model_metrics.items():
                data[name] = {
                    "total_requests": metrics.total_requests,
                    "successful_requests": metrics.successful_requests,
                    "total_latency": metrics.total_latency,
                    "user_ratings": metrics.user_ratings,
                    "task_successes": metrics.task_successes,
                }
            with open(self.metrics_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save metrics: {e}")

    def _call_model(
        self, model: Dict, messages: List[Dict], temperature: float, timeout: int
    ) -> Dict:
        start_time = time.time()

        try:
            payload = {"model": model["model"], "messages": messages, "stream": False}

            if temperature is not None and model["backend"] == "ollama":
                payload["options"] = {"temperature": temperature}

            headers = {}
            if model.get("api_key"):
                headers["Authorization"] = f"Bearer {model['api_key']}"

            response = requests.post(
                model["url"], json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()

            data = response.json()
            latency = time.time() - start_time

            if model["backend"] == "ollama":
                content = data.get("message", {}).get("content", "")
            elif model["backend"] == "openai_compat":
                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
            else:
                content = str(data)

            return {
                "model_name": model["name"],
                "response": content,
                "latency": latency,
                "success": True,
            }

        except Exception as e:
            latency = time.time() - start_time
            return {
                "model_name": model["name"],
                "response": "",
                "latency": latency,
                "success": False,
                "error": str(e),
            }

    def _score_response(self, response: str, context: QueryContext) -> float:
        scores = []

        length_score = min(1.0, len(response) / 150)
        scores.append(length_score)

        if context.task_type == "code":
            code_keywords = [
                "def",
                "function",
                "class",
                "import",
                "return",
                "if",
                "for",
                "while",
            ]
            code_score = sum(1 for kw in code_keywords if kw in response) / len(
                code_keywords
            )
            scores.append(min(1.0, code_score * 2))

        if context.requires_creativity:
            creative_words = response.lower().split()
            diversity = len(set(creative_words)) / max(1, len(creative_words))
            scores.append(diversity)

        if context.requires_accuracy:
            has_structure = any(char in response for char in [".", ";", ":"])
            scores.append(1.0 if has_structure else 0.5)

        return sum(scores) / len(scores)

    def _auto_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        if context.urgency == "high":
            return self._adaptive_routing_strategy(context, responses)
        elif context.complexity == "high":
            return self._voting_strategy(context, responses)
        elif context.requires_accuracy:
            return self._consensus_strategy(context, responses)
        else:
            return self._adaptive_routing_strategy(context, responses)

    def _adaptive_routing_strategy(
        self, context: QueryContext, responses: List[Dict]
    ) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            return "All models failed to respond."

        for model in self.models:
            model_name = model["name"]
            if model_name in self.model_metrics:
                self.model_metrics[model_name].record_request(
                    success=False, latency=0, task_type=context.task_type
                )

        best_model = None
        best_score = -1.0

        for response in successful:
            model_name = response["model_name"]
            metrics = self.model_metrics.get(model_name, ModelMetrics())

            model_score = metrics.get_score(context.task_type)

            if self.learning_mode and metrics.total_requests >= self.min_samples:
                if best_score < model_score:
                    best_score = model_score
                    best_model = response
            else:
                if not best_model or response["latency"] < best_model["latency"]:
                    best_model = response

        if best_model:
            merlin_logger.info(
                f"Adaptive routing: Selected {best_model['model_name']} (score: {best_score:.2f})"
            )
            return best_model["response"]

        return successful[0]["response"]

    def _voting_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            return "All models failed to respond."

        scored = [(r, self._score_response(r["response"], context)) for r in successful]
        best = max(scored, key=lambda x: x[1])

        if self.learning_mode:
            for response, score in scored:
                model_name = response["model_name"]
                if model_name not in self.model_metrics:
                    self.model_metrics[model_name] = ModelMetrics()
                self.model_metrics[model_name].record_request(
                    success=response["success"],
                    latency=response["latency"],
                    task_type=context.task_type,
                )

        merlin_logger.info(
            f"Adaptive voting: Selected {best[0]['model_name']} (score: {best[1]:.2f})"
        )
        return best[0]["response"]

    def _adaptive_cascade_strategy(
        self, context: QueryContext, responses: List[Dict]
    ) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            return "All models failed to respond."

        fastest = min(successful, key=lambda r: r["latency"])

        if self.learning_mode and context.urgency != "high":
            best_quality = max(
                successful, key=lambda r: self._score_response(r["response"], context)
            )

            if fastest["latency"] < 2.0:
                refined = f"{fastest['response']}\n\n[Verified by {best_quality['model_name']}]"
                merlin_logger.info(
                    f"Adaptive cascade: {fastest['model_name']} → {best_quality['model_name']}"
                )

                for model_name in [fastest["model_name"], best_quality["model_name"]]:
                    if model_name not in self.model_metrics:
                        self.model_metrics[model_name] = ModelMetrics()
                    response_data = next(
                        r for r in successful if r["model_name"] == model_name
                    )
                    self.model_metrics[model_name].record_request(
                        success=response_data["success"],
                        latency=response_data["latency"],
                        task_type=context.task_type,
                    )

                return refined

        return fastest["response"]

    def _consensus_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            return "All models failed to respond."

        responses_text = [r["response"] for r in successful]

        word_counter = Counter()
        for resp in responses_text:
            words = resp.lower().split()
            word_counter.update(words)

        common_words = [
            word
            for word, count in word_counter.most_common(30)
            if count >= len(successful) // 2
        ]

        if len(common_words) < 5:
            return self._voting_strategy(context, responses)

        consensus = " ".join(common_words[:20])

        if self.learning_mode:
            for response in successful:
                model_name = response["model_name"]
                if model_name not in self.model_metrics:
                    self.model_metrics[model_name] = ModelMetrics()
                self.model_metrics[model_name].record_request(
                    success=response["success"],
                    latency=response["latency"],
                    task_type=context.task_type,
                )

        merlin_logger.info(f"Adaptive consensus: Built from {len(successful)} models")
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
                            "content": "Streaming not supported in adaptive mode yet."
                        }
                    }
                ]
            }

        query = messages[-1]["content"] if messages else ""
        context = QueryContext.analyze(query)

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
                merlin_logger.error(f"Adaptive execution error: {e}")

        strategy_func = self.strategies.get(self.strategy, self._auto_strategy)
        final_response = strategy_func(context, responses)

        self.save_metrics()

        return {"choices": [{"message": {"content": final_response}}]}

    def provide_feedback(self, model_name: str, rating: int, task_type: str = None):
        if self.learning_mode:
            if model_name not in self.model_metrics:
                self.model_metrics[model_name] = ModelMetrics()
            self.model_metrics[model_name].record_rating(rating)
            self.save_metrics()
            merlin_logger.info(f"Feedback recorded for {model_name}: {rating}/5")

    def get_status(self) -> Dict:
        return {
            "strategy": self.strategy,
            "learning_mode": self.learning_mode,
            "min_samples": self.min_samples,
            "models": [
                {"name": m["name"], "backend": m["backend"]} for m in self.models
            ],
            "metrics": {
                name: {
                    "total_requests": m.total_requests,
                    "success_rate": m.success_rate,
                    "avg_latency": m.avg_latency,
                    "avg_rating": m.avg_rating,
                }
                for name, m in self.model_metrics.items()
            },
        }

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

    def reset_metrics(self, model_name: str = None):
        if model_name:
            if model_name in self.model_metrics:
                self.model_metrics[model_name] = ModelMetrics()
        else:
            self.model_metrics = {name: ModelMetrics() for name in self.model_metrics}
        self.save_metrics()


adaptive_llm_backend = AdaptiveLLMBackend()
