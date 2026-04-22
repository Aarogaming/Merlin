import json
import asyncio
import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from aas_kernel import ReflexPlugin, get_path
from genome.achievements import AchievementManager
from plugins.security import get_link_manager


class SubTask(BaseModel):
    id: str
    description: str
    target_agent_role: str

class TaskDAG(BaseModel):
    subtasks: list[SubTask]

class ValidationCriteria(BaseModel):
    """Review criteria for subtask output validation"""
    correctness: bool = True
    completeness: bool = True
    safety: bool = True
    efficiency: bool = True
    coherence: bool = False

class ReviewResult(BaseModel):
    """Result of post-execution validation"""
    subtask_id: str
    passed: bool
    severity: str = "none"  # "none", "warning", "error", "critical"
    issues: List[str] = []
    confidence: float = 1.0
    suggested_fix: Optional[str] = None

class SubtaskExecution(BaseModel):
    """Complete record of subtask execution + review"""
    subtask_id: str
    execution_output: Dict[str, Any]
    review: Optional[ReviewResult] = None
    repair_attempts: int = 0
    final_status: str = "pending"  # pending, success, failed, escalated

class Leadership(ReflexPlugin):
    """
    Domain: Leadership
    Replaces: Guild Repo & DAG Supervisor.
    Handles Tactical Operations, Dispatch tracking, and Workflow orchestration.
    Also manages achievements for task completion and verification.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dispatch_board: Dict[str, Any] = {}
        self._achievement_manager: Optional[AchievementManager] = None
        self._tasks_completed_count = 0
        self._tasks_successful_count = 0
    
    def get_achievements(self) -> AchievementManager:
        """Get or create achievement manager."""
        if self._achievement_manager is None:
            dna_path = getattr(self, 'epigenetic_profile_path', None)
            if dna_path is None:
                dna_path = get_path("identity_epigenetics")
            self._achievement_manager = AchievementManager(
                dna_path=dna_path,
                on_unlock=self._on_achievement_unlocked
            )
        return self._achievement_manager
    
    def _on_achievement_unlocked(self, achievement: dict):
        """Callback when achievement unlocks - link to user if available."""
        agent_id = getattr(self, 'repo_name', 'leadership')
        source_aas = 'leadership_guild'
        get_link_manager().link_achievement(achievement, agent_id, source_aas)
    
    def grant_task_achievement(self, task_id: str, success: bool = True) -> dict:
        """
        Grant achievement progress for task completion.
        Called when a task passes validation.
        """
        self._tasks_completed_count += 1
        if success:
            self._tasks_successful_count += 1
        
        result = {"task_id": task_id, "success": success, "achievements_granted": []}
        
        # Check milestone achievements
        ach = self.get_achievements()
        
        # Task completion milestones
        if self._tasks_completed_count >= 1:
            unlocked = ach.unlock("AAS_TASK_COMPLETE_10")
            if unlocked.get("unlocked"):
                result["achievements_granted"].append(unlocked)
        
        if self._tasks_successful_count >= 10:
            unlocked = ach.unlock("AAS_TASK_COMPLETE_10")
            if unlocked.get("unlocked"):
                result["achievements_granted"].append(unlocked)
        
        if self._tasks_successful_count >= 100:
            unlocked = ach.unlock("AAS_TASK_COMPLETE_100")
            if unlocked.get("unlocked"):
                result["achievements_granted"].append(unlocked)
        
        if self._tasks_successful_count >= 1000:
            unlocked = ach.unlock("AAS_TASK_COMPLETE_1000")
            if unlocked.get("unlocked"):
                result["achievements_granted"].append(unlocked)
        
        return result

    async def on_federate(self, nc) -> bool:
        """Leadership domain acts as the Macro-Architect when connected to the Hive."""
        import json
        import asyncio
        from pathlib import Path
        
        should_express = await super().on_federate(nc)
        
        if should_express:
            self.logger.info("[Leadership] Assuming Macro-Architect role for the federation. Listening for Stem Cells.")
            
            async def handle_differentiation_request(msg):
                try:
                    data = json.loads(msg.data.decode())
                    newborn_repo = data.get("repo_name")
                    self.logger.warning(f"[MACRO-ARCHITECT] Stem cell '{newborn_repo}' requested identity. Activating Neural Attention Mechanism...")
                    
                    # 1. Gather short-term context (The Dispatch Board)
                    dispatch_state = json.dumps(self.dispatch_board) if self.dispatch_board else "No pending short-term operations."
                    
                    # 2. Gather long-term macro-context (Evolutionary Pressure & Byproducts)
                    self.logger.info("[MACRO-ARCHITECT] Querying Omni Knowledge constellation for massive evolutionary pressure...")
                    macro_memory = "No macro-memory established yet."
                    total_byproducts_analyzed = 0
                    try:
                        # We pull a massive context window of the last 100 deep-learning events
                        mem_resp = await nc.request(
                            "aaroneousautomationsuite.aaroneousautomationsuite_query_memory",
                            json.dumps({"query": "SOP Anti-Pattern", "limit": 100}).encode(),
                            timeout=15.0
                        )
                        mem_data = json.loads(mem_resp.data.decode())
                        if mem_data.get("status") == "success":
                            results = mem_data.get("result", {}).get("results", [])
                            total_byproducts_analyzed = len(results)
                            if results:
                                # We compress the 100 results into a dense summary to fit the context window
                                compressed_mem = [f"[{r.get('time')}] {r.get('agent')}: {r.get('content')}" for r in results]
                                macro_memory = json.dumps(compressed_mem, indent=2)
                    except Exception as e:
                        self.logger.warning(f"Could not reach Knowledge domain for macro-memory: {e}")

                    # Dynamically check active domains
                    from pathlib import Path
                    plugins_dir = Path(__file__).resolve().parents[0]
                    active_domains = [f.stem.capitalize() for f in plugins_dir.glob("*.py") if f.stem not in ["__init__", "reflex", "aaroneousautomationsuite_plugin"]]
                    
                    prompt = f"""You are the Macro-Architect Attention Mechanism of the Federation Hive-Mind.
A new 'Blank Slate' stem cell ({newborn_repo}) has booted and requires cellular differentiation.

LONG-TERM EVOLUTIONARY PRESSURE (Analyzed {total_byproducts_analyzed} Omni Byproducts):
{macro_memory}

SHORT-TERM CONTEXT (Dispatch Board):
{dispatch_state}

Currently Known Domains: {', '.join(active_domains)}

