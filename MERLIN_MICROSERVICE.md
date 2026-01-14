# Merlin Microservice Mode

This document outlines the plan for embedding Merlin as a microservice within the Aaroneous Automation Suite (AAS).

## 1. Architecture
Merlin will run as a standalone FastAPI service, communicating with other AAS components via:
- **REST API**: For synchronous requests (chat, system info).
- **WebSockets**: For real-time updates and voice streaming.
- **Shared Volume**: For accessing indexed resources and logs.

## 2. Integration Points
- **AAS Dashboard**: A widget to interact with Merlin.
- **AAS Automation Engine**: Merlin can trigger automations via the `/merlin/execute` endpoint.
- **AAS Security**: Centralized OAuth2 authentication instead of simple API keys.

## 3. Deployment
- **Docker**: Containerize the Merlin backend for easy deployment.
- **Environment Variables**: Use `.env` for all AAS-specific configurations.

## 4. Roadmap
- [ ] Containerize Merlin with Docker.
- [ ] Implement OAuth2 integration.
- [ ] Add WebSocket support for real-time events.
- [ ] Create AAS-specific plugins.
