# Merlin

## Overview
Merlin is a modular automation and AI assistant project designed to provide intelligent task execution, integration with other systems, and extensibility for custom workflows. It serves as a core component for orchestrating automation and AI-driven features across the workspace.

## Features
- Modular plugin architecture for extensibility
- Integration with automation suites and external APIs
- AI-assisted task execution and decision support
- Secure environment variable and secret management

## Getting Started

### Prerequisites
- Python 3.12+
- (Optional) Node.js for dashboard or web integrations
- See `.env.example` for required environment variables

### Setup
1. Clone the repository and navigate to the Merlin directory.
2. Create and activate a Python virtual environment:
   ```sh
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   ```
3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in required secrets.
5. Run the main assistant module:
   ```sh
   python main.py
   ```

## Usage
- Use the CLI or API endpoints to interact with the assistant.
- Extend functionality by adding plugins to the `plugins/` directory.
- See the `docs/` folder for advanced configuration and integration guides.

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Task Tracking
- Summary board: `artifacts/handoff/ACTIVE_TASKS.md`
- Detailed plan: `MERLIN_100_TASKS.md`

## License
MIT
