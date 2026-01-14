import os
import subprocess
import sys
from merlin_logger import merlin_logger

def setup_staging():
    # Task 11: Set up a staging environment
    merlin_logger.info("Setting up Merlin Staging Environment...")
    
    # Create staging env file if not exists
    if not os.path.exists(".env.staging"):
        with open(".env.staging", "w") as f:
            f.write("MERLIN_API_PORT=8001\n")
            f.write("MERLIN_CHAT_HISTORY_DIR=merlin_chat_history_staging\n")
            f.write("REDIS_HOST=localhost\n")
            f.write("REDIS_PORT=6380\n")
            
    merlin_logger.info("Staging environment configured on port 8001.")

def run_staging():
    merlin_logger.info("Starting Merlin Staging Server...")
    # Load staging env and run
    os.environ["MERLIN_API_PORT"] = "8001"
    subprocess.Popen([sys.executable, "merlin_api_server.py"], shell=True)

if __name__ == "__main__":
    setup_staging()
    run_staging()
