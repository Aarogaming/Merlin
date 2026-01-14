# Merlin: Project Planning Checklist

## Actionable Recommendations (Completed)

- [x] P1: Add `merlin_settings.py` to centralize environment-driven config and chat history paths.
- [x] P1: Fix `merlin_api_server.py` initialization order and make host/port/CORS configurable.
- [x] P1: Add request validation and `/health` endpoint to the chat API.
- [x] P1: Clean up exported chat history zip files after download.
- [x] P1: Parameterize LLM endpoints/timeouts and add logging in `merlin_emotion_chat.py`.
- [x] P1: Implement `merlin_backup_to_drive.py` for Google Drive backups.
- [x] P1: Make scheduled backups configurable and idempotent per day.
- [x] P2: Add launcher env overrides and optional backup-on-start support.
- [x] P2: Make log cleanup retention configurable via env.
- [x] P3: Make reminder scheduler configurable and dedupe daily runs.
- [x] P3: Make config sync folder configurable via env.
- [x] P1: Enhance resource indexing with config-driven scan root, exclusions, limits, and relative paths.
- [x] P2: Expand `merlin_resource_config.json` with new scan options.
- [x] P1: Extend resource API with caching, refresh/stats endpoints, and pagination.
- [x] P2: Add `merlin_resource_cli.py` for quick index queries.
- [x] P3: Update `MERLIN_RESOURCE_INDEXER.md` with config + usage + CLI examples.
- [x] P2: Add `.env.example` with supported runtime variables.
- [x] P2: Add `requirements.txt` for repeatable dependency installs.
- [x] P2: Update `SETUP_MERLIN_BACKEND.md` for the new workflow.
- [x] P3: Add repo hygiene docs (README + `.gitignore`).

## Project Setup

- [x] Create `Merlin/` directory for Merlin
- [x] Draft initial design and planning document (`MERLIN_DESIGN.md`)
- [x] Review and iterate on design with community feedback

## Architecture

- [x] Finalize tech stack (Python backend, web frontend, LLM integration)
- [x] Define API contracts (REST/WebSocket)
- [x] Plan plugin/module system

## MVP Features

- [x] Chat UI (text)
- [x] Backend command execution
- [x] File management
- [x] System info
- [x] LLM integration
- [x] Authentication & permissions

## Extensibility

- [x] Plugin system scaffolding
- [ ] Logging & diagnostics
- [x] Unit/integration test setup

## Resource Indexing & Inventory

- [x] Build resource indexer module (scan/catalog scripts, sounds, docs)
- [x] Document available resources for Merlin
- [x] Enable dynamic inventory refresh

## AAS/PM Sync & Security

- [ ] Regularly check AAS/PM context/docs for updates
- [ ] Implement permission checks and logging for resource access

## Voice Integration (Future)

- [ ] Abstract TTS/STT interfaces
- [ ] UI hooks for voice

## Mobile & AAS Integration

- [ ] Responsive web UI
- [ ] Plan for native app
- [ ] Microservice/plugin mode for AAS

## Community Feedback

- [ ] Share design doc for review
- [ ] Collect and incorporate suggestions

---

*Update this checklist as Merlin evolves!*
