import os
import sys
import subprocess
import shutil


def run_command(command: list, description: str):
    print(f"--- {description} ---")
    try:
        subprocess.run(command, check=True)
        print(f"Success: {description}")
    except subprocess.CalledProcessError as e:
        print(f"Error: {description} failed with exit code {e.returncode}")
        sys.exit(1)


def bootstrap():
    print("=" * 40)
    print("Merlin Merlin - Bootstrapping Script")
    print("=" * 40)

    # 1. Create virtual environment
    if not os.path.exists(".venv"):
        run_command(
            [sys.executable, "-m", "venv", ".venv"], "Creating virtual environment"
        )
    else:
        print("Virtual environment already exists.")

    # 2. Determine pip path
    if os.name == "nt":
        pip_path = os.path.join(".venv", "Scripts", "pip")
        python_path = os.path.join(".venv", "Scripts", "python")
    else:
        pip_path = os.path.join(".venv", "bin", "pip")
        python_path = os.path.join(".venv", "bin", "python")

    # 3. Install dependencies
    if os.path.exists("requirements.txt"):
        run_command(
            [pip_path, "install", "-r", "requirements.txt"], "Installing requirements"
        )

    if os.path.exists("requirements-dev.txt"):
        run_command(
            [pip_path, "install", "-r", "requirements-dev.txt"],
            "Installing dev requirements",
        )

    # 4. Setup .env
    if not os.path.exists(".env") and os.path.exists(".env.example"):
        print("Copying .env.example to .env")
        shutil.copy(".env.example", ".env")
    elif os.path.exists(".env"):
        print(".env already exists.")

    # 5. Create directories
    required_dirs = ["logs", "merlin_chat_history", "plugins", "tests"]
    for d in required_dirs:
        if not os.path.exists(d):
            print(f"Creating directory: {d}")
            os.makedirs(d)

    # 6. Run doctor
    print("\nRunning Merlin Doctor...")
    run_command([python_path, "merlin_doctor.py"], "Running environment check")

    print("\n" + "=" * 40)
    print("Bootstrapping complete! You can now start Merlin.")
    print("To activate the venv:")
    if os.name == "nt":
        print("  .venv\\Scripts\\activate")
    else:
        print("  source .venv/bin/activate")
    print("=" * 40)


if __name__ == "__main__":
    bootstrap()