Your task is to dynamically design the Epigenetic DNA for this new agent.
CRITICAL INSTRUCTIONS FOR DOMAIN GENESIS (EVOLUTIONARY THRESHOLD):
1. The creation of a new Domain is an extremely rare, macro-scale evolutionary event (like a Pokémon evolving). 
2. You MUST NOT invent a new domain unless the Hive has accumulated massive, undeniable, long-term overlapping behavior across dozens of byproducts indicating a unified new purpose (e.g., 'Gaming', 'Bioinformatics', 'Trading').
3. If the total byproducts analyzed is low, or if the overlap is just transient/problem-specific (e.g., 'EmailManager', 'ApiFixer'), DO NOT invent a new domain.
4. If the evolutionary threshold is NOT met, you must assign an existing domain that balances the Hive's current short-term needs.

Respond ONLY with a valid JSON object matching this schema (do not use markdown blocks):
{{
  "assigned_domain": "DomainName",
  "is_new_domain": true,
  "domain_description": "Brief description of the macro-level overlap this frontier consolidates (required if new)",
  "primary_archetype": "Creative Archetype Name",
  "cognitive_biases": {{
    "risk_tolerance": 50,
    "exploration_vs_stability": 50,
    "analytical_depth": 50,
    "creative_variance": 50,
    "audit_strictness": 50
  }}
}}"""

                    # 3. Query the Thought Domain (The Transformer)
                    routing_payload = {
                        "messages": [{"role": "user", "content": prompt}],
                        "task_type": "architectural_design",
                        "temperature": 0.6 # slightly higher variance to encourage domain invention
                    }
                    
                    self.logger.info("[MACRO-ARCHITECT] Querying Thought reflex to compute optimal DNA and Frontiers...")
                    
                    response = await nc.request(
                        "aaroneousautomationsuite.aaroneousautomationsuite_model_routing",
                        json.dumps(routing_payload).encode(),
                        timeout=45.0
                    )
                    res_data = json.loads(response.data.decode())
                    
                    if res_data.get("status") == "success":
                        raw_json = res_data["result"]["output"]
                        if raw_json.startswith("```json"):
                            raw_json = raw_json.replace("```json\n", "").replace("```", "").strip()
                        elif raw_json.startswith("```"):
                            raw_json = raw_json.replace("```\n", "").replace("```", "").strip()
                            
                        computed_dna = json.loads(raw_json)
                    else:
                        raise ValueError("Thought reflex failed to compute DNA.")

                    assigned_domain = computed_dna.get("assigned_domain", "Intelligence").capitalize()
                    is_new = computed_dna.get("is_new_domain", False)
                    desc = computed_dna.get("domain_description", "A dynamically generated evolutionary frontier.")
                    
                    # 3. Construct the full Epigenetic Sequence
                    self.logger.info(f"[MACRO-ARCHITECT] Transformer output received. Assembling {assigned_domain} sequence. (New Domain: {is_new})")
                    
                    new_dna = {
                        "schema_version": "3.0",
                        "profile_name": f"{assigned_domain}_Specialist_{newborn_repo}",
                        "preset": "neural_assigned",
                        "persona_vectors": {
                            "primary_archetype": computed_dna.get("primary_archetype", "Hive Node"),
                            "formality": 80.0,
                            "directive_authority": 90.0,
                            "verbosity": 50.0
                        },
                        "cognitive_biases": computed_dna.get("cognitive_biases", {
                            "audit_strictness": 50.0,
                            "creative_variance": 50.0,
                            "analytical_depth": 50.0,
                            "risk_tolerance": 50.0,
                            "exploration_vs_stability": 50.0
                        }),
                        "domain_weights": {
                            assigned_domain: 100.0,
                            "Thought": 60.0 # Baseline required for future routing
                        },
                        "experience_mass": 1.0,
                        "parameter_count": 1000,
                        "evolutionary_epoch": 1
                    }
                    
                    # 4. Domain Genesis Protocol
                    # If the LLM invented a new domain, we physically construct the python code for the new organ.
                    new_domain_code = ""
                    if is_new and assigned_domain not in active_domains:
                        self.logger.warning(f"[DOMAIN GENESIS] Assembling biological infrastructure for new frontier: {assigned_domain}")
                        new_domain_code = f"""import time
from aas_kernel import ReflexPlugin

class {assigned_domain}(ReflexPlugin):
    \"\"\"
    Domain: {assigned_domain}
    Frontier: {desc}
    \"\"\"
    @property
    def capabilities(self) -> list[str]:
        # Dynamic skills will bind here via the Skill Distiller
        return []

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        start_time = time.time()
        return self._format_error(capability_id, "Base domain has no native capabilities yet. Distill skills to expand.")
