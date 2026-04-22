"""
OAuth Authentication Server for AAS Achievement Linking

Provides HTTP endpoints for OAuth flows (GitHub, Google, GitLab).
Integrates with achievement linking system.

Usage:
    # Start server
    python -m genome.achievements.auth --port 8080
    
    # Or integrate into main app
    from genome.achievements.auth import create_auth_app
    import uvicorn
    uvicorn.run(create_auth_app(), host="0.0.0.0", port=8080)
"""

import os
import json
import logging
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional, Dict
from dataclasses import dataclass, field

from aas_kernel import get_path

logger = logging.getLogger("AAS-OAuth")


# OAuth Configuration
OAUTH_CONFIG = {
    "github": {
        "client_id": os.getenv("AAS_GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GITHUB_CLIENT_SECRET", ""),
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_url": "https://api.github.com/user",
        "scopes": ["read:user", "user:email"],
    },
    "google": {
        "client_id": os.getenv("AAS_GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GOOGLE_CLIENT_SECRET", ""),
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "gitlab": {
        "client_id": os.getenv("AAS_GITLAB_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GITLAB_CLIENT_SECRET", ""),
        "authorize_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "user_url": "https://gitlab.com/api/v4/user",
        "scopes": ["read_user"],
    },
}


@dataclass
class AuthSession:
    """OAuth session state."""
    session_id: str
    user_id: str  # AAS user_id to link to
    provider: str
    code_verifier: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat() + "Z")
    expires_at: Optional[str] = None
    completed: bool = False


class OAuthSessionStore:
    """Manages OAuth sessions in memory (could be Redis-backed)."""
    
    def __init__(self):
        self.sessions: Dict[str, AuthSession] = {}
        self._code_verifiers: Dict[str, str] = {}  # code -> verifier for PKCE
    
    def create_session(self, user_id: str, provider: str) -> tuple[str, str]:
        """Create new OAuth session. Returns (session_id, code_verifier)."""
        session_id = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        
        session = AuthSession(
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            code_verifier=code_verifier
        )
        
        self.sessions[session_id] = session
        self._code_verifiers[session_id] = code_verifier
        
        return session_id, code_verifier
    
    def get_session(self, session_id: str) -> Optional[AuthSession]:
        return self.sessions.get(session_id)
    
    def complete_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].completed = True
            # Clean up code verifier
            self._code_verifiers.pop(session_id, None)
    
    def delete_session(self, session_id: str):
        self.sessions.pop(session_id, None)
        self._code_verifiers.pop(session_id, None)


# Global session store
SESSION_STORE = OAuthSessionStore()


def generate_state(user_id: str) -> str:
    """Generate secure state parameter."""
    raw = f"{user_id}:{secrets.token_urlsafe(16)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def verify_state(state: str, expected_user_id: str) -> bool:
    """Verify state matches expected user_id."""
    # In production, store state in session/Redis with user_id mapping
    # For now, just validate format
    return len(state) == 32


async def get_authorization_url(provider: str, user_id: str, redirect_uri: str) -> tuple[str, str]:
    """Generate OAuth authorization URL."""
    config = OAUTH_CONFIG.get(provider)
    if not config:
        raise ValueError(f"Unknown provider: {provider}")
    
    if not config["client_id"]:
        raise ValueError(f"Provider {provider} not configured - missing client_id")
    
    session_id, code_verifier = SESSION_STORE.create_session(user_id, provider)
    
    # Build URL based on provider
    if provider == "github":
        scopes = "+".join(config["scopes"])
        url = (
            f"{config['authorize_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&state={session_id}"
        )
    elif provider == "google":
        scopes = "%20".join(config["scopes"])
        url = (
            f"{config['authorize_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&state={session_id}"
            f"&code_challenge={hashlib.sha256(code_verifier.encode()).digest().hex()[:43]}"
            f"&code_challenge_method=S256"
        )
    elif provider == "gitlab":
        scopes = config["scopes"]
        url = (
            f"{config['authorize_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={' '.join(scopes)}"
            f"&state={session_id}"
        )
    else:
        raise ValueError(f"Provider {provider} not supported")
    
    return url, session_id


async def exchange_code_for_token(provider: str, code: str, redirect_uri: str, session_id: str) -> Optional[dict]:
    """Exchange authorization code for access token."""
    import httpx
    
    config = OAUTH_CONFIG.get(provider)
    if not config:
        return None
    
    session = SESSION_STORE.get_session(session_id)
    if not session:
        return None
    
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri,
    }
    
    # Add code verifier for Google (PKCE)
    if provider == "google" and session.code_verifier:
        data["code_verifier"] = session.code_verifier
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=data,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
    
    return None


