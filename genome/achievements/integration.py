"""
Achievement Link Integration with Lifecycle

Example of how achievement linking integrates with AAS lifecycle.
Also provides MCP-compatible tool handlers.
"""

from genome.achievements.link import AchievementLinkManager, AuthProvider

LINK_MANAGER = None


def get_link_manager():
    """Get or create the achievement link manager."""
    global LINK_MANAGER
    if LINK_MANAGER is None:
        LINK_MANAGER = AchievementLinkManager()
    return LINK_MANAGER


def create_user_identity(display_name: str) -> dict:
    """Create a new user identity for achievement linking."""
    manager = get_link_manager()
    identity = manager.create_identity(display_name)
    return {
        "user_id": identity.user_id,
        "display_name": identity.display_name,
        "created_at": identity.created_at
    }


def link_oauth(user_id: str, provider: str, provider_user_id: str) -> dict:
    """Link an OAuth provider to a user identity."""
    manager = get_link_manager()
    try:
        auth_provider = AuthProvider(provider)
        success = manager.link_provider(user_id, auth_provider, provider_user_id)
        return {"success": success, "user_id": user_id, "provider": provider}
    except ValueError as e:
        return {"success": False, "error": str(e)}


def generate_agent_link(agent_id: str, user_id: str) -> dict:
    """Generate a link code for binding an AAS agent to a user."""
    manager = get_link_manager()
    code = manager.generate_link_code(agent_id, user_id)
    return {"agent_id": agent_id, "user_id": user_id, "link_code": code}


def verify_link(agent_id: str, code: str) -> dict:
    """Verify link code and return user_id."""
    manager = get_link_manager()
    user_id = manager.verify_link_code(agent_id, code)
    if user_id:
        return {"success": True, "user_id": user_id, "agent_id": agent_id}
    return {"success": False, "error": "Invalid or expired link code"}


def link_achievement_on_unlock(achievement: dict, agent_id: str, source_aas: str = "local") -> dict:
    """
    Called when an achievement is unlocked.
    Attempts to link it to a user if agent is bound.
    """
    manager = get_link_manager()
    linked = manager.link_achievement(achievement, agent_id, source_aas)
    
    if linked:
        link = manager.links.get(agent_id)
        if link:
            return {"linked": True, "user_id": link.user_id}
    
    return {"linked": False}


def get_user_profile(user_id: str) -> dict:
    """Get a user's complete achievement profile."""
    manager = get_link_manager()
    return manager.get_user_stats(user_id)


def export_for_cloud_sync(user_id: str) -> dict:
    """Export user data for cloud sync."""
    manager = get_link_manager()
    return manager.export_user_data(user_id)


# MCP Tool Handlers - called by NATS/MCP bridge

def mcp_achievement_link_identity(args: dict) -> dict:
    """MCP tool: create_user_identity"""
    display_name = args.get("display_name", "")
    if not display_name:
        return {"error": "display_name is required"}
    return create_user_identity(display_name)


def mcp_achievement_link_oauth(args: dict) -> dict:
    """MCP tool: link_oauth"""
    user_id = args.get("user_id", "")
    provider = args.get("provider", "")
    provider_user_id = args.get("provider_user_id", "")
    
    if not all([user_id, provider, provider_user_id]):
        return {"error": "user_id, provider, and provider_user_id are required"}
    
    return link_oauth(user_id, provider, provider_user_id)


def mcp_achievement_generate_link_code(args: dict) -> dict:
    """MCP tool: generate_link_code"""
    agent_id = args.get("agent_id", "")
    user_id = args.get("user_id", "")
    
    if not all([agent_id, user_id]):
        return {"error": "agent_id and user_id are required"}
    
    return generate_agent_link(agent_id, user_id)


def mcp_achievement_verify_link(args: dict) -> dict:
    """MCP tool: verify_link"""
    agent_id = args.get("agent_id", "")
    code = args.get("code", "")
    
    if not all([agent_id, code]):
        return {"error": "agent_id and code are required"}
    
    return verify_link(agent_id, code)


def mcp_achievement_get_profile(args: dict) -> dict:
    """MCP tool: get_user_profile"""
    user_id = args.get("user_id", "")
    
    if not user_id:
        return {"error": "user_id is required"}
    
    return get_user_profile(user_id)


def mcp_achievement_export_cloud(args: dict) -> dict:
    """MCP tool: export_for_cloud_sync"""
    user_id = args.get("user_id", "")
    
    if not user_id:
        return {"error": "user_id is required"}
    
    return export_for_cloud_sync(user_id)


# Tool registry for easy lookup
MCP_TOOLS = {
    "achievement_link_identity": mcp_achievement_link_identity,
    "achievement_link_oauth": mcp_achievement_link_oauth,
    "achievement_generate_link_code": mcp_achievement_generate_link_code,
    "achievement_verify_link": mcp_achievement_verify_link,
    "achievement_get_profile": mcp_achievement_get_profile,
    "achievement_export_cloud": mcp_achievement_export_cloud,
}


def handle_mcp_tool(tool_name: str, args: dict) -> dict:
    """Route MCP tool call to appropriate handler."""
    handler = MCP_TOOLS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(args)
