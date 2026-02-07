import logging
import uuid
from pathlib import Path

import speech_recognition as sr

import merlin_settings as settings
from merlin_voice_router import MerlinVoiceRouter
from merlin_voice_whisper import WhisperSTT


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _temp_audio_path(suffix: str = ".wav") -> Path:
    base_dir = Path(settings.MERLIN_VOICE_CACHE_DIR or "artifacts/voice") / "stt"
    _ensure_dir(base_dir)
    return base_dir / f"stt_{uuid.uuid4().hex}{suffix}"


class MerlinVoice:
    def __init__(self):
        self.router = MerlinVoiceRouter()
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = settings.MERLIN_STT_DYNAMIC_ENERGY
        if settings.MERLIN_STT_ENERGY_THRESHOLD is not None:
            self.recognizer.energy_threshold = settings.MERLIN_STT_ENERGY_THRESHOLD
        self._whisper = None
        self._whisper_failed = False

    def _normalize_engine(self, name: str | None) -> str:
        if not name:
            return ""
        value = str(name).strip().lower()
        if value in {"speech_recognition", "speechrecognition", "sr"}:
            return "google"
        return value

    def _stt_route_order(self, preferred: str | list[str] | None = None) -> list[str]:
        order: list[str] = []
        if preferred:
            if isinstance(preferred, (list, tuple)):
                order.extend([self._normalize_engine(item) for item in preferred])
            else:
                order.append(self._normalize_engine(preferred))
        order.extend(
            [
                self._normalize_engine(settings.MERLIN_STT_PRIMARY_ENGINE),
                self._normalize_engine(settings.MERLIN_STT_FALLBACK_ENGINE),
                "google",
            ]
        )
        cleaned: list[str] = []
        seen = set()
        for name in order:
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append(name)
        return cleaned

    def _get_whisper(self) -> WhisperSTT | None:
        if self._whisper_failed:
            return None
        if self._whisper is None:
            try:
                self._whisper = WhisperSTT(
                    api_key=settings.OPENAI_API_KEY or None,
                    base_url=settings.MERLIN_STT_WHISPER_BASE_URL,
                    model=settings.MERLIN_STT_WHISPER_MODEL,
                    language=settings.MERLIN_STT_WHISPER_LANGUAGE or None,
                    timeout_s=settings.MERLIN_STT_WHISPER_TIMEOUT_S or 60,
                )
            except Exception as exc:
                logging.warning(f"Whisper STT init failed: {exc}")
                self._whisper_failed = True
                return None
        return self._whisper

    def _transcribe_with_google(self, audio: sr.AudioData) -> str | None:
        try:
            return self.recognizer.recognize_google(
                audio, language=settings.MERLIN_STT_GOOGLE_LANGUAGE
            )
        except Exception as exc:
            logging.warning(f"Google STT failed: {exc}")
            return None

    def _transcribe_file_google(self, audio_path: Path) -> str | None:
        try:
            with sr.AudioFile(str(audio_path)) as source:
                audio = self.recognizer.record(source)
            return self._transcribe_with_google(audio)
        except Exception as exc:
            logging.warning(f"Google STT file failed: {exc}")
            return None

    def _transcribe_file_whisper(self, audio_path: Path) -> str | None:
        whisper = self._get_whisper()
        if not whisper:
            return None
        return whisper.transcribe(
            str(audio_path),
            model=settings.MERLIN_STT_WHISPER_MODEL,
            language=settings.MERLIN_STT_WHISPER_LANGUAGE or None,
        )

    def _transcribe_audio_whisper(self, audio: sr.AudioData) -> str | None:
        temp_path = _temp_audio_path(".wav")
        try:
            with temp_path.open("wb") as handle:
                handle.write(audio.get_wav_data())
            return self._transcribe_file_whisper(temp_path)
        finally:
            if not settings.MERLIN_VOICE_KEEP_TEMP_AUDIO and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def speak(self, text: str, engine: str | list[str] | None = None) -> bool:
        try:
            logging.info(f"Speaking: {text}")
            return self.router.speak(text, engine=engine)
        except Exception as e:
            logging.error(f"TTS Error: {e}")
            return False

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path | None = None,
        engine: str | list[str] | None = None,
    ):
        try:
            return self.router.synthesize_to_file(
                text, output_path=output_path, engine=engine
            )
        except Exception as e:
            logging.error(f"TTS Synthesis Error: {e}")
            return None

    def transcribe_file(
        self, audio_path: str | Path, engine: str | list[str] | None = None
    ):
        path = Path(audio_path)
        if not path.exists():
            logging.warning(f"STT file missing: {path}")
            return None
        for engine_name in self._stt_route_order(engine):
            if engine_name == "whisper":
                text = self._transcribe_file_whisper(path)
            elif engine_name == "google":
                text = self._transcribe_file_google(path)
            else:
                continue
            if text:
                logging.info(f"STT ({engine_name}) -> {text}")
                return text
        return None

    def listen(
        self,
        timeout: float | None = None,
        phrase_time_limit: float | None = None,
        engine: str | list[str] | None = None,
    ):
        try:
            with sr.Microphone() as source:
                logging.info("Listening...")
                audio = self.recognizer.listen(
                    source,
                    timeout=(
                        timeout
                        if timeout is not None
                        else settings.MERLIN_STT_TIMEOUT_S
                    ),
                    phrase_time_limit=(
                        phrase_time_limit
                        if phrase_time_limit is not None
                        else settings.MERLIN_STT_PHRASE_TIME_LIMIT_S
                    ),
                )
            for engine_name in self._stt_route_order(engine):
                if engine_name == "whisper":
                    text = self._transcribe_audio_whisper(audio)
                elif engine_name == "google":
                    text = self._transcribe_with_google(audio)
                else:
                    continue
                if text:
                    logging.info(f"Recognized ({engine_name}): {text}")
                    return text
            return None
        except sr.WaitTimeoutError:
            logging.warning("Listening timed out")
            return None
        except Exception as e:
            logging.error(f"STT Error: {e}")
            return None

    def status(self) -> dict:
        tts_status = {
            "primary": settings.MERLIN_VOICE_PRIMARY_ENGINE,
            "fallback": settings.MERLIN_VOICE_FALLBACK_ENGINE,
            "engines": self.router.available_engines(),
        }
        whisper = self._get_whisper()
        stt_status = {
            "primary": settings.MERLIN_STT_PRIMARY_ENGINE,
            "fallback": settings.MERLIN_STT_FALLBACK_ENGINE,
            "google_language": settings.MERLIN_STT_GOOGLE_LANGUAGE,
            "whisper_model": settings.MERLIN_STT_WHISPER_MODEL,
            "whisper_language": settings.MERLIN_STT_WHISPER_LANGUAGE or None,
            "engines": {
                "google": True,
                "whisper": bool(getattr(whisper, "api_key", None)),
            },
        }
        return {"tts": tts_status, "stt": stt_status}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    voice = MerlinVoice()
    voice.speak("Hello, I am Merlin. How can I help you today?")
