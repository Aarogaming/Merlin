import asyncio
import sys
import json
import logging
from pathlib import Path

sys.path.append(str(Path(r"D:\Library\Core")))
from run_agent import AASAgent

logger = logging.getLogger("AAS.MerlinEngine")
GRIMOIRE_PATH = Path(r"D:\Merlin\artifacts\grimoire.json")

def append_to_grimoire(topic: str, content: str) -> str:
    """Updates The Grimoire with newly researched or synthesized knowledge."""
    state = {}
    if GRIMOIRE_PATH.exists():
        try:
            state = json.loads(GRIMOIRE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    state[topic] = {
        "content": content,
        "recorded_at": asyncio.get_event_loop().time()
    }
    
    GRIMOIRE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    logger.info(f"Added knowledge to The Grimoire under topic '{topic}'.")
    return f"Successfully recorded '{topic}' in The Grimoire."

async def main():
    merlin = AASAgent(
        repo_name="Merlin", 
        persona_name="Merlin", 
        system_prompt_path=str(Path(r"D:\Merlin\.aas\AGENTS.md"))
    )

    merlin.register_tool(
        name="append_to_grimoire",
        func=append_to_grimoire,
        description="Records synthesized knowledge or research into The Grimoire. Use this to permanently document findings.",
        schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The category or title of the knowledge"},
                "content": {"type": "string", "description": "The detailed findings to record"}
            },
            "required": ["topic", "content"]
        }
    )

    await merlin.start()

if __name__ == "__main__":
    asyncio.run(main())