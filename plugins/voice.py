# Merlin Plugin: Voice (TTS/STT)
from pathlib import Path
from typing import Any, Optional


class MerlinVoicePlugin:
    def __init__(self):
        self.name = "voice"
        self.description = "Voice utilities (speak, transcribe, listen)."
        self.version = "1.0.0"
        self.author = "AAS"
        self._voice = None
        self._init_error: Optional[str] = None

    def _get_voice(self):
        if self._init_error:
            raise RuntimeError(self._init_error)
        if self._voice is None:
            try:
                from merlin_voice import MerlinVoice

                self._voice = MerlinVoice()
            except Exception as exc:
                self._init_error = str(exc)
                raise
        return self._voice

    def get_info(self):
        info = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }
        if self._init_error:
            info["init_error"] = self._init_error
        return info

    def execute(self, action: str, **kwargs: Any):
        if not action:
            return {"error": "action_required", "actions": ["speak", "transcribe", "listen", "synthesize"]}
        try:
            voice = self._get_voice()
        except Exception as exc:
            return {"error": "voice_init_failed", "detail": str(exc)}

        action = str(action).strip().lower()
        if action == "speak":
            text = kwargs.get("text")
            if not text:
                return {"error": "text_required"}
            engine = kwargs.get("engine")
            ok = voice.speak(text, engine=engine)
            return {"ok": bool(ok)}
        if action == "synthesize":
            text = kwargs.get("text")
            if not text:
                return {"error": "text_required"}
            output_path = kwargs.get("output_path")
            engine = kwargs.get("engine")
            result = voice.synthesize_to_file(
                text, output_path=output_path, engine=engine
            )
            return {"ok": bool(result), "path": str(result) if result else None}
        if action == "transcribe":
            audio_path = kwargs.get("audio_path")
            if not audio_path:
                return {"error": "audio_path_required"}
            engine = kwargs.get("engine")
            text = voice.transcribe_file(Path(audio_path), engine=engine)
            return {"text": text}
        if action == "listen":
            timeout = kwargs.get("timeout")
            phrase_time_limit = kwargs.get("phrase_time_limit")
            engine = kwargs.get("engine")
            text = voice.listen(
                timeout=timeout, phrase_time_limit=phrase_time_limit, engine=engine
            )
            return {"text": text}

        return {"error": "unsupported_action", "action": action}


def get_plugin():
    return MerlinVoicePlugin()
