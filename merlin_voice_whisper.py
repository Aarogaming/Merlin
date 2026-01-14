import os
import requests
from merlin_logger import merlin_logger

class WhisperSTT:
    def __init__(self, api_key=None, base_url="https://api.openai.com/v1"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url

    def transcribe(self, audio_file_path):
        if not self.api_key:
            merlin_logger.error("Whisper STT: No API key provided")
            return None

        merlin_logger.info(f"Transcribing {audio_file_path} using Whisper...")
        
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": open(audio_file_path, "rb")}
        data = {"model": "whisper-1"}

        try:
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            return response.json().get("text")
        except Exception as e:
            merlin_logger.error(f"Whisper STT Error: {e}")
            return None

# Example usage
if __name__ == "__main__":
    # stt = WhisperSTT()
    # print(stt.transcribe("path/to/audio.wav"))
    pass
