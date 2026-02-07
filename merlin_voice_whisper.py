import os
import requests
from merlin_logger import merlin_logger


class WhisperSTT:
    def __init__(
        self,
        api_key=None,
        base_url="https://api.openai.com/v1",
        model="whisper-1",
        language=None,
        timeout_s=60,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.model = model
        self.language = language
        self.timeout_s = timeout_s

    def transcribe(self, audio_file_path, model=None, language=None):
        if not self.api_key:
            merlin_logger.error("Whisper STT: No API key provided")
            return None

        merlin_logger.info(f"Transcribing {audio_file_path} using Whisper...")

        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": model or self.model}
        language_value = language if language is not None else self.language
        if language_value:
            data["language"] = language_value

        try:
            with open(audio_file_path, "rb") as audio_file:
                files = {"file": audio_file}
                response = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=self.timeout_s,
                )
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