async def fetch_user_info(provider: str, access_token: str) -> Optional[dict]:
    """Fetch user info from provider."""
    import httpx
    
    config = OAUTH_CONFIG.get(provider)
    if not config:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                config["user_url"],
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
            )
            
            if response.status_code == 200:
                user_data = response.json()
                
                # Normalize user data
                if provider == "github":
                    return {
                        "provider": "github",
                        "provider_user_id": str(user_data.get("id")),
                        "username": user_data.get("login"),
                        "email": user_data.get("email"),
                        "name": user_data.get("name"),
                        "avatar_url": user_data.get("avatar_url"),
                    }
                elif provider == "google":
                    return {
                        "provider": "google",
                        "provider_user_id": user_data.get("id"),
                        "username": user_data.get("email").split("@")[0] if user_data.get("email") else None,
                        "email": user_data.get("email"),
                        "name": user_data.get("name"),
                        "avatar_url": user_data.get("picture"),
                    }
                elif provider == "gitlab":
                    return {
                        "provider": "gitlab",
                        "provider_user_id": str(user_data.get("id")),
                        "username": user_data.get("username"),
                        "email": user_data.get("email"),
                        "name": user_data.get("name"),
                        "avatar_url": user_data.get("avatar_url"),
                    }
    except Exception as e:
        logger.error(f"User info fetch failed: {e}")
    
    return None


async def complete_oauth_flow(provider: str, code: str, redirect_uri: str, session_id: str) -> Optional[dict]:
    """Complete OAuth flow and return user info."""
    # Exchange code for token
    token_data = await exchange_code_for_token(provider, code, redirect_uri, session_id)
    if not token_data:
        return {"error": "token_exchange_failed"}
    
    access_token = token_data.get("access_token")
    if not access_token:
        return {"error": "no_access_token"}
    
    # Fetch user info
    user_info = await fetch_user_info(provider, access_token)
    if not user_info:
        return {"error": "user_fetch_failed"}
    
    # Mark session complete
    SESSION_STORE.complete_session(session_id)
    
    return {
        "success": True,
        "provider": provider,
        "user_info": user_info,
        "token_data": {
            "access_token": access_token[:10] + "...",
            "token_type": token_data.get("token_type"),
            "expires_in": token_data.get("expires_in"),
        }
    }


def create_auth_app(host: str = "0.0.0.0", port: int = 8080):
    """Create FastAPI app for OAuth."""
    try:
        from fastapi import FastAPI, Query, HTTPException, Request
        from fastapi.responses import RedirectResponse, HTMLResponse
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        logger.error("FastAPI not installed. Run: pip install fastapi httpx uvicorn")
        return None
    
    app = FastAPI(title="AAS OAuth Server")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        return {"status": "aas_oauth_server", "version": "1.0.0"}
    
    @app.get("/auth/{provider}")
    async def auth_start(provider: str, user_id: str = Query(...), redirect_uri: str = Query(...)):
        """Start OAuth flow."""
        try:
            url, session_id = await get_authorization_url(provider, user_id, redirect_uri)
            return {"authorization_url": url, "session_id": session_id}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/auth/callback")
    async def auth_callback(provider: str, code: str = Query(...), state: str = Query(...), redirect_uri: str = Query(...)):
        """OAuth callback handler."""
        result = await complete_oauth_flow(provider, code, redirect_uri, state)
        
        if result and result.get("success"):
            # Redirect to success page with user info
            user_info = result["user_info"]
            return {
                "status": "linked",
                "provider": provider,
                "username": user_info.get("username"),
                "email": user_info.get("email"),
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "unknown_error"))
    
    @app.post("/auth/link")
    async def link_provider(user_id: str, provider: str, provider_user_id: str):
        """Manually link a provider (for testing or non-OAuth)."""
        from genome.achievements.integration import link_oauth
        return link_oauth(user_id, provider, provider_user_id)
    
    @app.get("/health")
    async def health():
        return {"status": "healthy"}
    
    return app


def main():
    """Run OAuth server."""
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description="AAS OAuth Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    args = parser.parse_args()
    
    app = create_auth_app()
    if app:
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        logger.error("Failed to create OAuth app")


if __name__ == "__main__":
    main()
