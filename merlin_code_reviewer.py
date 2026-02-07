# Merlin: The Automated Code Reviewer (Librarian's Wisdom)
import os
from merlin_logger import merlin_logger
import merlin_settings as settings
import requests


class MerlinCodeReviewer:
    def __init__(self):
        self.system_prompt = (
            "You are Merlin, a Master Code Architect. "
            "Analyze the provided code snippet for bugs, security risks, and optimization opportunities. "
            "Be critical but constructive. Focus on AAS compatibility and Python best practices."
        )

    def review_file(self, file_path):
        if not os.path.exists(file_path):
            return "File not found."

        with open(file_path, "r") as f:
            code = f.read()

        merlin_logger.info(f"Merlin is reviewing code: {file_path}")

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": f"Review this file: {os.path.basename(file_path)}\n\n```python\n{code}\n```",
                },
            ],
            "temperature": 0.2,
        }

        try:
            response = requests.post(settings.LM_STUDIO_URL, json=payload, timeout=60)
            review = response.json()["choices"][0]["message"]["content"]
            merlin_logger.info(f"Review complete for {file_path}")
            return review
        except Exception as e:
            merlin_logger.error(f"Review Error: {e}")
            return f"My neural link failed during review: {str(e)}"


# Singleton for system use
code_reviewer = MerlinCodeReviewer()
