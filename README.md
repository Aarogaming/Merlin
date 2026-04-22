# AaroneousAutomationSuite (Agent-Zero)

**AAS is no longer a place; it is a protocol and a workforce.**

This repository exists strictly as **"Agent-Zero"**: the complete, versionable template version of the microkernel architecture that powers the rest of the federation. 

## Purpose
- **Template Basis:** Provides a clean, pristine example of the `boot.py`, plugin architecture, and `mcp-manifest.json` configurations.
- **Living Testbed:** Can be booted to establish stable testing for engines, new plugin formats, and core protocol changes without risking the production operations of active federation members.
- **Core Logistics:** Operates purely for logistics, telemetry, and system-wide analysis. It does *not* operate within the daily task workflows of the rest of the suite.

## How to create a new Federation Member
If you need to stand up a new dedicated specialist for the workforce:
1. Copy the `Workbench/templates/agent_core` folder to your new directory.
2. The `scripts/boot.py` dynamically infers its repository name from the folder it lives in.
3. Modify the `mcp-manifest.json` to declare the new member's capabilities.
4. Add your logic to the `plugins/` directory.
5. Run `python scripts/boot.py`. It will seamlessly join the event bus and wake the rest of the Suite.