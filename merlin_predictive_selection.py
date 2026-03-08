# Predictive Model Selection - ML-Based LLM Optimization
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from merlin_logger import merlin_logger
from merlin_adaptive_llm import adaptive_llm_backend


@dataclass
class QueryFeatures:
    task_type: (
        str  # code, creative, analysis, search, fact, planning, translation, summarize
    )
    complexity: str  # low, medium, high
    urgency: str  # low, normal, high
    requires_creativity: bool
    requires_accuracy: bool
    length: int
    word_count: int
    has_code_keywords: bool
    has_question_mark: bool
    time_of_day: int  # 0-23 hours
    day_of_week: int  # 0-6 (Mon-Sun)

    @classmethod
    def from_query(
        cls, query: str, query_time: Optional[datetime] = None
    ) -> "QueryFeatures":
        if query_time is None:
            query_time = datetime.now()

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
            "creative": [
                "story",
                "write",
                "poem",
                "creative",
                "imagine",
                "invent",
                "innovative",
            ],
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
            kw in query_lower for kw in ["creative", "story", "imagine", "invent"]
        )
        requires_accuracy = any(
            kw in query_lower
            for kw in ["accurate", "precise", "exact", "correct", "factual"]
        )

        code_keywords = [
            "def",
            "function",
            "class",
            "import",
            "return",
            "if",
            "for",
            "while",
            "variable",
        ]
        has_code_keywords = any(kw in query_lower for kw in code_keywords)
        has_question_mark = "?" in query

        return cls(
            task_type=task_type,
            complexity=complexity,
            urgency=urgency,
            requires_creativity=requires_creativity,
            requires_accuracy=requires_accuracy,
            length=len(query),
            word_count=len(query.split()),
            has_code_keywords=has_code_keywords,
            has_question_mark=has_question_mark,
            time_of_day=query_time.hour,
            day_of_week=query_time.weekday(),
        )


@dataclass
class ModelPerformance:
    model_name: str
    success_rate: float
    avg_latency: float
    avg_rating: float
    total_requests: int
    task_successes: Dict[str, int] = field(default_factory=dict)

    def get_feature_vector(self, task_type: str) -> list[float]:
        task_score = self.task_successes.get(task_type, 0) / max(1, self.total_requests)

        vector = [
            self.success_rate,
            10.0 / max(1.0, self.avg_latency),  # Higher is worse
            self.avg_rating / 5.0,  # Normalized to 0-1
            task_score,
            1.0 if self.total_requests > 100 else 0.5,  # Confidence
            1.0 if self.success_rate > 0.9 else 0.7,  # Reliability
        ]

        return vector


