"""
Repair Utilities for Critic Loop.

Provides advanced repair strategies that can augment the Leadership domain's
built-in repair mechanisms (_repair_faster_tier, _repair_heavier_tier, etc).

These utilities enable sophisticated retry logic with different model tiers,
context management, and escalation patterns.
"""

import json
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RepairAttempt:
    """Record of a single repair attempt"""
    attempt_number: int
    strategy: str
    timestamp: str
    result_status: str
    duration: float
    error: Optional[str] = None


class RepairExecutor:
    """High-level repair orchestration"""
    
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.attempt_history = []
    
    async def execute_repair(
        self,
        subtask_id: str,
        execution_output: Dict[str, Any],
        validation_issues: list[str],
        nc,
        strategy: str = "auto"
    ) -> Dict[str, Any]:
        """
        Execute a repair attempt.
        
        Args:
            subtask_id: ID of failed subtask
            execution_output: Original execution output
            validation_issues: List of validation issues
            nc: NATS connection
            strategy: Repair strategy to use ("auto" for selection)
            
        Returns:
            Repair result with new execution output and metadata
        """
        
        if strategy == "auto":
            strategy = self._select_strategy(validation_issues)
        
        attempt_num = len(self.attempt_history) + 1
        
        if attempt_num > self.max_attempts:
            return {
                "status": "failed",
                "reason": f"Exceeded max repair attempts ({self.max_attempts})",
                "strategy": strategy,
                "attempt": attempt_num
            }
        
        result = await self._execute_strategy(strategy, execution_output, nc)
        
        # Record attempt
        attempt = RepairAttempt(
            attempt_number=attempt_num,
            strategy=strategy,
            timestamp=datetime.utcnow().isoformat(),
            result_status=result.get("status", "unknown"),
            duration=result.get("duration", 0),
            error=result.get("error")
        )
        self.attempt_history.append(attempt)
        
        return {
            "status": "attempted",
            "strategy": strategy,
            "attempt": attempt_num,
            "result": result,
            "attempts_remaining": self.max_attempts - attempt_num
        }
    
    def _select_strategy(self, issues: list[str]) -> str:
        """Select best strategy based on issues"""
        issue_text = " ".join(issues).lower()
        
        if "slow" in issue_text or "timeout" in issue_text:
            return "faster_tier"
        elif "incomplete" in issue_text or "missing" in issue_text:
            return "more_context"
        elif "memory" in issue_text or "oom" in issue_text:
            return "smaller_context"
        elif "policy" in issue_text or "permission" in issue_text:
            return "escalate"
        else:
            return "heavier_tier"
    
    async def _execute_strategy(
        self,
        strategy: str,
        execution_output: Dict[str, Any],
        nc
    ) -> Dict[str, Any]:
        """Execute specific repair strategy"""
        
        if strategy == "faster_tier":
            return await self._strategy_faster_tier(execution_output)
        elif strategy == "heavier_tier":
            return await self._strategy_heavier_tier(execution_output)
        elif strategy == "more_context":
            return await self._strategy_more_context(execution_output)
        elif strategy == "smaller_context":
            return await self._strategy_smaller_context(execution_output)
        elif strategy == "exponential_backoff":
            return await self._strategy_exponential_backoff(execution_output)
        elif strategy == "escalate":
            return {"status": "escalated", "message": "Escalated to Fortress for policy review"}
        else:
            return {"status": "unknown_strategy", "strategy": strategy}
    
    async def _strategy_faster_tier(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retry with fast, lightweight model tier.
        Reduces context window and timeout.
        """
        return {
            "status": "retry_prepared",
            "tier": "tier_1_local",
            "max_tokens": 256,
            "timeout": 30,
            "hint": "Using fast, local model for rapid retry"
        }
    
    async def _strategy_heavier_tier(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retry with heavy, capable model tier.
        Uses full context window and longer timeout.
        """
        return {
            "status": "retry_prepared",
            "tier": "tier_3_heavy",
            "max_tokens": 2048,
            "timeout": 90,
            "hint": "Using heavy model (GPT-4/Claude) for complex reasoning"
        }
    
    async def _strategy_more_context(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retry with doubled context window.
        Useful for incomplete outputs.
        """
        original_tokens = output.get("max_tokens", 1024)
        new_tokens = min(original_tokens * 2, 4096)
        
        return {
            "status": "retry_prepared",
            "max_tokens": new_tokens,
            "timeout": 60,
            "hint": f"Doubled context: {original_tokens} → {new_tokens} tokens"
        }
    
    async def _strategy_smaller_context(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retry with reduced context window.
        Useful when hitting memory limits.
        """
        original_tokens = output.get("max_tokens", 1024)
        new_tokens = max(original_tokens // 2, 256)
        
        return {
            "status": "retry_prepared",
            "max_tokens": new_tokens,
            "timeout": 30,
            "hint": f"Reduced context: {original_tokens} → {new_tokens} tokens"
        }
    
    async def _strategy_exponential_backoff(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wait with exponential backoff before retry.
        Useful for rate-limited or overloaded services.
        """
        attempt = len(self.attempt_history)
        delay = min(2 ** attempt, 300)  # Cap at 5 minutes
        
        return {
            "status": "backoff_scheduled",
            "delay_seconds": delay,
            "hint": f"Exponential backoff: waiting {delay}s before retry"
        }
    
    def get_attempt_summary(self) -> Dict[str, Any]:
        """Get summary of all repair attempts"""
        return {
            "total_attempts": len(self.attempt_history),
            "max_attempts": self.max_attempts,
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "strategy": a.strategy,
                    "result": a.result_status,
                    "duration": a.duration,
                    "timestamp": a.timestamp
                }
                for a in self.attempt_history
            ]
        }


class ContextAdjustment:
    """Context window and memory management"""
    
    @staticmethod
    def calculate_optimal_context(
        target_agent: str,
        complexity_level: str = "medium",
        available_memory_mb: int = 8192
    ) -> int:
        """
        Calculate optimal context window based on agent and constraints.
        
        Args:
            target_agent: Agent tier (tier_1_local, tier_2_fast, tier_3_heavy)
            complexity_level: Task complexity (simple, medium, complex)
            available_memory_mb: Available VRAM/RAM in MB
            
        Returns:
            Recommended max_tokens
        """
        
        complexity_multipliers = {
            "simple": 0.5,
            "medium": 1.0,
            "complex": 2.0
        }
        
        tier_limits = {
            "tier_1_local": 2048,      # Fast, limited
            "tier_2_fast": 4096,       # Balanced
            "tier_3_heavy": 16384      # Capable, slow
        }
        
        base_tokens = tier_limits.get(target_agent, 2048)
        multiplier = complexity_multipliers.get(complexity_level, 1.0)
        
        # Adjust for available memory
        if available_memory_mb < 4096:
            multiplier *= 0.5
        elif available_memory_mb > 16384:
            multiplier *= 1.5
        
        optimal = int(base_tokens * multiplier)
        max_allowed = tier_limits.get(target_agent, 2048)
        
        return min(optimal, max_allowed)
    
    @staticmethod
    def suggest_context_reduction(
        failed_due_to: str,
        current_context: int
    ) -> Dict[str, Any]:
        """
        Suggest context reduction based on failure reason.
        
        Args:
            failed_due_to: Reason for failure (timeout, oom, etc)
            current_context: Current max_tokens
            
        Returns:
            Reduction suggestion
        """
        
        if "timeout" in failed_due_to.lower():
            reduction_factor = 0.75
            reason = "Timeout - reducing for faster completion"
        elif "memory" in failed_due_to.lower() or "oom" in failed_due_to.lower():
            reduction_factor = 0.5
            reason = "Out of memory - significant reduction needed"
        else:
            reduction_factor = 0.8
            reason = "General failure - modest reduction"
        
        new_context = max(int(current_context * reduction_factor), 256)
        
        return {
            "current_tokens": current_context,
            "suggested_tokens": new_context,
            "reduction_factor": reduction_factor,
            "reason": reason
        }


class EscalationPath:
    """Policy escalation and manual review handling"""
    
    @staticmethod
    async def escalate_to_fortress(
        subtask_id: str,
        validation_issues: list[str],
        execution_output: Dict[str, Any],
        nc
    ) -> Dict[str, Any]:
        """
        Escalate failed subtask to Fortress domain for policy review.
        
        Args:
            subtask_id: Failed subtask ID
            validation_issues: What went wrong
            execution_output: Original execution output
            nc: NATS connection
            
        Returns:
            Escalation result
        """
        
        escalation_ticket = {
            "subtask_id": subtask_id,
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "high",
            "issues": validation_issues,
            "execution_output_snippet": str(execution_output)[:500],
            "action_required": "policy_review"
        }
        
        # Route to Fortress for review
        try:
            response = await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_fortress_policy_evaluate",
                json.dumps({
                    "operation": "escalated_review",
                    "ticket": escalation_ticket
                }).encode(),
                timeout=30.0
            )
            
            result = json.loads(response.data.decode())
            return {
                "status": "escalated",
                "ticket_id": subtask_id,
                "fortress_response": result
            }
        
        except Exception as e:
            return {
                "status": "escalation_failed",
                "error": str(e),
                "fallback": "marked_for_manual_review"
            }
