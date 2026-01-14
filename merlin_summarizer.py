import requests
import json
import merlin_settings as settings
from merlin_logger import merlin_logger

class MerlinSummarizer:
    def __init__(self):
        self.model = settings.OPENAI_MODEL

    def summarize_chat(self, history: list) -> str:
        if not history:
            return ""
            
        merlin_logger.info(f"Summarizing chat history with {len(history)} messages...")
        
        # Format history for the LLM
        history_text = "\n".join([f"{'User' if 'user' in m else 'Merlin'}: {m.get('user', m.get('merlin'))}" for m in history])
        
        prompt = f"Please provide a concise summary of the following conversation history:\n\n{history_text}"
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }
        
        try:
            response = requests.post(settings.LM_STUDIO_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            summary = data['choices'][0]['message']['content']
            merlin_logger.info("Chat summarization complete.")
            return summary
        except Exception as e:
            merlin_logger.error(f"Summarization failed: {e}")
            return "Summary unavailable."

merlin_summarizer = MerlinSummarizer()
