# Merlin Merlin Backend Setup (Python 3.12)

## 1. Create and Activate Virtual Environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate  # Windows
# Or: source .venv/bin/activate  # macOS/Linux
```

## 2. Install Required Packages

```bash
pip install -r requirements.txt
```

## 3. Configure Environment

- Copy `.env.example` to `.env` and set API keys/paths.
- Adjust `merlin_resource_config.json` if you want a different scan root or exclusions.

## 4. (Optional) Install All AAS-Compatible Packages

```bash
pip install -r ../AaroneousAutomationSuite/requirements.txt
```

## 5. Build Resource Index

```bash
python merlin_resource_indexer.py
```

## 6. Run Merlin Resource API

```bash
uvicorn merlin_resource_api:app --reload
```

## 7. Run Merlin Chat API

```bash
uvicorn merlin_api_server:app --reload
```

---

*This ensures Merlin’s backend matches AAS and PM for maximum compatibility.*
