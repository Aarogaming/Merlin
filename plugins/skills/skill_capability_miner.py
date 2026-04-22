import ast
from pathlib import Path
from plugins.knowledge import Knowledge

class CapabilityMinerSkill(Knowledge):
    """
    Skill: Capability Miner
    Domain: Knowledge
    
    Reverse-engineered from Library 'capability_miner.py'.
    Parses Python ASTs across the federation to discover internal and registered
    capabilities, synthesizing them into the Omni Memory constellation index.
    Inherits its Epigenetic weight from the Knowledge domain.
    """
    
    @property
    def capabilities(self) -> list[str]:
        return ["aaroneousautomationsuite_library_mine_capabilities"]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()
        
        if capability_id != "aaroneousautomationsuite_library_mine_capabilities":
            return self._format_error(capability_id, "Unhandled capability.")
            
        target_path = payload.get("target_path")
        if not target_path:
            return self._format_error(capability_id, "Missing 'target_path' in payload.")
            
        target = Path(target_path)
        if not target.exists():
            return self._format_error(capability_id, f"Target {target_path} not found.")

        found_caps = set()
        
        # AST Parsing Logic (poached from capability_miner.py)
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith("handle_message") or node.name.startswith("_"):
                        continue
                    found_caps.add(node.name)
                    
        except Exception as e:
            return self._format_error(capability_id, f"Failed to parse AST: {e}")

        result = {
            "mined_file": str(target),
            "capabilities_discovered": list(found_caps)
        }
        
        # In a full implementation, we would now insert these directly into the SQLite Omni.
        # For now, we return the parsed state natively.
        return self._format_success(capability_id, result, start_time)
