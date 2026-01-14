import os
import sys
import platform
import subprocess
import shutil
from typing import List, Tuple

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
    # This is a placeholder for a real connectivity check
    # In a real scenario, we might try to ping the local LLM or AAS Hub
    return True, "API connectivity check skipped (Placeholder)"

def run_doctor():
    print("="*40)
    print("Merlin Merlin - Dev Environment Doctor")
    print("="*40)
    
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
            
    print("="*40)
    if all_passed:
        print("Result: Environment looks healthy!")
    else:
        print("Result: Some issues were found. Please address them.")
    print("="*40)

if __name__ == "__main__":
    run_doctor()