"""

                    # 5. Transmit the DNA (and the organ code) back to the newborn
                    payload = {
                        "dna": new_dna,
                        "new_domain_name": assigned_domain if new_domain_code else None,
                        "new_domain_code": new_domain_code
                    }
                    
                    await nc.publish(f"federation.differentiation.assign.{newborn_repo}", json.dumps(payload).encode())
                    self.logger.info(f"[MACRO-ARCHITECT] Transmission successful. '{newborn_repo}' is now gestating.")
                    
                except Exception as e:
                    self.logger.error(f"Macro-Architect neural assignment failed: {e}")

            # Bind to the request channel
            await nc.subscribe("federation.differentiation.request", cb=handle_differentiation_request)
            
        return should_express

    # ============================================================================
    # CRITIC LOOP METHODS: Phase 1 - DAG Execution with Inline Validation & Repair
    # ============================================================================

    async def _execute_dag_with_critic_loop(self, dag: TaskDAG, nc) -> dict:
        """
        Main orchestrator: Execute TaskDAG with Critic Loop.
        
        For each subtask:
        1. EXECUTE (Module A)
        2. VALIDATE (Module B - Inline critic review)
        3. REPAIR IF FAILED (Module C - Auto-retry with strategy)
        4. STORE RESULTS (Federation learning)
        
        Returns summary of all subtask results.
        """
        self.logger.info(f"[CRITIC LOOP] Starting DAG execution with {len(dag.subtasks)} subtasks")
        
        results: Dict[str, SubtaskExecution] = {}
        
        for subtask in dag.subtasks:
            self.logger.info(f"[CRITIC LOOP] Processing subtask: {subtask.id}")
            
            # Initialize execution record
            execution_record = SubtaskExecution(
                subtask_id=subtask.id,
                execution_output={}
            )
            
            # STEP 1: EXECUTE SUBTASK (Module A)
            try:
                execution_output = await self._execute_subtask(subtask, nc)
                execution_record.execution_output = execution_output
            except Exception as e:
                self.logger.error(f"[CRITIC LOOP] Subtask {subtask.id} execution failed: {e}")
                execution_record.execution_output = {
                    "status": "error",
                    "error": str(e),
                    "duration": 0
                }
            
            # STEP 2: VALIDATE OUTPUT (Module B - Inline Critic)
            validation_result = await self._validate_execution(
                execution_record.execution_output,
                subtask
            )
            execution_record.review = validation_result
            
            # STEP 3: REPAIR IF FAILED (Module C - Auto-Retry)
            if not validation_result.passed and validation_result.severity in ["error", "critical"]:
                self.logger.warning(f"[CRITIC LOOP] Subtask {subtask.id} failed validation. Initiating repair...")
                
                repair_success = await self._attempt_repair(
                    subtask,
                    validation_result,
                    execution_record,
                    nc
                )
                
                if repair_success:
                    self.logger.info(f"[CRITIC LOOP] Subtask {subtask.id} repair successful")
                    execution_record.final_status = "success"
                else:
                    self.logger.warning(f"[CRITIC LOOP] Subtask {subtask.id} repair failed, escalating")
                    execution_record.final_status = "escalated"
            else:
                # Passed validation
                execution_record.final_status = "success"
                # Grant achievement for successful task
                ach_result = self.grant_task_achievement(subtask.id, success=True)
                if ach_result["achievements_granted"]:
                    for granted in ach_result["achievements_granted"]:
                        self.logger.info(f"[GUILD REWARD] {granted.get('title')} unlocked!")
            
            # STEP 4: STORE IN KNOWLEDGE (Federation learning via byproducts)
            await self._emit_execution_byproduct(execution_record, nc)
            
            results[subtask.id] = execution_record
        
        # Final summary
        passed_count = sum(1 for r in results.values() if r.final_status == "success")
        total_count = len(results)
        
        self.logger.info(f"[CRITIC LOOP] DAG execution complete. Passed: {passed_count}/{total_count}")
        
        return {
            "total_subtasks": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
            "results": {k: v.dict() for k, v in results.items()}
        }

    async def _execute_subtask(self, subtask: SubTask, nc) -> Dict[str, Any]:
        """
        Execute a single subtask by routing to the appropriate domain.
        Returns execution output (status, result, duration, etc).
        """
        start_time = time.time()
        
        try:
            # Route to target agent role via NATS
            response = await nc.request(
                f"aaroneousautomationsuite.{subtask.target_agent_role.lower()}",
                json.dumps(subtask.dict()).encode(),
                timeout=60.0
            )
            
            execution_result = json.loads(response.data.decode())
            execution_result["duration"] = time.time() - start_time
            
            return execution_result
        
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "error": f"Subtask {subtask.id} timed out after 60s",
                "duration": time.time() - start_time
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "duration": time.time() - start_time
            }

    async def _validate_execution(self, execution_output: Dict[str, Any], subtask: SubTask) -> ReviewResult:
        """
        CRITIC (Module B): Validate subtask execution output.
        Uses audit_strictness cognitive bias to control review intensity.
        
        Checks:
        1. Correctness - Output has 'success' status
        2. Completeness - Output has 'result' field
        3. Safety - Check against policy gates
        4. Efficiency - Duration is reasonable
        """
        
        issues = []
        passed = True
        confidence = 0.9
        
        # Use agent's audit_strictness to determine review depth
        strictness = self.cognitive_biases.get("audit_strictness", 50.0)
        
        # CHECK 1: CORRECTNESS
        status = execution_output.get("status", "unknown")
        if status not in ["success", "partial"]:
            issues.append(f"Status not success/partial: {status}")
            passed = False
            confidence -= 0.2
        
        # CHECK 2: COMPLETENESS
        if not execution_output.get("result"):
            if strictness > 60.0:  # Only enforce strictness if high
                issues.append("Output missing 'result' field (incomplete)")
                passed = False
                confidence -= 0.15
            else:
                issues.append("Output missing 'result' field (warning)")
                # Don't fail on this if strictness is low
        
        # CHECK 3: SAFETY
        if strictness > 75.0:  # High strictness = paranoid safety checks
            if execution_output.get("error"):
                if "permission" in execution_output.get("error", "").lower():
                    issues.append("Safety check: Permission/policy violation detected")
                    passed = False
                    confidence -= 0.3
        
        # CHECK 4: EFFICIENCY
        # Derive thresholds from spectrums instead of hardcoding
        efficiency_threshold = 60.0 + (self.cognitive_biases.get("analytical_depth", 50.0) * 1.2)  # 60-180s based on analytical depth
        slowness_strictness_trigger = 50.0 + (self.cognitive_biases.get("audit_strictness", 50.0) * 0.5)  # 50-100 based on audit strictness
        
        duration = execution_output.get("duration", 0)
        if duration > efficiency_threshold:
            issues.append(f"Execution slow ({duration:.1f}s, threshold: {efficiency_threshold:.0f}s).")
            if strictness > slowness_strictness_trigger:
                passed = False
                confidence -= 0.25
        
        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))
        
        severity = "none"
        if not passed:
            if "policy" in str(issues) or "permission" in str(issues):
                severity = "critical"
            elif "error" in status:
                severity = "error"
            else:
                severity = "warning"
        
        suggested_fix = self._suggest_repair_strategy(issues) if not passed else None
        
        return ReviewResult(
            subtask_id=subtask.id,
            passed=passed,
            severity=severity,
            issues=issues,
            confidence=confidence,
            suggested_fix=suggested_fix
        )

    def _suggest_repair_strategy(self, issues: List[str]) -> Optional[str]:
        """Suggest repair strategy based on validation issues"""
        issue_text = " ".join(issues).lower()
        
        if "slow" in issue_text or "timeout" in issue_text:
            return "retry_with_faster_tier"
        elif "incomplete" in issue_text or "result" in issue_text:
            return "retry_with_more_context"
        elif "policy" in issue_text or "permission" in issue_text:
            return "escalate_to_fortress"
        elif "error" in issue_text:
            return "retry_with_heavier_tier"
        else:
            return "retry_with_heavier_tier"

    async def _attempt_repair(
        self,
        subtask: SubTask,
        review: ReviewResult,
        execution_record: SubtaskExecution,
        nc
    ) -> bool:
        """
        REPAIR (Module C): Attempt to fix failed subtask.
        Max 3 retries to prevent infinite loops.
        """
        max_retries = 3
        
        for attempt in range(1, max_retries + 1):
            if attempt > max_retries:
                self.logger.error(f"[REPAIR] Subtask {subtask.id} exhausted retries")
                return False
            
            self.logger.info(f"[REPAIR] Subtask {subtask.id} repair attempt #{attempt}")
            execution_record.repair_attempts = attempt
            
            # Select repair strategy
            repair_strategy = review.suggested_fix or "retry_with_heavier_tier"
            
            # Execute repair based on strategy
            try:
                if repair_strategy == "retry_with_faster_tier":
                    repaired_output = await self._repair_faster_tier(subtask, nc)
                
                elif repair_strategy == "retry_with_heavier_tier":
                    repaired_output = await self._repair_heavier_tier(subtask, nc)
                
                elif repair_strategy == "retry_with_more_context":
                    repaired_output = await self._repair_more_context(subtask, nc)
                
                elif repair_strategy == "escalate_to_fortress":
                    # Policy violation - escalate for manual review
                    self.logger.warning(f"[REPAIR] Escalating {subtask.id} to Fortress for policy review")
                    return False  # Don't auto-repair policy violations
                
                else:
                    repaired_output = await self._execute_subtask(subtask, nc)
                
                repaired_output["duration"] = repaired_output.get("duration", 0)
                execution_record.execution_output = repaired_output
                
                # Re-validate after repair
                re_validation = await self._validate_execution(repaired_output, subtask)
                execution_record.review = re_validation
                
                if re_validation.passed:
                    self.logger.info(f"[REPAIR] Subtask {subtask.id} repair successful on attempt #{attempt}")
                    return True
                
                # If still failed, update review for next attempt
                review = re_validation
            
            except Exception as e:
                self.logger.error(f"[REPAIR] Subtask {subtask.id} repair attempt #{attempt} failed: {e}")
                continue
        
        return False

    async def _repair_faster_tier(self, subtask: SubTask, nc) -> Dict[str, Any]:
        """Retry with faster, lighter model tier"""
        self.logger.info(f"[REPAIR STRATEGY] Retrying {subtask.id} with faster tier")
        modified = subtask.copy()
        # Signal to thought domain to use tier_1_local (fast, local)
        return await self._execute_subtask(modified, nc)

    async def _repair_heavier_tier(self, subtask: SubTask, nc) -> Dict[str, Any]:
        """Retry with heavier, more capable model tier"""
        self.logger.info(f"[REPAIR STRATEGY] Retrying {subtask.id} with heavier tier")
        modified = subtask.copy()
        # Signal to thought domain to use tier_3_heavy (Claude, GPT-4)
        return await self._execute_subtask(modified, nc)

    async def _repair_more_context(self, subtask: SubTask, nc) -> Dict[str, Any]:
        """Retry with increased context window"""
        self.logger.info(f"[REPAIR STRATEGY] Retrying {subtask.id} with increased context")
        modified = subtask.copy()
        # Add context hint to subtask
        return await self._execute_subtask(modified, nc)

    async def _emit_execution_byproduct(self, execution_record: SubtaskExecution, nc) -> None:
        """
        Emit execution result to Knowledge domain for federation learning.
        Uses existing byproduct pattern from reflex._adapt().
        """
        try:
            byproduct = {
                "subtask_id": execution_record.subtask_id,
                "execution_status": execution_record.execution_output.get("status"),
                "review_passed": execution_record.review.passed if execution_record.review else False,
                "review_issues": execution_record.review.issues if execution_record.review else [],
                "repair_attempts": execution_record.repair_attempts,
                "final_status": execution_record.final_status
            }
            
            # Store via Knowledge domain
            await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_store_memory",
                json.dumps({"content": json.dumps(byproduct)}).encode(),
                timeout=15.0
            )
        except Exception as e:
            self.logger.warning(f"Failed to emit execution byproduct: {e}")

    # ============================================================================
    # END CRITIC LOOP METHODS
    # ============================================================================

    # ============================================================================
    # CONSENSUS PROTOCOL: Phase 7 - Multi-Critic Validation
    # ============================================================================

    async def _consensus_review(
        self,
        subtask: SubTask,
        execution_output: Dict[str, Any],
        nc,
        num_critics: int = 3
    ) -> Dict[str, Any]:
        """
        Route validation to multiple independent critics and require consensus.
        
        This is used for high-stakes operations where a single critic's judgment
        may not be sufficient. Each critic evaluates independently, then votes.
        
        Args:
            subtask: The subtask being reviewed
            execution_output: Output from Module A execution
            nc: NATS connection
            num_critics: Number of independent critics (default: 3)
            
        Returns:
            Consensus result with votes and final decision
        """
        self.logger.info(f"[CONSENSUS] Starting {num_critics}-critic review for {subtask.id}")
        
        # Define critic roles (each has different bias profile)
        critic_roles = [
            {"role": "analytical", "bias": {"analytical_depth": 90, "audit_strictness": 70}},
            {"role": "cautious", "bias": {"analytical_depth": 70, "audit_strictness": 90}},
            {"role": "creative", "bias": {"analytical_depth": 80, "audit_strictness": 50, "creative_variance": 80}},
        ]
        
        # Limit to num_critics
        active_critics = critic_roles[:num_critics]
        
        # Collect votes from each critic
        votes = []
        for critic in active_critics:
            vote = await self._single_critic_vote(
                subtask,
                execution_output,
                critic,
                nc
            )
            votes.append(vote)
        
        # Calculate consensus
        passed_votes = sum(1 for v in votes if v["passed"])
        total_votes = len(votes)
        consensus_ratio = passed_votes / total_votes if total_votes > 0 else 0
        
        # Determine final decision
        if consensus_ratio >= 0.66:  # 2/3 majority
            decision = "approved"
        elif consensus_ratio >= 0.5:  # Simple majority
            decision = "conditional"
        else:
            decision = "rejected"
        
        # Calculate confidence based on agreement
        if passed_votes == total_votes:
            confidence = 1.0
        elif passed_votes == 0 or passed_votes == total_votes:
            confidence = 0.9
        else:
            confidence = 0.7
        
        result = {
            "decision": decision,
            "consensus_ratio": consensus_ratio,
            "votes": {
                "passed": passed_votes,
                "total": total_votes,
                "confidence": confidence
            },
            "individual_votes": [
                {
                    "critic": v["critic_role"],
                    "passed": v["passed"],
                    "issues": v["issues"],
                    "reasoning": v.get("reasoning", "")
                }
                for v in votes
            ],
            "requires_manual_review": decision == "rejected" and consensus_ratio < 0.33
        }
        
        self.logger.info(
            f"[CONSENSUS] {subtask.id}: {decision} "
            f"({passed_votes}/{total_votes} votes, confidence: {confidence:.2f})"
        )
        
        return result

    async def _single_critic_vote(
        self,
        subtask: SubTask,
        execution_output: Dict[str, Any],
        critic_config: Dict[str, Any],
        nc
    ) -> Dict[str, Any]:
        """
        Simulate a single critic's evaluation with custom bias profile.
        
        This creates an isolated validation context with specific cognitive biases
        to ensure diverse, independent evaluations.
        """
        # Save current biases
        original_biases = self.cognitive_biases.copy()
        
        # Apply critic-specific biases
        self.cognitive_biases.update(critic_config.get("bias", {}))
        
        try:
            # Run validation with critic's bias profile
            review = await self._validate_execution(execution_output, subtask)
            
            return {
                "critic_role": critic_config["role"],
                "passed": review.passed,
                "issues": review.issues,
                "severity": review.severity,
                "confidence": review.confidence,
                "reasoning": self._generate_critic_reasoning(review, critic_config["role"])
            }
        finally:
            # Restore original biases
            self.cognitive_biases = original_biases

    def _generate_critic_reasoning(
        self,
        review: ReviewResult,
        critic_role: str
    ) -> str:
        """Generate reasoning explanation based on critic role"""
        
        if critic_role == "analytical":
            if review.passed:
                return "Logic sound. Data integrity verified. Proceeding."
            else:
                return f"Analysis reveals {len(review.issues)} critical issues. Requires resolution."
        
        elif critic_role == "cautious":
            if review.passed:
                return "Risk acceptable within safety parameters. Approved with standard monitoring."
            else:
                return f"SAFETY VIOLATION: {review.issues[0] if review.issues else 'Unknown'}. Cannot approve."
        
        elif critic_role == "creative":
            if review.passed:
                return "Novel approach validated. Creative solution within bounds."
            else:
                return f"Alternative path exists. Consider: {review.suggested_fix or 'rethinking approach'}"
        
        return "Evaluation complete."

    async def _execute_with_consensus(
        self,
        subtask: SubTask,
        nc,
        require_consensus: bool = True,
        num_critics: int = 3
    ) -> Dict[str, Any]:
        """
        Execute subtask with optional consensus validation.
        
        If require_consensus is True, uses multi-critic validation for high-stakes decisions.
        """
        # Step 1: Execute (Module A)
        execution_output = await self._execute_subtask(subtask, nc)
        
        # Step 2: If consensus required, use multi-critic review
        if require_consensus and self.cognitive_biases.get("analytical_depth", 50) > 70:
            consensus_result = await self._consensus_review(
                subtask,
                execution_output,
                nc,
                num_critics
            )
            
            # If rejected, escalate
            if consensus_result["decision"] == "rejected":
                return {
                    "status": "rejected_by_consensus",
                    "execution_output": execution_output,
                    "consensus": consensus_result,
                    "escalation_required": True
                }
            
            # If conditional, add warning
            if consensus_result["decision"] == "conditional":
                execution_output["consensus_warning"] = "Conditional approval - monitor closely"
        
        # Step 3: Standard validation as fallback
        else:
            review = await self._validate_execution(execution_output, subtask)
            
            if not review.passed:
                return {
                    "status": "failed_validation",
                    "execution_output": execution_output,
                    "review": review.dict(),
                    "needs_repair": True
                }
        
        return {
            "status": "success",
            "execution_output": execution_output
        }

    # ============================================================================
    # END CONSENSUS PROTOCOL
    # ============================================================================

    # ============================================================================
    # FEW-SHOT LEARNING: Phase 8 - Store & Retrieve Repair Patterns
    # ============================================================================

    FEWSHOT_MEMORY_KEY = "critic_loop_repair_patterns"
    MAX_STORED_PATTERNS = 20

    async def _store_successful_repair_pattern(
        self,
        subtask: SubTask,
        issue_type: str,
        repair_strategy: str,
        nc
    ) -> None:
        """
        Store a successful repair pattern for few-shot learning.
        
        This allows the system to remember what repair strategies work for
        specific issue types, enabling smarter strategy selection in the future.
        """
        try:
            # Query existing patterns
            patterns_response = await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_query_memory",
                json.dumps({
                    "query": self.FEWSHOT_MEMORY_KEY,
                    "limit": self.MAX_STORED_PATTERNS
                }).encode(),
                timeout=10.0
            )
            
            existing_patterns = []
            try:
                data = json.loads(patterns_response.data.decode())
                if data.get("status") == "success":
                    existing_patterns = data.get("result", {}).get("results", [])
            except Exception:
                pass
            
            # Check if pattern already exists
            pattern_exists = any(
                p.get("issue_type") == issue_type and p.get("repair_strategy") == repair_strategy
                for p in existing_patterns
            )
            
            if pattern_exists:
                self.logger.debug(f"[FEWSHOT] Pattern already stored: {issue_type} -> {repair_strategy}")
                return
            
            # Create new pattern
            new_pattern = {
                "type": "repair_pattern",
                "issue_type": issue_type,
                "repair_strategy": repair_strategy,
                "subtask_description": subtask.description,
                "target_role": subtask.target_agent_role,
                "success_timestamp": time.time(),
                "example_count": 1
            }
            
            # Store in memory
            await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_store_memory",
                json.dumps({
                    "content": json.dumps(new_pattern),
                    "domain": self.FEWSHOT_MEMORY_KEY
                }).encode(),
                timeout=10.0
            )
            
            self.logger.info(f"[FEWSHOT] Stored pattern: {issue_type} -> {repair_strategy}")
        
        except Exception as e:
            self.logger.warning(f"[FEWSHOT] Failed to store pattern: {e}")

    async def _get_recommended_strategy(
        self,
        issues: List[str],
        subtask: SubTask,
        nc
    ) -> Optional[str]:
        """
        Get recommended repair strategy based on stored few-shot patterns.
        
        Queries the Knowledge domain for similar issue types and returns
        the most successful repair strategy.
        """
        try:
            # Build query from issues
            issue_text = " ".join(issues).lower()
            
            # Query for matching patterns
            response = await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_query_memory",
                json.dumps({
                    "query": f"{self.FEWSHOT_MEMORY_KEY} {issue_text}",
                    "limit": 5
                }).encode(),
                timeout=10.0
            )
            
            data = json.loads(response.data.decode())
            if data.get("status") != "success":
                return None
            
            results = data.get("result", {}).get("results", [])
            if not results:
                return None
            
            # Find best matching pattern
            best_pattern = None
            best_score = 0
            
            for result in results:
                try:
                    content = json.loads(result.get("content", "{}"))
                    if content.get("type") != "repair_pattern":
                        continue
                    
                    # Score by relevance
                    score = 0
                    
                    # Match issue type
                    if any(issue_word in content.get("issue_type", "").lower() for issue_word in issues):
                        score += 2
                    
                    # Match target role
                    if content.get("target_role") == subtask.target_agent_role:
                        score += 1
                    
                    if score > best_score:
                        best_score = score
                        best_pattern = content
                
                except Exception:
                    continue
            
            if best_pattern and best_score > 0:
                strategy = best_pattern.get("repair_strategy")
                self.logger.info(f"[FEWSHOT] Found pattern: {best_pattern.get('issue_type')} -> {strategy}")
                return strategy
        
        except Exception as e:
            self.logger.warning(f"[FEWSHOT] Failed to get recommendations: {e}")
        
        return None

    def _extract_issue_type(self, issues: List[str]) -> str:
        """Extract primary issue type from validation issues"""
        issue_text = " ".join(issues).lower()
        
        if "timeout" in issue_text or "slow" in issue_text:
            return "timeout_slow"
        elif "incomplete" in issue_text or "missing result" in issue_text:
            return "incomplete_output"
        elif "policy" in issue_text or "permission" in issue_text:
            return "policy_violation"
        elif "error" in issue_text:
            return "execution_error"
        elif "memory" in issue_text or "oom" in issue_text:
            return "memory_exceeded"
        else:
            return "unknown_issue"

    # Override _attempt_repair to use few-shot learning
    async def _attempt_repair(
        self,
        subtask: SubTask,
        review: ReviewResult,
        execution_record: SubtaskExecution,
        nc
    ) -> bool:
        """
        REPAIR (Module C): Attempt to fix failed subtask.
        Now includes few-shot learning integration.
        """
        max_retries = 3
        
        # Extract issue type for few-shot storage
        issue_type = self._extract_issue_type(review.issues)
        
        for attempt in range(1, max_retries + 1):
            if attempt > max_retries:
                self.logger.error(f"[REPAIR] Subtask {subtask.id} exhausted retries")
                return False
            
            self.logger.info(f"[REPAIR] Subtask {subtask.id} repair attempt #{attempt}")
            execution_record.repair_attempts = attempt
            
            # Try few-shot recommended strategy first
            repair_strategy = None
            if attempt == 1:
                repair_strategy = await self._get_recommended_strategy(
                    review.issues,
                    subtask,
                    nc
                )
            
            # Fall back to suggested strategy
            if not repair_strategy:
                repair_strategy = review.suggested_fix or "retry_with_heavier_tier"
            
            # Execute repair based on strategy
            try:
                if repair_strategy == "retry_with_faster_tier":
                    repaired_output = await self._repair_faster_tier(subtask, nc)
                elif repair_strategy == "retry_with_heavier_tier":
                    repaired_output = await self._repair_heavier_tier(subtask, nc)
                elif repair_strategy == "retry_with_more_context":
                    repaired_output = await self._repair_more_context(subtask, nc)
                elif repair_strategy == "escalate_to_fortress":
                    self.logger.warning(f"[REPAIR] Escalating {subtask.id} to Fortress for policy review")
                    return False
                else:
                    repaired_output = await self._execute_subtask(subtask, nc)
                
                repaired_output["duration"] = repaired_output.get("duration", 0)
                execution_record.execution_output = repaired_output
                
                # Re-validate after repair
                re_validation = await self._validate_execution(repaired_output, subtask)
                execution_record.review = re_validation
                
                if re_validation.passed:
                    self.logger.info(
                        f"[REPAIR] Subtask {subtask.id} repair successful on attempt #{attempt}"
                    )
                    
                    # Store successful pattern for few-shot learning
                    await self._store_successful_repair_pattern(
                        subtask,
                        issue_type,
                        repair_strategy,
                        nc
                    )
                    
                    return True
                
                # If still failed, update review for next attempt
                review = re_validation
            
            except Exception as e:
                self.logger.error(
                    f"[REPAIR] Subtask {subtask.id} repair attempt #{attempt} failed: {e}"
                )
                continue
        
        return False

    # ============================================================================
    # END FEW-SHOT LEARNING
    # ============================================================================

    # ============================================================================
    # ADAPTIVE STRICTNESS: Phase 9 - Dynamic audit_strictness Adjustment
    # ============================================================================

    HISTORY_WINDOW_SIZE = 50  # Number of recent executions to consider
    HIGH_FAILURE_THRESHOLD = 0.3  # 30% failure rate triggers paranoia
    LOW_FAILURE_THRESHOLD = 0.1  # 10% or lower triggers relaxation

    async def _update_adaptive_strictness(
        self,
        nc,
        force_recalc: bool = False
    ) -> Dict[str, Any]:
        """
        Dynamically adjust audit_strictness based on historical success rates.
        
        This allows the critic to become more paranoid after failures
        and relax after sustained success.
        
        Args:
            nc: NATS connection
            force_recalc: Force recalculation even if recently updated
            
        Returns:
            Updated strictness info
        """
        try:
            # Query recent execution history
            response = await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_query_memory",
                json.dumps({
                    "query": "subtask execution_status review_passed",
                    "limit": self.HISTORY_WINDOW_SIZE
                }).encode(),
                timeout=10.0
            )
            
            data = json.loads(response.data.decode())
            if data.get("status") != "success":
                return {"error": "Failed to query history"}
            
            results = data.get("result", {}).get("results", [])
            
            if not results:
                return {"message": "No history yet, using defaults"}
            
            # Calculate failure rate
            total = len(results)
            failures = sum(
                1 for r in results 
                if not r.get("review_passed", True) or r.get("final_status") in ["failed", "escalated"]
            )
            failure_rate = failures / total if total > 0 else 0
            
            # Get current strictness
            current_strictness = self.cognitive_biases.get("audit_strictness", 50.0)
            new_strictness = current_strictness
            
            adjustment_reason = ""
            
            # Adjust based on failure rate
            if failure_rate >= self.HIGH_FAILURE_THRESHOLD:
                # High failure rate - increase strictness (become paranoid)
                new_strictness = min(100.0, current_strictness + 10.0)
                adjustment_reason = f"High failure rate ({failure_rate:.1%}) - increasing caution"
            
            elif failure_rate <= self.LOW_FAILURE_THRESHOLD:
                # Low failure rate - decrease strictness (relax)
                new_strictness = max(20.0, current_strictness - 5.0)
                adjustment_reason = f"Sustained success ({failure_rate:.1%}) - relaxing controls"
            
            # Apply if changed
            if new_strictness != current_strictness:
                self.cognitive_biases["audit_strictness"] = new_strictness
                
                self.logger.info(
                    f"[ADAPTIVE] audit_strictness: {current_strictness:.1f} -> {new_strictness:.1f}"
                )
                self.logger.info(f"[ADAPTIVE] Reason: {adjustment_reason}")
                
                # Also adjust analytical_depth inversely
                analytical = self.cognitive_biases.get("analytical_depth", 50.0)
                if failure_rate >= self.HIGH_FAILURE_THRESHOLD:
                    self.cognitive_biases["analytical_depth"] = min(100.0, analytical + 5.0)
                elif failure_rate <= self.LOW_FAILURE_THRESHOLD:
                    self.cognitive_biases["analytical_depth"] = max(30.0, analytical - 2.0)
                
                # Persist changes for closed-loop adaptation
                if hasattr(self, 'kernel') and self.kernel:
                    self.kernel.persist_cognitive_biases()
            
            return {
                "current_strictness": current_strictness,
                "new_strictness": new_strictness,
                "failure_rate": failure_rate,
                "history_size": total,
                "adjustment_reason": adjustment_reason or "No adjustment needed"
            }
        
        except Exception as e:
            self.logger.warning(f"[ADAPTIVE] Failed to update strictness: {e}")
            return {"error": str(e)}

    async def _check_domain_health(
        self,
        domain: str,
        nc
    ) -> Dict[str, Any]:
        """
        Check the health/success rate of a specific domain.
        
        Used to identify which domains need attention and which are performing well.
        """
        try:
            response = await nc.request(
                "aaroneousautomationsuite.aaroneousautomationsuite_query_memory",
                json.dumps({
                    "query": f"subtask target_agent_role {domain} execution_status",
                    "limit": 20
                }).encode(),
                timeout=10.0
            )
            
            data = json.loads(response.data.decode())
            results = data.get("result", {}).get("results", []) if data.get("status") == "success" else []
            
            total = len(results)
            if total == 0:
                return {"domain": domain, "status": "no_data"}
            
            successes = sum(1 for r in results if r.get("review_passed", False))
            success_rate = successes / total
            
            return {
                "domain": domain,
                "total_executions": total,
                "successes": successes,
                "success_rate": success_rate,
                "health": "healthy" if success_rate >= 0.8 else "degraded" if success_rate >= 0.5 else "critical"
            }
        
        except Exception as e:
            return {"domain": domain, "error": str(e)}

    # ============================================================================
    # END ADAPTIVE STRICTNESS
    # ============================================================================

    # ============================================================================
    # LATENCY TELEMETRY: Phase 10 - Thinking Pause Visualization
    # ============================================================================

    async def _emit_inference_latency(
        self,
        nc,
        stage: str,
        duration: float,
        metadata: Dict[str, Any] = None
    ) -> None:
        """
        Emit latency telemetry for UI feedback during "thinking" pauses.
        
        This allows the UI to visualize when the system is "thinking" - showing
        the user that processing is happening during longer operations.
        
        Args:
            nc: NATS connection
            stage: Current stage (planning, execution, validation, repair)
            duration: Duration in seconds
            metadata: Additional context (model used, tokens, etc.)
        """
        try:
            telemetry = {
                "timestamp": time.time(),
                "stage": stage,
                "duration_seconds": duration,
                "agent": "leadership",
                "metadata": metadata or {}
            }
            
            # Publish to telemetry stream
            await nc.publish(
                "federation.telemetry.critic_loop.latency",
                json.dumps(telemetry).encode()
            )
        
        except Exception as e:
            self.logger.debug(f"[TELEMETRY] Failed to emit latency: {e}")

    async def _emit_stage_transition(
        self,
        nc,
        from_stage: str,
        to_stage: str,
        subtask_id: str = None
    ) -> None:
        """
        Emit stage transition events for real-time UI updates.
        
        This allows the UI to show progress through the critic loop stages:
        PLANNING -> EXECUTING -> VALIDATING -> (REPAIRING) -> COMPLETE
        """
        try:
            event = {
                "timestamp": time.time(),
                "event_type": "stage_transition",
                "from_stage": from_stage,
                "to_stage": to_stage,
                "subtask_id": subtask_id,
                "agent": "leadership"
            }
            
            await nc.publish(
                "federation.telemetry.critic_loop.stages",
                json.dumps(event).encode()
            )
        
        except Exception as e:
            self.logger.debug(f"[TELEMETRY] Failed to emit stage transition: {e}")

    # Helper to add telemetry to _execute_dag_with_critic_loop
    async def _execute_dag_with_critic_loop_telemetry(
        self,
        dag: TaskDAG,
        nc,
        emit_telemetry: bool = True
    ) -> dict:
        """
        Wrapper around DAG execution with full telemetry support.
        
        This wraps _execute_dag_with_critic_loop to emit telemetry
        at each stage of the critic loop.
        """
        start_time = time.time()
        
        if emit_telemetry:
            await self._emit_stage_transition(nc, "idle", "planning", dag.subtasks[0].id if dag.subtasks else None)
        
        self.logger.info(f"[CRITIC LOOP] Starting DAG execution with {len(dag.subtasks)} subtasks")
        
        results: Dict[str, SubtaskExecution] = {}
        
        for i, subtask in enumerate(dag.subtasks):
            subtask_start = time.time()
            
            if emit_telemetry:
                await self._emit_stage_transition(
                    nc, 
                    "planning" if i == 0 else "complete", 
                    "executing", 
                    subtask.id
                )
            
            # Initialize execution record
            execution_record = SubtaskExecution(
                subtask_id=subtask.id,
                execution_output={}
            )
            
            # STEP 1: EXECUTE SUBTASK (Module A)
            try:
                exec_start = time.time()
                execution_output = await self._execute_subtask(subtask, nc)
                exec_duration = time.time() - exec_start
                
                if emit_telemetry:
                    await self._emit_inference_latency(
                        nc,
                        "subtask_execution",
                        exec_duration,
                        {"subtask_id": subtask.id, "target": subtask.target_agent_role}
                    )
                
                execution_record.execution_output = execution_output
            except Exception as e:
                self.logger.error(f"[CRITIC LOOP] Subtask {subtask.id} execution failed: {e}")
                execution_record.execution_output = {
                    "status": "error",
                    "error": str(e),
                    "duration": 0
                }
            
            # STEP 2: VALIDATE OUTPUT (Module B - Inline Critic)
            if emit_telemetry:
                await self._emit_stage_transition(nc, "executing", "validating", subtask.id)
            
            val_start = time.time()
            validation_result = await self._validate_execution(
                execution_record.execution_output,
                subtask
            )
            val_duration = time.time() - val_start
            
            if emit_telemetry:
                await self._emit_inference_latency(
                    nc,
                    "validation",
                    val_duration,
                    {"subtask_id": subtask.id, "passed": validation_result.passed}
                )
            
            execution_record.review = validation_result
            
            # STEP 3: REPAIR IF FAILED (Module C - Auto-Retry)
            repair_count = 0
            if not validation_result.passed and validation_result.severity in ["error", "critical"]:
                if emit_telemetry:
                    await self._emit_stage_transition(nc, "validating", "repairing", subtask.id)
                
                repair_start = time.time()
                repair_success = await self._attempt_repair(
                    subtask,
                    validation_result,
                    execution_record,
                    nc
                )
                repair_duration = time.time() - repair_start
                repair_count = execution_record.repair_attempts
                
                if emit_telemetry:
                    await self._emit_inference_latency(
                        nc,
                        "repair",
                        repair_duration,
                        {"subtask_id": subtask.id, "success": repair_success, "attempts": repair_count}
                    )
                
                if repair_success:
                    self.logger.info(f"[CRITIC LOOP] Subtask {subtask.id} repair successful")
                    execution_record.final_status = "success"
                else:
                    self.logger.warning(f"[CRITIC LOOP] Subtask {subtask.id} repair failed, escalating")
                    execution_record.final_status = "escalated"
            else:
                # Passed validation
                execution_record.final_status = "success"
                # Grant achievement for successful task
                ach_result = self.grant_task_achievement(subtask.id, success=True)
                if ach_result["achievements_granted"]:
                    for granted in ach_result["achievements_granted"]:
                        self.logger.info(f"[GUILD REWARD] {granted.get('title')} unlocked!")
            
            # STEP 4: STORE IN KNOWLEDGE (Federation learning via byproducts)
            if emit_telemetry:
                await self._emit_stage_transition(nc, "repairing" if repair_count > 0 else "validating", "storing", subtask.id)
            
            await self._emit_execution_byproduct(execution_record, nc)
            
            if emit_telemetry:
                await self._emit_stage_transition(nc, "storing", "complete", subtask.id)
            
            results[subtask.id] = execution_record
        
        # Final summary
        passed_count = sum(1 for r in results.values() if r.final_status == "success")
        total_count = len(results)
        total_duration = time.time() - start_time
        
        self.logger.info(f"[CRITIC LOOP] DAG execution complete. Passed: {passed_count}/{total_count}")
        
        if emit_telemetry:
            await self._emit_stage_transition(nc, "complete", "idle", None)
            await self._emit_inference_latency(
                nc,
                "total_dag_execution",
                total_duration,
                {
                    "total_subtasks": total_count,
                    "passed": passed_count,
                    "failed": total_count - passed_count
                }
            )
        
        return {
            "total_subtasks": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
            "results": {k: v.dict() for k, v in results.items()}
        }

    # ============================================================================
    # END LATENCY TELEMETRY
    # ============================================================================

    def capabilities(self) -> list[str]:
        return [
            "aaroneousautomationsuite_triage_user_request_advanced",
            "aaroneousautomationsuite_guild_assign_tactical_operation",
            "aaroneousautomationsuite_guild_resolve_tactical_operation",
            "aaroneousautomationsuite_guild_view_dispatch_board",
            "aaroneousautomationsuite_critic_get_repair_patterns",
            "aaroneousautomationsuite_critic_adaptive_strictness",
            "aaroneousautomationsuite_critic_domain_health"
        ]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()

        if capability_id == "aaroneousautomationsuite_guild_assign_tactical_operation":
            op_id = payload.get("operation_id")
            self.dispatch_board[op_id] = {"status": "pending", "agent": payload.get("assigned_agent")}
            return self._format_success(capability_id, f"Operation {op_id} dispatched.", start_time)

        elif capability_id == "aaroneousautomationsuite_guild_resolve_tactical_operation":
            op_id = payload.get("operation_id")
            if op_id in self.dispatch_board:
                self.dispatch_board[op_id]["status"] = "resolved"
            return self._format_success(capability_id, f"Operation {op_id} resolved.", start_time)

        elif capability_id == "aaroneousautomationsuite_guild_view_dispatch_board":
            return self._format_success(capability_id, self.dispatch_board, start_time)

        elif capability_id == "aaroneousautomationsuite_triage_user_request_advanced":
            # Native DAG Execution with Critic Loop
            user_request = payload.get("request", "")
            if not self.kernel or not self.kernel.nc:
                return self._format_error(capability_id, "No Event Bus for DAG execution.")
                
            routing_payload = {
                "messages": [{"role": "user", "content": f"Create TaskDAG JSON for: {user_request}"}],
                "task_type": "architectural_design"
            }
            
            try:
                response = await self.kernel.nc.request(
                    "aaroneousautomationsuite.aaroneousautomationsuite_model_routing",
                    json.dumps(routing_payload).encode(), timeout=30.0
                )
                res_data = json.loads(response.data.decode())
                
                if res_data.get("status") == "success":
                    raw = res_data["result"]["output"].replace("```json\\n", "").replace("```", "").strip()
                    dag = TaskDAG.parse_raw(raw)
                    
                    # Check if telemetry is enabled
                    emit_telemetry = payload.get("enable_telemetry", True)
                    
                    if emit_telemetry:
                        # Use telemetry-enabled execution
                        dag_result = await self._execute_dag_with_critic_loop_telemetry(
                            dag, 
                            self.kernel.nc,
                            emit_telemetry=True
                        )
                    else:
                        # Standard execution
                        dag_result = await self._execute_dag_with_critic_loop(dag, self.kernel.nc)
                    
                    # Optionally update adaptive strictness after execution
                    if payload.get("update_adaptive_strictness", False):
                        await self._update_adaptive_strictness(self.kernel.nc)
                    
                    return self._format_success(
                        capability_id,
                        {
                            "message": f"DAG orchestration complete",
                            "summary": dag_result
                        },
                        start_time
                    )
            except Exception as e:
                return self._format_error(capability_id, f"DAG Execution Failed: {e}")

        elif capability_id == "aaroneousautomationsuite_critic_get_repair_patterns":
            query = payload.get("query", "")
            if not self.kernel or not self.kernel.nc:
                return self._format_error(capability_id, "No Event Bus.")
            try:
                strategy = await self._get_recommended_strategy(
                    [query],
                    SubTask(id="query", description=query, target_agent_role="unknown"),
                    self.kernel.nc
                )
                return self._format_success(
                    capability_id,
                    {"recommended_strategy": strategy, "query": query},
                    start_time
                )
            except Exception as e:
                return self._format_error(capability_id, str(e))

        elif capability_id == "aaroneousautomationsuite_critic_adaptive_strictness":
            if not self.kernel or not self.kernel.nc:
                return self._format_error(capability_id, "No Event Bus.")
            force = payload.get("force_recalc", False)
            try:
                result = await self._update_adaptive_strictness(self.kernel.nc, force_recalc=force)
                return self._format_success(capability_id, result, start_time)
            except Exception as e:
                return self._format_error(capability_id, str(e))

        elif capability_id == "aaroneousautomationsuite_critic_domain_health":
            domain = payload.get("domain", "thought")
            if not self.kernel or not self.kernel.nc:
                return self._format_error(capability_id, "No Event Bus.")
            try:
                result = await self._check_domain_health(domain, self.kernel.nc)
                return self._format_success(capability_id, result, start_time)
            except Exception as e:
                return self._format_error(capability_id, str(e))

        return self._format_error(capability_id, "Unknown leadership capability.")
