# Cost Optimization Manager - Minimizing LLM API Expenses
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from merlin_logger import merlin_logger
from merlin_predictive_selection import predictive_model_selector


@dataclass
class ModelPricing:
    model_name: str
    input_cost_per_1k: float  # Cost per 1K input tokens
    output_cost_per_1k: float  # Cost per 1K output tokens
    currency: str = "USD"
    free_tier_limit: Optional[int] = None  # Tokens per month
    tier_name: Optional[str] = None  # Free, Pro, Enterprise


@dataclass
class UsageMetrics:
    model_name: str
    date: str  # YYYY-MM-DD
    requests: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    avg_cost_per_request: float
    cost_efficiency_score: float  # Lower is better


class CostOptimizationManager:
    def __init__(self):
        self.pricing_file = "artifacts/model_pricing.json"
        self.usage_file = "artifacts/model_usage.json"
        self.optimization_log_file = "artifacts/cost_optimization_log.json"

        self.model_pricing: Dict[str, ModelPricing] = {}
        self.daily_usage: Dict[str, List[UsageMetrics]] = defaultdict(list)

        self.budget_limit: float = float(os.getenv("MONTHLY_BUDGET_LIMIT", "100.0"))
        self.cost_thresholds = {
            "warning": float(
                os.getenv("COST_WARNING_THRESHOLD", "70.0")
            ),  # 70% of budget
            "critical": float(
                os.getenv("COST_CRITICAL_THRESHOLD", "90.0")
            ),  # 90% of budget
        }

        self.load_pricing()
        self.load_usage()
        self.cleanup_old_usage()

        merlin_logger.info(
            f"Cost Optimization Manager: {len(self.model_pricing)} models, budget: ${self.budget_limit}"
        )

    def load_pricing(self):
        if os.path.exists(self.pricing_file):
            try:
                with open(self.pricing_file, "r") as f:
                    data = json.load(f)
                    for model_name, pricing in data.get("models", {}).items():
                        self.model_pricing[model_name] = ModelPricing(**pricing)
                merlin_logger.info(
                    f"Loaded pricing for {len(self.model_pricing)} models"
                )
            except Exception as e:
                merlin_logger.error(f"Failed to load pricing: {e}")

    def load_usage(self):
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, "r") as f:
                    data = json.load(f)
                    for model_name, usage_list in data.get("daily_usage", {}).items():
                        self.daily_usage[model_name] = [
                            UsageMetrics(**usage) for usage in usage_list
                        ]
                merlin_logger.info(
                    f"Loaded usage data for {len(self.daily_usage)} models"
                )
            except Exception as e:
                merlin_logger.error(f"Failed to load usage: {e}")

    def cleanup_old_usage(self):
        cutoff_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        for model_name in list(self.daily_usage.keys()):
            self.daily_usage[model_name] = [
                usage
                for usage in self.daily_usage[model_name]
                if usage.date >= cutoff_date
            ]

        self.save_usage()
        merlin_logger.info(f"Cleaned up usage data older than {cutoff_date}")

    def record_usage(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = None,
    ):
        if model_name not in self.model_pricing:
            merlin_logger.warning(f"No pricing data for model: {model_name}")
            return

        pricing = self.model_pricing[model_name]
        input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k
        total_cost = input_cost + output_cost

        today = datetime.now().strftime("%Y-%m-%d")

        existing = [u for u in self.daily_usage[model_name] if u.date == today]
        if existing:
            existing[0].requests += 1
            existing[0].input_tokens += input_tokens
            existing[0].output_tokens += output_tokens
            existing[0].total_cost += total_cost
            existing[0].avg_cost_per_request = (
                existing[0].total_cost / existing[0].requests
            )
        else:
            self.daily_usage[model_name].append(
                UsageMetrics(
                    model_name=model_name,
                    date=today,
                    requests=1,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_cost=total_cost,
                    avg_cost_per_request=total_cost,
                    cost_efficiency_score=self.calculate_cost_efficiency(
                        total_cost, input_tokens + output_tokens
                    ),
                )
            )

        self.save_usage()
        self.check_budget_alerts()

        merlin_logger.info(
            f"Recorded usage: {model_name}, {input_tokens}+{output_tokens} tokens, ${total_cost:.4f}"
        )

    def calculate_cost_efficiency(self, total_cost: float, total_tokens: int) -> float:
        if total_cost == 0 or total_tokens == 0:
            return 1.0

        cost_per_1k_tokens = total_cost / (total_tokens / 1000)

        efficiency_score = 0.0
        if cost_per_1k_tokens <= 0.01:  # Very cheap (< $0.01/1K tokens)
            efficiency_score = 1.0
        elif cost_per_1k_tokens <= 0.05:  # Cheap (< $0.05/1K tokens)
            efficiency_score = 0.8
        elif cost_per_1k_tokens <= 0.10:  # Moderate
            efficiency_score = 0.6
        elif cost_per_1k_tokens <= 0.20:  # Expensive
            efficiency_score = 0.4
        else:  # Very expensive (> $0.20/1K tokens)
            efficiency_score = 0.2

        return efficiency_score

    def check_budget_alerts(self):
        today = datetime.now().strftime("%Y-%m-%d")
        today_costs = {}

        for model_name, usage_list in self.daily_usage.items():
            today_data = [u for u in usage_list if u.date == today]
            if today_data:
                total_cost = sum(u.total_cost for u in today_data)
                today_costs[model_name] = total_cost

        total_spend = sum(today_costs.values())

        if total_spend > 0:
            budget_percentage = (total_spend / self.budget_limit) * 100

            if budget_percentage >= self.cost_thresholds["critical"]:
                self.log_optimization_event(
                    "budget_critical",
                    {
                        "total_spend": total_spend,
                        "budget_limit": self.budget_limit,
                        "percentage": budget_percentage,
                    },
                )
            elif budget_percentage >= self.cost_thresholds["warning"]:
                self.log_optimization_event(
                    "budget_warning",
                    {
                        "total_spend": total_spend,
                        "budget_limit": self.budget_limit,
                        "percentage": budget_percentage,
                    },
                )

    def get_cost_optimization_recommendation(self) -> Dict:
        today = datetime.now().strftime("%Y-%m-%d")
        today_usage = {
            model_name: [u for u in usage_list if u.date == today]
            for model_name, usage_list in self.daily_usage.items()
        }

        recommendations = {
            "switch_to_free_model": False,
            "reduce_usage": False,
            "adjust_thresholds": False,
            "schedule_review": False,
        }

        model_costs = {}
        for model_name, usage_list in today_usage.items():
            today_data = [u for u in usage_list if u.date == today]
            if today_data:
                model_costs[model_name] = sum(u.total_cost for u in today_data)

        total_spend = sum(model_costs.values())

        if total_spend > self.budget_limit * 0.9:
            recommendations["switch_to_free_model"] = True

        highest_cost_model = (
            max(model_costs.items(), key=lambda x: x[1]) if model_costs else (None, 0)
        )
        lowest_cost_model = (
            min(model_costs.items(), key=lambda x: x[1]) if model_costs else (None, 0)
        )

        if highest_cost_model and lowest_cost_model:
            ratio = highest_cost_model[1] / lowest_cost_model[1]
            if ratio > 2.0:
                recommendations["reduce_usage"] = True

        avg_cost = sum(model_costs.values()) / len(model_costs) if model_costs else 0
        if avg_cost > 5.0:  # Average cost > $5 per request
            recommendations["adjust_thresholds"] = True

        if len([u for ulist in self.daily_usage.values() for u in ulist]) > 1000:
            recommendations["schedule_review"] = True

        return recommendations

    def log_optimization_event(self, event_type: str, data: Dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data,
        }

        try:
            with open(self.optimization_log_file, "a") as f:
                json.dump(event, f)
                f.write("\n")
        except Exception as e:
            merlin_logger.error(f"Failed to log optimization event: {e}")

    def get_cost_report(self, days: int = 30) -> Dict[str, Any]:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        report_data: Dict[str, Any] = {
            "period_days": days,
            "start_date": cutoff_date,
            "end_date": datetime.now().strftime("%Y-%m-%d"),
            "budget_limit": self.budget_limit,
            "total_spend": 0.0,
            "model_breakdown": {},
            "daily_average": {},
            "recommendations": [],
        }

        total_spend = 0.0

        for model_name, usage_list in self.daily_usage.items():
            recent = [u for u in usage_list if u.date >= cutoff_date]

            if recent:
                model_total = sum(u.total_cost for u in recent)
                model_avg = model_total / len(recent)

                total_spend += model_total

                report_data["model_breakdown"][model_name] = {
                    "total_cost": model_total,
                    "avg_cost_per_request": model_avg,
                    "requests": len(recent),
                    "avg_tokens_per_request": (
                        sum(u.input_tokens + u.output_tokens for u in recent)
                        / len(recent)
                    ),
                }

                report_data["daily_average"][model_name] = model_avg

        report_data["total_spend"] = total_spend
        report_data["recommendations"] = self.get_cost_optimization_recommendation()

        return report_data

    def get_monthly_summary(self, year: int, month: int) -> Dict[str, Any]:
        pattern = f"{year}-{month:02d}-"

        summary: Dict[str, Any] = {
            "year": year,
            "month": month,
            "model_breakdown": {},
            "total_spend": 0.0,
            "daily_breakdown": [],
        }

        for model_name, usage_list in self.daily_usage.items():
            monthly_data = [u for u in usage_list if u.date.startswith(pattern)]

            if monthly_data:
                model_total = sum(u.total_cost for u in monthly_data)
                summary["model_breakdown"][model_name] = model_total
                summary["total_spend"] += model_total

                daily_summary = {}
                for day in range(1, 32):
                    day_pattern = f"{year}-{month:02d}-{day:02d}-"
                    day_data = [u for u in monthly_data if u.date == day_pattern]

                    if day_data:
                        daily_summary[f"day_{day:02d}"] = sum(
                            u.total_cost for u in day_data
                        )
                    else:
                        daily_summary[f"day_{day:02d}"] = 0.0

                summary["daily_breakdown"].append(
                    {"model": model_name, "daily": daily_summary}
                )

        return summary

    def save_usage(self):
        data = {
            "daily_usage": {
                model_name: [
                    {
                        "date": u.date,
                        "requests": u.requests,
                        "input_tokens": u.input_tokens,
                        "output_tokens": u.output_tokens,
                        "total_cost": u.total_cost,
                        "avg_cost_per_request": u.avg_cost_per_request,
                        "cost_efficiency_score": u.cost_efficiency_score,
                    }
                    for u in usage_list
                ]
                for model_name, usage_list in self.daily_usage.items()
            },
            "last_updated": datetime.now().isoformat(),
        }

        try:
            os.makedirs(os.path.dirname(self.usage_file), exist_ok=True)
            with open(self.usage_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save usage data: {e}")

    def save_pricing(self, pricing_data: Dict[str, dict]):
        data = {"models": pricing_data, "last_updated": datetime.now().isoformat()}

        try:
            os.makedirs(os.path.dirname(self.pricing_file), exist_ok=True)
            with open(self.pricing_file, "w") as f:
                json.dump(data, f, indent=2)
            merlin_logger.info(f"Saved pricing for {len(pricing_data)} models")
        except Exception as e:
            merlin_logger.error(f"Failed to save pricing data: {e}")


cost_optimization_manager = CostOptimizationManager()
