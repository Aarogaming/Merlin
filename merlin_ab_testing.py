# A/B Testing System - Strategy Performance Comparison
import os
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from merlin_logger import merlin_logger
from merlin_streaming_llm import streaming_llm_backend


@dataclass
class ABTest:
    test_id: str
    name: str
    variants: List[str]  # Strategy names being tested
    weights: List[float]  # Traffic split percentages
    start_time: str
    end_time: Optional[str] = None
    status: str = "active"  # active, paused, completed
    metrics: Dict[str, Dict] = field(default_factory=dict)  # variant -> metrics

    def get_variant_for_request(self) -> str:
        if self.status != "active":
            return self.variants[0]

        rand = random.random()
        cumulative = 0.0
        for variant, weight in zip(self.variants, self.weights):
            cumulative += weight
            if rand < cumulative:
                return variant

        return self.variants[0]

    def add_metric(
        self,
        variant: str,
        user_rating: Optional[int] = None,
        latency: float = 0.0,
        success: bool = True,
    ):
        if variant not in self.metrics:
            self.metrics[variant] = {
                "requests": 0,
                "ratings": [],
                "latencies": [],
                "successes": [],
            }

        metrics = self.metrics[variant]
        metrics["requests"] += 1
        metrics["successes"].append(1 if success else 0)
        metrics["latencies"].append(latency)

        if user_rating is not None:
            metrics["ratings"].append(user_rating)
            if len(metrics["ratings"]) > 100:
                metrics["ratings"] = metrics["ratings"][-50:]

    def get_variant_stats(self, variant: str) -> Dict:
        if variant not in self.metrics:
            return {"requests": 0, "success_rate": 0, "avg_latency": 0, "avg_rating": 0}

        metrics = self.metrics[variant]
        requests = metrics["requests"]

        if requests == 0:
            return {"requests": 0, "success_rate": 0, "avg_latency": 0, "avg_rating": 0}

        successes = sum(metrics["successes"])
        success_rate = successes / requests

        avg_latency = (
            sum(metrics["latencies"]) / len(metrics["latencies"])
            if metrics["latencies"]
            else 0
        )

        avg_rating = (
            sum(metrics["ratings"]) / len(metrics["ratings"])
            if metrics["ratings"]
            else 0
        )

        return {
            "requests": requests,
            "success_rate": success_rate,
            "avg_latency": avg_latency,
            "avg_rating": avg_rating,
        }

    def get_winner(self) -> Optional[Dict]:
        if self.status != "completed" or not self.metrics:
            return None

        best_variant = None
        best_score = -1.0

        for variant in self.metrics:
            stats = self.get_variant_stats(variant)
            if stats["requests"] < 10:
                continue

            score = (
                stats["success_rate"] * 0.5
                + (10.0 / max(1.0, stats["avg_latency"])) * 0.3
                + stats["avg_rating"] / 5.0 * 0.2
            )

            if score > best_score:
                best_score = score
                best_variant = variant

        if best_variant:
            stats = self.get_variant_stats(best_variant)
            return {"variant": best_variant, "score": best_score, "stats": stats}

        return None


