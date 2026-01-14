# LM Studio Agents - Merlin

This project can be worked on with local LM Studio agents. Use this doc as a standard checklist for agent runs.

## Quick start
1. Start LM Studio server: `lms server start --port 1234`
2. Choose a model and note it in your run log
3. Provide context: `README.md`, `docs/`, key config files
4. Run your agent tool (opencode, custom scripts, etc.)

## Suggested context files
- `README.md`
- `docs/` (if present)
- `package.json` / `pyproject.toml` / `*.sln` (as relevant)
- `.env.example` (if present)

## Safety and quality
- Do not include secrets in prompts or logs
- Prefer small, reversible changes
- Run lint/tests when possible
- Summarize changes and files touched

## Prompt starter
```
Goal: <what you want>
Constraints: <time, scope, dependencies>
Context: <paths you provided>
```

## Project notes
- Primary language: <fill in>
- Build/Test commands: <fill in>
- Key entrypoints: <fill in>
