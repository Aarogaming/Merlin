# Contributing

Thank you for your interest in contributing to Merlin!

## Before you start
- Check for open issues or discussions in the repository.
- Propose significant changes via an issue before submitting a PR.
- Do not commit secrets or credentials.

## Development setup
- Install dependencies: `pip install -r requirements.txt`
- Lint: `flake8 .`
- Format: `black .`
- Test: `pytest`
- Run: `python main.py`

## Branching and commits
- Branch naming: `feature/<short-description>`, `bugfix/<short-description>`
- Commit message style: Use imperative mood (e.g., "Add new plugin system")
- PRs should include: summary, testing notes, screenshots (if UI)

## Code style
- Follow PEP8 and the repo's `.editorconfig` rules.
- Document public interfaces and modules.
- Add or update tests for new or changed behavior.

## Reporting issues
Include:
- Steps to reproduce
- Expected vs actual behavior
- Logs or screenshots if relevant

## Security
If you find a security issue, do not open a public issue. Contact the maintainer directly.
