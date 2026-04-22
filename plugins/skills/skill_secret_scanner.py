import re
from pathlib import Path
from plugins.security import Security

class SecretScannerSkill(Security):
    """
    Skill: Secret Scanner
    Domain: Security
    
    Reverse-engineered from MyFortress 'scan_for_secrets.py'.
    Scans files or directories for API keys, passwords, and private keys.
    Inherits its Epigenetic weight from the Security domain.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.api_patterns = [
            ("openai_project_key", re.compile(r"sk-proj-[A-Za-z0-9]{20,}")),
            ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
            ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]+")),
            ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"))
        ]
        
        self.credential_patterns = [
            ("password_assignment", re.compile(r'password\s*[=:]\s*["\'][^"\']{3,}["\']', re.IGNORECASE)),
            ("token_assignment", re.compile(r'token\s*[=:]\s*["\'][^"\']{10,}["\']', re.IGNORECASE)),
        ]

    @property
    def capabilities(self) -> list[str]:
        # Expands the agent's MCP manifest dynamically
        return ["aaroneousautomationsuite_fortress_scan_for_secrets"]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()
        
        if capability_id != "aaroneousautomationsuite_fortress_scan_for_secrets":
            return self._format_error(capability_id, "Unhandled capability.")
            
        file_path = payload.get("file_path")
        if not file_path:
            return self._format_error(capability_id, "Missing 'file_path' in payload.")
            
        target = Path(file_path)
        if not target.exists():
            return self._format_error(capability_id, f"File {file_path} not found.")
            
        issues = []
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            for line_idx, line in enumerate(content.splitlines(), start=1):
                for label, pattern in self.api_patterns + self.credential_patterns:
                    if pattern.search(line):
                        issues.append(f"Potential {label} at {target.name}:{line_idx}")
        except Exception as e:
            return self._format_error(capability_id, f"Failed to scan: {e}")

        result = {
            "scanned_file": str(target),
            "status": "clean" if len(issues) == 0 else "vulnerable",
            "issues_found": issues
        }
        
        # Telemetry is handled natively by the inherited Reflex base class
        return self._format_success(capability_id, result, start_time)
