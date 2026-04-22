"""
Validation Utilities for Critic Loop.

Provides enhanced validation checks that can be optionally integrated
into the Leadership domain's _validate_execution method.

These are supplements to the inline validation in leadership.py.
"""

import json
from typing import Dict, Any, List
from datetime import datetime


class AdvancedValidationChecks:
    """Advanced validation checks beyond basic correctness/completeness"""
    
    @staticmethod
    def check_response_format(output: Dict[str, Any], expected_schema: Dict[str, Any] = None) -> tuple[bool, List[str]]:
        """
        Validate output against expected schema.
        
        Args:
            output: Execution output to validate
            expected_schema: Optional Pydantic model or dict schema
            
        Returns:
            (passed, issues)
        """
        issues = []
        
        # Check for required fields
        required_fields = ["status", "result", "duration"]
        for field in required_fields:
            if field not in output:
                issues.append(f"Missing required field: {field}")
        
        # Check status is valid
        valid_statuses = ["success", "partial", "warning", "error", "timeout"]
        if output.get("status") not in valid_statuses:
            issues.append(f"Invalid status: {output.get('status')}. Must be one of {valid_statuses}")
        
        passed = len(issues) == 0
        return passed, issues
    
    @staticmethod
    def check_performance(output: Dict[str, Any], max_duration: float = 120.0) -> tuple[bool, List[str]]:
        """
        Check execution performance metrics.
        
        Args:
            output: Execution output
            max_duration: Maximum acceptable duration in seconds
            
        Returns:
            (passed, issues)
        """
        issues = []
        
        duration = output.get("duration", 0)
        if duration > max_duration:
            issues.append(f"Execution exceeds max duration: {duration:.1f}s > {max_duration}s")
        elif duration > max_duration * 0.8:
            issues.append(f"Execution approaching max duration: {duration:.1f}s")
        
        passed = len(issues) == 0
        return passed, issues
    
    @staticmethod
    def check_error_patterns(output: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Check for known error patterns and anti-patterns.
        
        Args:
            output: Execution output
            
        Returns:
            (passed, issues)
        """
        issues = []
        
        error_msg = str(output.get("error", "")).lower()
        result_msg = str(output.get("result", "")).lower()
        
        # Check for common error patterns
        critical_patterns = [
            ("permission denied", "Security violation"),
            ("unauthorized", "Authorization failure"),
            ("forbidden", "Access forbidden"),
            ("rate limit", "Rate limit exceeded"),
            ("connection refused", "Service unavailable"),
        ]
        
        for pattern, description in critical_patterns:
            if pattern in error_msg or pattern in result_msg:
                issues.append(f"Critical pattern detected: {description}")
        
        # Check for recovery needed patterns
        recovery_patterns = [
            ("timeout", "Timeout - retry with longer window"),
            ("out of memory", "OOM - retry with smaller context"),
            ("model overloaded", "Service busy - retry later"),
        ]
        
        for pattern, hint in recovery_patterns:
            if pattern in error_msg or pattern in result_msg:
                issues.append(f"Recovery hint: {hint}")
        
        passed = len([i for i in issues if "Critical" in i]) == 0
        return passed, issues
    
    @staticmethod
    def check_coherence(output: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Check semantic coherence of output.
        Detects contradictions or nonsensical results.
        
        Args:
            output: Execution output
            
        Returns:
            (passed, issues)
        """
        issues = []
        
        # Basic coherence checks
        status = output.get("status", "")
        result = output.get("result", "")
        error = output.get("error", "")
        
        # Contradiction checks
        if status == "success" and error:
            issues.append("Contradiction: Status is 'success' but error is present")
        
        if status == "error" and not error:
            issues.append("Incoherence: Status is 'error' but no error message provided")
        
        # Check for empty/null results when success claimed
        if status == "success" and not result:
            issues.append("Incomplete: Success claimed but result is empty")
        
        passed = len(issues) == 0
        return passed, issues
    
    @staticmethod
    def compile_validation_report(output: Dict[str, Any], checks: List[str] = None) -> Dict[str, Any]:
        """
        Compile a comprehensive validation report.
        
        Args:
            output: Execution output
            checks: List of check names to run (default: all)
            
        Returns:
            Validation report dict
        """
        if checks is None:
            checks = ["format", "performance", "errors", "coherence"]
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks_run": [],
            "passed_checks": [],
            "failed_checks": [],
            "all_issues": [],
            "overall_passed": True
        }
        
        check_methods = {
            "format": AdvancedValidationChecks.check_response_format,
            "performance": AdvancedValidationChecks.check_performance,
            "errors": AdvancedValidationChecks.check_error_patterns,
            "coherence": AdvancedValidationChecks.check_coherence,
        }
        
        for check_name in checks:
            if check_name not in check_methods:
                continue
            
            report["checks_run"].append(check_name)
            passed, issues = check_methods[check_name](output)
            
            if passed:
                report["passed_checks"].append(check_name)
            else:
                report["failed_checks"].append(check_name)
                report["all_issues"].extend(issues)
                report["overall_passed"] = False
        
        return report


class RepairStrategy:
    """Repair strategy selection based on validation results"""
    
    @staticmethod
    def select_strategy(issues: List[str]) -> str:
        """
        Select best repair strategy based on validation issues.
        
        Args:
            issues: List of validation issues
            
        Returns:
            Strategy name
        """
        issue_text = " ".join(issues).lower()
        
        # Priority-ordered strategy selection
        if "timeout" in issue_text or "slow" in issue_text:
            return "retry_with_faster_tier"
        elif "rate limit" in issue_text or "overload" in issue_text:
            return "retry_with_exponential_backoff"
        elif "permission" in issue_text or "unauthorized" in issue_text:
            return "escalate_to_fortress"
        elif "out of memory" in issue_text or "context" in issue_text:
            return "retry_with_smaller_context"
        elif "incomplete" in issue_text:
            return "retry_with_more_context"
        else:
            return "retry_with_heavier_tier"
    
    @staticmethod
    def get_strategy_description(strategy: str) -> Dict[str, Any]:
        """Get description and parameters for a strategy"""
        strategies = {
            "retry_with_faster_tier": {
                "description": "Use lightweight, fast model tier",
                "priority": "immediate",
                "max_retries": 1,
                "timeout": 30
            },
            "retry_with_heavier_tier": {
                "description": "Use heavyweight, capable model tier",
                "priority": "elevated",
                "max_retries": 2,
                "timeout": 60
            },
            "retry_with_more_context": {
                "description": "Increase context window and retry",
                "priority": "elevated",
                "max_retries": 1,
                "timeout": 90
            },
            "retry_with_smaller_context": {
                "description": "Reduce context to fit in memory",
                "priority": "urgent",
                "max_retries": 1,
                "timeout": 30
            },
            "retry_with_exponential_backoff": {
                "description": "Wait and retry with exponential backoff",
                "priority": "deferred",
                "max_retries": 3,
                "initial_delay": 5
            },
            "escalate_to_fortress": {
                "description": "Escalate to security/policy review",
                "priority": "critical",
                "max_retries": 0,
                "timeout": 0
            }
        }
        
        return strategies.get(strategy, {})
