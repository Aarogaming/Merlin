import subprocess
import sys
import os


def run_step(name: str, command: list):
    print(f"\n>>> Running {name}...")
    try:
        subprocess.run(command, check=True)
        print(f"✅ {name} passed!")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {name} failed!")
        return False
    except FileNotFoundError:
        print(f"⚠️ {name} skipped (tool not found)")
        return True


def main():
    print("=" * 40)
    print("Merlin Merlin - Quality Gates")
    print("=" * 40)

    # Determine python path (prefer venv if active)
    python_exe = sys.executable

    steps = [
        ("Formatting Check (Black)", [python_exe, "-m", "black", "--check", "."]),
        ("Type Check (Mypy)", [python_exe, "-m", "mypy", "."]),
        ("Unit Tests (Pytest)", [python_exe, "-m", "pytest"]),
    ]

    all_passed = True
    for name, cmd in steps:
        if not run_step(name, cmd):
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 All quality gates passed!")
        sys.exit(0)
    else:
        print("🚫 Some quality gates failed. Please fix the issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()
