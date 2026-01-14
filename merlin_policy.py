import os
from enum import Enum
from typing import List, Optional

class ExecutionMode(Enum):
    SAFE = "safe"          # No destructive actions allowed
    RESTRICTED = "restricted" # Destructive actions require confirmation (if implemented)
    LIVE = "live"          # All actions allowed

class ExecutionPolicyManager:
    def __init__(self):
        self.mode = self._determine_mode()
        self.blocked_commands = ["rm -rf /", "format", "del /s /q C:\\"] # Example dangerous commands

    def _determine_mode(self) -> ExecutionMode:
        mode_str = os.environ.get("MERLIN_EXECUTION_MODE", "safe").lower()
        if mode_str == "live":
            return ExecutionMode.LIVE
        elif mode_str == "restricted":
            return ExecutionMode.RESTRICTED
        else:
            return ExecutionMode.SAFE

    def is_command_allowed(self, command: str) -> bool:
        if self.mode == ExecutionMode.LIVE:
            return True
        
        # Check against blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return False
        
        # In safe mode, we might want to block all "destructive" looking commands
        if self.mode == ExecutionMode.SAFE:
            destructive_keywords = ["rm ", "del ", "rd ", "format ", "mkfs "]
            if any(kw in command.lower() for kw in destructive_keywords):
                return False
        
        return True

    def is_file_action_allowed(self, action: str, path: str) -> bool:
        if self.mode == ExecutionMode.LIVE:
            return True
        
        if action == "delete":
            return self.mode != ExecutionMode.SAFE
        
        return True

policy_manager = ExecutionPolicyManager()
