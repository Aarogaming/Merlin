import os
import sys
import platform
import subprocess
import shutil
from typing import List, Tuple
from urllib import request, error


def check_python_version() -> Tuple[bool, str]:
    version = platform.python_version()
    major, minor = sys.version_info[:2]
    if major == 3 and minor >= 10:
        return True, f"Python {version} detected (OK)"
    else:
        return False, f"Python {version} detected (Requires 3.10+)"


def check_dependencies() -> Tuple[bool, str]:
    if not os.path.exists("requirements.txt"):
        return False, "requirements.txt not found"

    try:
        # Simple check to see if some key packages are installed
        import fastapi
        import uvicorn
        import pydantic

        return True, "Core dependencies appear to be installed"
    except ImportError as e:
        return False, f"Missing dependency: {e.name}"


def check_env_file() -> Tuple[bool, str]:
    if os.path.exists(".env"):
        return True, ".env file found (OK)"
    elif os.path.exists(".env.example"):
        return False, ".env file missing (Found .env.example - please copy to .env)"
    else:
        return False, ".env and .env.example missing"


def check_directories() -> Tuple[bool, str]:
    required_dirs = ["logs", "merlin_chat_history", "plugins", "tests"]
    missing = [d for d in required_dirs if not os.path.isdir(d)]
    if not missing:
        return True, "All required directories present"
    else:
        return False, f"Missing directories: {', '.join(missing)}"


def check_api_connectivity() -> Tuple[bool, str]:
    candidates: List[str] = []

    explicit_health_url = os.getenv("AAS_HUB_HEALTH_URL", "").strip()
    if explicit_health_url:
        candidates.append(explicit_health_url)

    web_base = os.getenv("AAS_WEB_BASE_URL", "").strip()
    if web_base:
        candidates.append(f"{web_base.rstrip('/')}/health")

    web_host = os.getenv("AAS_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    web_port = os.getenv("AAS_WEB_PORT", "8000").strip() or "8000"
    candidates.append(f"http://{web_host}:{web_port}/health")

    opencode_host = os.getenv("AAS_OPENCODE_HOST", "127.0.0.1").strip() or "127.0.0.1"
    opencode_port = os.getenv("AAS_OPENCODE_PORT", "4096").strip() or "4096"
    candidates.append(f"http://{opencode_host}:{opencode_port}/global/health")

    seen = set()
    deduped_candidates = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        deduped_candidates.append(url)

    last_error = ""
    for url in deduped_candidates:
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=2.5) as response:
                status = getattr(response, "status", response.getcode())
            if int(status) < 500:
                return True, f"Connectivity OK via {url} (status={status})"
            last_error = f"{url} returned status {status}"
        except (error.URLError, error.HTTPError, TimeoutError) as exc:
            last_error = f"{url} failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{url} error: {exc}"

    if not deduped_candidates:
        return False, "No health endpoints configured"
    return (
        False,
        f"Connectivity failed across {len(deduped_candidates)} endpoint(s): {last_error}",
    )


def run_doctor():
    print("=" * 40)
    print("Merlin Merlin - Dev Environment Doctor")
    print("=" * 40)

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Environment File", check_env_file),
        ("Directory Structure", check_directories),
        ("API Connectivity", check_api_connectivity),
    ]

    all_passed = True
    for name, check_func in checks:
        passed, message = check_func()
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status:<7} {name:<20}: {message}")
        if not passed:
            all_passed = False

    print("=" * 40)
    if all_passed:
        print("Result: Environment looks healthy!")
    else:
        print("Result: Some issues were found. Please address them.")
    print("=" * 40)


if __name__ == "__main__":
    run_doctor()
