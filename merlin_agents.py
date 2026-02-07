import asyncio
import json
import os
from typing import List, Dict, Any
from merlin_logger import merlin_logger
import merlin_settings as settings
import requests


class MerlinAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    async def execute_task(self, task: str, context: str = "") -> str:
        merlin_logger.info(f"Agent {self.name} ({self.role}) executing task: {task}")

        # In a real implementation, this would call the LLM
        # For this prototype, we'll simulate the LLM call
        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": f"You are {self.name}, a {self.role}."},
                {"role": "user", "content": f"Task: {task}\nContext: {context}"},
            ],
            "temperature": 0.7,
        }

        try:
            # Simulate async LLM call
            await asyncio.sleep(1)
            # In reality: response = await async_client.post(settings.LM_STUDIO_URL, json=payload)
            return f"Result from {self.name}: Completed task '{task}'"
        except Exception as e:
            merlin_logger.error(f"Agent {self.name} failed: {e}")
            return f"Error from {self.name}: {str(e)}"


class MerlinOrchestrator:
    def __init__(self):
        self.agents = {
            "researcher": MerlinAgent("Researcher", "Expert at gathering information"),
            "coder": MerlinAgent("Coder", "Expert at writing and debugging code"),
            "reviewer": MerlinAgent(
                "Reviewer", "Expert at quality control and security"
            ),
        }

    async def decompose_and_execute(self, goal: str) -> Dict[str, Any]:
        merlin_logger.info(f"Orchestrating goal: {goal}")

        # 1. Decompose goal into tasks (Simulated)
        tasks = [
            {"agent": "researcher", "task": f"Research requirements for: {goal}"},
            {"agent": "coder", "task": f"Implement core logic for: {goal}"},
            {"agent": "reviewer", "task": f"Review implementation for: {goal}"},
        ]

        # 2. Execute tasks in parallel
        execution_tasks = []
        for t in tasks:
            agent = self.agents.get(t["agent"])
            if agent:
                execution_tasks.append(agent.execute_task(t["task"]))

        results = await asyncio.gather(*execution_tasks)

        return {"goal": goal, "results": results, "status": "completed"}


orchestrator = MerlinOrchestrator()

if __name__ == "__main__":
    # Simple test
    async def test():
        result = await orchestrator.decompose_and_execute("Add a new plugin to Merlin")
        print(json.dumps(result, indent=2))

    asyncio.run(test())