class ABTestingManager:
    def __init__(self):
        self.tests_file = "artifacts/ab_tests.json"
        self.active_tests: Dict[str, ABTest] = {}
        self.test_history: List[ABTest] = []
        self.load_tests()
        merlin_logger.info(f"AB Testing Manager: {len(self.active_tests)} active tests")

    def load_tests(self):
        if os.path.exists(self.tests_file):
            try:
                with open(self.tests_file, "r") as f:
                    data = json.load(f)
                    for test_id, test_data in data.get("active_tests", {}).items():
                        self.active_tests[test_id] = ABTest(**test_data)

                    for history_data in data.get("history", []):
                        self.test_history.append(ABTest(**history_data))

                merlin_logger.info(f"Loaded {len(self.active_tests)} active tests")
            except Exception as e:
                merlin_logger.error(f"Failed to load A/B tests: {e}")

    def save_tests(self):
        try:
            data = {
                "active_tests": {
                    test_id: {
                        "test_id": test.test_id,
                        "name": test.name,
                        "variants": test.variants,
                        "weights": test.weights,
                        "start_time": test.start_time,
                        "end_time": test.end_time,
                        "status": test.status,
                        "metrics": test.metrics,
                    }
                    for test_id, test in self.active_tests.items()
                },
                "history": [
                    {
                        "test_id": test.test_id,
                        "name": test.name,
                        "variants": test.variants,
                        "weights": test.weights,
                        "start_time": test.start_time,
                        "end_time": test.end_time,
                        "status": test.status,
                        "metrics": test.metrics,
                    }
                    for test in self.test_history
                ],
            }

            os.makedirs(os.path.dirname(self.tests_file), exist_ok=True)
            with open(self.tests_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            merlin_logger.error(f"Failed to save A/B tests: {e}")

    def create_test(
        self,
        name: str,
        variants: List[str],
        weights: List[float] = None,
        duration_hours: int = 24,
    ) -> str:
        if weights is None:
            weights = [1.0 / len(variants)] * len(variants)

        if len(weights) != len(variants):
            raise ValueError("Weights must match variants count")

        if abs(sum(weights) - 1.0) > 0.01:
            raise ValueError("Weights must sum to 1.0")

        test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test = ABTest(
            test_id=test_id,
            name=name,
            variants=variants,
            weights=weights,
            start_time=datetime.now().isoformat(),
            status="active",
        )

        self.active_tests[test_id] = test
        self.save_tests()

        merlin_logger.info(
            f"Created A/B test '{name}': {variants} with weights {weights}"
        )

        return test_id

    def get_variant(self, test_id: str) -> Optional[str]:
        if test_id not in self.active_tests:
            return None

        test = self.active_tests[test_id]
        return test.get_variant_for_request()

    def record_result(
        self,
        test_id: str,
        variant: str,
        user_rating: Optional[int] = None,
        latency: float = 0.0,
        success: bool = True,
    ):
        if test_id not in self.active_tests:
            return

        test = self.active_tests[test_id]
        test.add_metric(variant, user_rating, latency, success)
        self.save_tests()

        merlin_logger.info(f"Recorded result for test {test_id}, variant {variant}")

    def complete_test(self, test_id: str) -> Optional[Dict]:
        if test_id not in self.active_tests:
            return None

        test = self.active_tests[test_id]
        test.status = "completed"
        test.end_time = datetime.now().isoformat()

        winner = test.get_winner()

        self.test_history.append(test)
        del self.active_tests[test_id]
        self.save_tests()

        merlin_logger.info(
            f"Completed test '{test.name}'. Winner: {winner.get('variant') if winner else 'None'}"
        )

        return winner

    def get_test_status(self, test_id: str) -> Optional[Dict]:
        if test_id not in self.active_tests:
            return None

        test = self.active_tests[test_id]

        variant_stats = {
            variant: test.get_variant_stats(variant) for variant in test.variants
        }

        return {
            "test_id": test_id,
            "name": test.name,
            "status": test.status,
            "variants": test.variants,
            "weights": test.weights,
            "start_time": test.start_time,
            "end_time": test.end_time,
            "duration_hours": self._get_duration_hours(test),
            "variant_stats": variant_stats,
            "winner": test.get_winner(),
        }

    def _get_duration_hours(self, test: ABTest) -> float:
        if test.end_time is None:
            return (
                datetime.now() - datetime.fromisoformat(test.start_time)
            ).total_seconds() / 3600
        return (
            datetime.fromisoformat(test.end_time)
            - datetime.fromisoformat(test.start_time)
        ).total_seconds() / 3600

    def list_active_tests(self) -> List[Dict]:
        return [
            {
                "test_id": test.test_id,
                "name": test.name,
                "variants": test.variants,
                "weights": test.weights,
                "status": test.status,
                "start_time": test.start_time,
                "variant_stats": {
                    variant: test.get_variant_stats(variant)
                    for variant in test.variants
                },
            }
            for test in self.active_tests.values()
        ]

    def get_summary(self) -> Dict:
        all_tests = list(self.active_tests.values()) + self.test_history

        total_tests = len(all_tests)
        completed_tests = len([t for t in all_tests if t.status == "completed"])

        best_performers: Dict[str, int] = defaultdict(int)
        for test in self.test_history:
            winner = test.get_winner()
            if winner:
                best_performers[winner["variant"]] += 1

        return {
            "total_tests": total_tests,
            "active_tests": len(self.active_tests),
            "completed_tests": completed_tests,
            "variant_winners": dict(best_performers),
        }


ab_testing_manager = ABTestingManager()