class PredictiveModelSelector:
    def __init__(self):
        self.models_file = "artifacts/predictive_model.json"
        self.model_weights = {}
        self.feature_importance = {}
        self.training_data: List[Tuple[QueryFeatures, str]] = []
        self.load_models()
        self._load_weights_fallback()
        merlin_logger.info(
            "Predictive Model Selector: ML-based model selection enabled"
        )

    def load_models(self):
        if os.path.exists(self.models_file):
            try:
                with open(self.models_file, "r") as f:
                    data = json.load(f)
                    self.model_weights = data.get("model_weights", {})
                    self.feature_importance = data.get("feature_importance", {})
                    self.training_data = [
                        (QueryFeatures(**qf), selected_model)
                        for qf, selected_model in data.get("training_data", [])
                    ]
                merlin_logger.info(
                    f"Loaded {len(self.model_weights)} models and {len(self.training_data)} training samples"
                )
            except Exception as e:
                merlin_logger.error(f"Failed to load predictive models: {e}")

    def _load_weights_fallback(self) -> None:
        if not self.model_weights:
            self.train_initial_weights()

    def save_models(self):
        try:
            data = {
                "model_weights": self.model_weights,
                "feature_importance": self.feature_importance,
                "training_data": self.training_data[-1000:],  # Keep last 1000 samples
                "last_updated": datetime.now().isoformat(),
            }

            os.makedirs(os.path.dirname(self.models_file), exist_ok=True)
            with open(self.models_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            merlin_logger.error(f"Failed to save predictive models: {e}")

    def train_initial_weights(self):
        if not self.model_weights:
            model_names = ["mistral", "llama3.2", "nemotron3", "glm4", "nomic"]

            for model in model_names:
                self.model_weights[model] = {
                    "task_type": 0.25,
                    "complexity": 0.20,
                    "urgency": 0.20,
                    "creativity": 0.15,
                    "accuracy": 0.10,
                    "latency": 0.10,
                }

            self.feature_importance = {
                "task_type": 0.9,
                "complexity": 0.8,
                "urgency": 0.8,
                "creativity": 0.7,
                "accuracy": 0.9,
                "latency": 0.8,
            }

            merlin_logger.info("Initialized default model weights")

    def get_model_scores(self, features: QueryFeatures) -> Dict[str, float]:
        scores = {}

        for model_name, weights in self.model_weights.items():
            feature_values = {
                "task_type": self._encode_task_type(features.task_type),
                "complexity": self._encode_complexity(features.complexity),
                "urgency": self._encode_urgency(features.urgency),
                "creativity": 1.0 if features.requires_creativity else 0.0,
                "accuracy": 1.0 if features.requires_accuracy else 0.0,
                "latency": self._encode_urgency(
                    features.urgency
                ),  # Higher urgency = lower latency importance
                "length": features.length / 500.0,  # Normalized
                "word_count": features.word_count / 100.0,  # Normalized
                "has_code_keywords": 1.0 if features.has_code_keywords else 0.0,
                "has_question_mark": 1.0 if features.has_question_mark else 0.0,
                "time_of_day": features.time_of_day / 23.0,  # Normalized
                "day_of_week": features.day_of_week / 6.0,  # Normalized
            }

            score = sum(
                feature_values[feature] * self.feature_importance.get(feature, 1.0)
                for feature in weights.keys()
            )

            scores[model_name] = score

        return scores

    def _encode_task_type(self, task_type: str) -> float:
        encodings = {
            "code": 0.8,
            "creative": 0.7,
            "analysis": 0.6,
            "search": 0.5,
            "fact": 0.4,
            "planning": 0.5,
            "translation": 0.3,
            "summarize": 0.3,
            "general": 0.5,
        }
        return encodings.get(task_type, 0.5)

    def _encode_complexity(self, complexity: str) -> float:
        encodings = {"low": 0.3, "medium": 0.5, "high": 0.7}
        return encodings.get(complexity, 0.5)

    def _encode_urgency(self, urgency: str) -> float:
        encodings = {"low": 0.3, "normal": 0.5, "high": 0.8}
        return encodings.get(urgency, 0.5)

    def select_model(self, query: str, query_time: Optional[datetime] = None) -> str:
        features = QueryFeatures.from_query(query, query_time)
        scores = self.get_model_scores(features)

        if not scores:
            return "llama3.2"  # Default

        best_model = max(scores.items(), key=lambda x: x[1])[0]

        merlin_logger.info(
            f"Predictive selection: {best_model} (score: {scores[best_model]:.3f}) for query: {query[:50]}"
        )

        return best_model

    def record_feedback(
        self,
        model_name: str,
        was_successful: bool,
        latency: float,
        task_type: str,
        rating: Optional[int] = None,
    ):
        if model_name not in self.model_weights:
            self.model_weights[model_name] = {
                "task_type": 0.25,
                "complexity": 0.20,
                "urgency": 0.20,
                "creativity": 0.15,
                "accuracy": 0.10,
                "latency": 0.10,
            }

        features = QueryFeatures.from_query("", datetime.now())
        encoded_task_type = self._encode_task_type(task_type)

        if rating is not None and rating >= 4:
            increase = 0.05 * (rating - 3) / 2.0  # Positive feedback
            self.model_weights[model_name]["task_type"] += increase
            merlin_logger.info(
                f"Positive feedback increased {model_name} task_type weight to {self.model_weights[model_name]['task_type']:.3f}"
            )

        elif rating is not None and rating <= 2:
            decrease = 0.05 * (3 - rating) / 2.0  # Negative feedback
            self.model_weights[model_name]["task_type"] -= decrease
            merlin_logger.info(
                f"Negative feedback decreased {model_name} task_type weight to {self.model_weights[model_name]['task_type']:.3f}"
            )

        if was_successful and latency < 1.0:
            self.model_weights[model_name]["latency"] += 0.02
        elif was_successful and latency > 3.0:
            self.model_weights[model_name]["latency"] -= 0.01

        normalized_score = self._normalize_weights(self.model_weights[model_name])
        merlin_logger.info(
            f"Updated {model_name} weights (normalized score: {normalized_score:.3f})"
        )

        self.save_models()

    def _normalize_weights(self, weights: Dict[str, float]) -> float:
        total = abs(sum(weights.values()))
        if total == 0:
            return 0.0
        return abs(weights.get("task_type", 0)) / total

    def get_model_explanation(self, model_name: str, query: str) -> str:
        features = QueryFeatures.from_query(query)
        scores = self.get_model_scores(features)
        model_score = scores.get(model_name, 0.0)
        weights = self.model_weights.get(model_name, {})

        reasons = []

        if model_score > 0:
            max_score = max(scores.values())
            if abs(model_score - max_score) < 0.1:
                reasons.append(
                    f"Best match for {features.task_type} queries (score: {model_score:.3f})"
                )

        if weights.get("task_type", 0) > 0.25:
            top_type, _top_name = max(
                ((m.get("task_type", 0), n) for n, m in self.model_weights.items()),
                key=lambda item: item[0],
            )
            if weights["task_type"] >= top_type * 0.9:
                reasons.append(f"Highly effective for {features.task_type} tasks")

        if weights.get("latency", 0) > 0.15:
            reasons.append(f"Fast response specialist")

        if features.urgency == "high" and model_score > 0.6:
            reasons.append(f"Optimized for urgent queries")

        if not reasons:
            reasons.append("Selected based on balanced capabilities")

        return "; ".join(reasons)

    def get_status(self) -> Dict:
        model_scores = {
            model: self._normalize_weights(self.model_weights.get(model, {}))
            for model in self.model_weights.keys()
        }
        return {
            "model_count": len(self.model_weights),
            "training_samples": len(self.training_data),
            "last_updated": datetime.now().isoformat(),
            "model_scores": model_scores,
            "feature_importance": self.feature_importance,
        }

    def export_model_data(self) -> Dict:
        return {
            "model_weights": self.model_weights,
            "training_data": self.training_data[-100:],
            "feature_importance": self.feature_importance,
            "export_timestamp": datetime.now().isoformat(),
        }


predictive_model_selector = PredictiveModelSelector()
