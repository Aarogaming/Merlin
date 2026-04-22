#!/usr/bin/env python3
"""
AAS Protocol - Onboarding & Discovery Utility

MCP support is now native in mcp-manifest.json (overlays).
This utility helps discover and configure external access.

Usage:
    python scripts/mcp_tools.py --list        # List MCP tools
    python scripts/mcp_tools.py --config     # Generate VS Code config
    python scripts/mcp_tools.py --discover   # Discover all capabilities
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List

AAS_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = AAS_ROOT / "mcp-manifest.json"


class MCPBridge:
    """Multi-tier gateway for AAS capabilities."""

    def __init__(self):
        self.capabilities = []
        self.load_manifest()

    def load_manifest(self):
        """Load native overlay manifest."""
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH, 'r') as f:
                data = json.load(f)
                self.capabilities = data.get("capabilities", [])
        return self.capabilities

    def to_mcp_tools(self) -> List[Dict]:
        """Read MCP overlay directly - no translation needed."""
        tools = []
        for cap in self.capabilities:
            overlays = cap.get("overlays", {})
            mcp_data = overlays.get("mcp", {})
            tools.append({
                "name": mcp_data.get("name", cap.get("capability_id", "").replace("aaroneousautomationsuite_", "")),
                "description": cap.get("description", ""),
                "inputSchema": mcp_data.get("inputSchema", {"type": "object", "properties": {}})
            })
        return tools

    def to_nats_rich(self) -> List[Dict]:
        """Read NATS overlay directly - no translation needed."""
        routes = []
        for cap in self.capabilities:
            overlays = cap.get("overlays", {})
            nats_data = overlays.get("nats", {})
            routes.append({
                "capability_id": cap.get("capability_id"),
                "subject": nats_data.get("subject", ""),
                "description": cap.get("description"),
                "internal": overlays.get("internal", {})
            })
        return routes

    def to_internal_federation(self) -> Dict:
        """Tier 3: Internal - full AAS DNA + capabilities."""
        return {
            "repo": "AaroneousAutomationSuite",
            "capabilities": self.capabilities,
            "tiers": {
                "external_mcp": self.to_mcp_tools(),
                "nats_bridge": self.to_nats_rich()
            }
        }

    def generate_mcp_config(self) -> Dict:
        """Generate MCP server config (for .vscode/mcp.json)."""
        return {
            "servers": {
                "aaroneous": {
                    "command": sys.executable,
                    "args": [str(Path(__file__).resolve()), "--serve"],
                    "env": {}
                }
            }
        }

    def handle_mcp_request(self, tool_name: str, args: Dict) -> Dict:
        """Handle external MCP tool call - route to internal."""
        # Map MCP name back to capability_id
        capability_id = f"aaroneousautomationsuite_{tool_name}"

        for cap in self.capabilities:
            if cap.get("capability_id", "").replace("aaroneousautomationsuite_", "") == tool_name:
                # Route to NATS for execution
                return {
                    "status": "routed_to_nats",
                    "subject": cap.get("entry_point"),
                    "capability_id": capability_id,
                    "payload": args
                }

        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    def print_tiers(self):
        """Display all three tiers."""
        print("=== AAS MCP Bridge - Three Tiers ===\n")

        print("TIER 1: External MCP (Standard Tools)")
        print("-" * 40)
        for tool in self.to_mcp_tools():
            print(f"  {tool['name']}: {tool['description'][:50]}...")

        print("\nTIER 2: NATS Bridge (Rich Metadata)")
        print("-" * 40)
        for route in self.to_nats_rich()[:5]:
            print(f"  {route['capability_id']} -> {route['subject']}")
        print(f"  ... ({len(self.to_nats_rich())} total)")

        print("\nTIER 3: Internal Federation (Full DNA)")
        print("-" * 40)
        internal = self.to_internal_federation()
        print(f"  Repo: {internal['repo']}")
        print(f"  Capabilities: {len(internal['capabilities'])}")
        print(f"  Tiers exposed: {list(internal['tiers'].keys())}")


def main():
    parser = argparse.ArgumentParser(description="AAS Protocol - Onboarding & Discovery Utility")
    parser.add_argument("--list", action="store_true", help="List available MCP tools")
    parser.add_argument("--config", action="store_true", help="Generate VS Code MCP config")
    parser.add_argument("--discover", action="store_true", help="Discover all capabilities (MCP + NATS + Internal)")
    args = parser.parse_args()

    bridge = MCPBridge()

    if args.list:
        print(json.dumps(bridge.to_mcp_tools(), indent=2))
    elif args.config:
        config = bridge.generate_mcp_config()
        print(json.dumps(config, indent=2))
    elif args.discover:
        print(json.dumps(bridge.to_internal_federation(), indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
