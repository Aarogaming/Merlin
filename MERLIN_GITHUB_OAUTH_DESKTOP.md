# Merlin GitHub OAuth Desktop Integration Guide

This guide explains how to add "Sign in with GitHub" to your Electron desktop client and verify users in your Python FastAPI backend.

Note: OAuth bearer auth is a draft workflow. The Merlin API currently enforces `X-Merlin-Key` for `/merlin/*` endpoints.

---

## 1. Register a GitHub OAuth App
- Go to https://github.com/settings/developers and click "New OAuth App".
- Set the application name (e.g., Merlin Desktop).
- Set the homepage URL (e.g., http://localhost:3000/ or your app's info page).
- Set the Authorization callback URL to `http://localhost:12345/callback` (for local testing).
- Save and note your Client ID and Client Secret.

## 2. Electron Desktop OAuth Flow
- Use Electron's `shell.openExternal` to open the GitHub OAuth URL:
  - `https://github.com/login/oauth/authorize?client_id=YOUR_CLIENT_ID&scope=read:user user:email`
- Start a local HTTP server (e.g., on port 12345) in your Electron main process to receive the OAuth callback.
- When the user signs in, GitHub redirects to `http://localhost:12345/callback?code=...`.
- Exchange the code for an access token using GitHub's API:
  - POST to `https://github.com/login/oauth/access_token` with client_id, client_secret, code.
  - Parse the returned access token.
- Use the access token to call Merlin API endpoints (send as `Authorization: Bearer <token>` header).

## 3. Example Electron Main Process Code
```js
const { app, BrowserWindow, shell } = require('electron');
const http = require('http');
const fetch = require('node-fetch');

const CLIENT_ID = 'YOUR_CLIENT_ID';
const CLIENT_SECRET = 'YOUR_CLIENT_SECRET';
const REDIRECT_URI = 'http://localhost:12345/callback';

function startOAuthFlow(win) {
  const authUrl = `https://github.com/login/oauth/authorize?client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=read:user user:email`;
  shell.openExternal(authUrl);
  const server = http.createServer(async (req, res) => {
    if (req.url.startsWith('/callback')) {
      const url = new URL(req.url, REDIRECT_URI);
      const code = url.searchParams.get('code');
      // Exchange code for token
      const tokenResp = await fetch('https://github.com/login/oauth/access_token', {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new URLSearchParams({
          client_id: CLIENT_ID,
          client_secret: CLIENT_SECRET,
          code,
          redirect_uri: REDIRECT_URI
        })
      });
      const tokenData = await tokenResp.json();
      const accessToken = tokenData.access_token;
      // Store accessToken for API calls
      win.webContents.send('github-token', accessToken);
      res.end('GitHub sign-in complete. You can close this window.');
      server.close();
    }
  });
  server.listen(12345);
}
```

## 4. Example Merlin API Call with Token (Renderer)
```js
const { ipcRenderer } = require('electron');
let githubToken = null;
ipcRenderer.on('github-token', (event, token) => { githubToken = token; });

async function sendMerlinChat(userInput) {
  const resp = await fetch('http://localhost:8000/merlin/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${githubToken}`
    },
    body: JSON.stringify({ user_input: userInput })
  });
  // ...handle response...
}
```

## 5. FastAPI Backend: Verify GitHub Token
- Install `httpx` and `python-jose` if needed.
- In your FastAPI endpoints, extract the `Authorization` header.
- Call `https://api.github.com/user` with the token to verify and get user info.

```python
from fastapi import Request, HTTPException
import httpx

async def get_github_user(request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    token = auth.split(' ', 1)[1]
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.github.com/user', headers={'Authorization': f'Bearer {token}'})
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail='Invalid GitHub token')
        return resp.json()
```

- Use `await get_github_user(request)` in your endpoints to get the signed-in user.

---

This setup gives you secure, passwordless GitHub sign-in for your desktop Merlin client!
