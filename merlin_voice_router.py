import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Optional

import merlin_settings as settings
from merlin_logger import merlin_logger


def _safe_text(text: str) -> str:
    cleaned = (text or "").strip()
    return cleaned if cleaned else "..."


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _play_audio_file(path: Path) -> bool:
    if not settings.MERLIN_VOICE_PLAYBACK:
        return False
    command = settings.MERLIN_VOICE_PLAYBACK_COMMAND
    if command:
        try:
            subprocess.run([command, str(path)], check=True)
            return True
        except Exception as exc:
            merlin_logger.warning(f"Voice playback failed ({command}): {exc}")
            return False

    for player in ("aplay", "ffplay", "play"):
        if shutil.which(player):
            args = [player, str(path)]
            if player == "ffplay":
                args = [player, "-nodisp", "-autoexit", str(path)]
            try:
                subprocess.run(
                    args,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception as exc:
                merlin_logger.warning(f"Voice playback failed ({player}): {exc}")
                return False
    return False


class VoiceEngine:
    name = "base"

    def is_available(self) -> bool:
        return False

    def speak(self, text: str) -> bool:
        return False

    def synthesize_to_file(self, text: str, output_path: Path) -> Optional[Path]:
        return None


class Pyttsx3Engine(VoiceEngine):
    name = "pyttsx3"

    def __init__(self) -> None:
        self._engine = None
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
        except Exception as exc:
            merlin_logger.warning(f"pyttsx3 unavailable: {exc}")

    def is_available(self) -> bool:
        return self._engine is not None

    def speak(self, text: str) -> bool:
        if not self._engine:
            return False
        try:
            self._engine.say(_safe_text(text))
            self._engine.runAndWait()
            return True
        except Exception as exc:
            merlin_logger.error(f"pyttsx3 speak failed: {exc}")
            return False

    def synthesize_to_file(self, text: str, output_path: Path) -> Optional[Path]:
        if not self._engine:
            return None
        try:
            self._engine.save_to_file(_safe_text(text), str(output_path))
            self._engine.runAndWait()
            return output_path
        except Exception as exc:
            merlin_logger.warning(f"pyttsx3 save failed: {exc}")
            return None


class PiperEngine(VoiceEngine):
    name = "piper"

    def __init__(self) -> None:
        self._piper_path = settings.MERLIN_VOICE_PIPER_PATH or "piper"
        self._model_path = settings.MERLIN_VOICE_PIPER_MODEL

    def is_available(self) -> bool:
        if not self._model_path:
            return False
        return bool(shutil.which(self._piper_path)) and Path(self._model_path).exists()

    def _build_command(self, output_path: Path) -> list[str]:
        cmd = [
            self._piper_path,
            "--model",
            self._model_path,
            "--output_file",
            str(output_path),
        ]
        if settings.MERLIN_VOICE_PIPER_SPEAKER_ID is not None:
            cmd.extend(["--speaker", str(settings.MERLIN_VOICE_PIPER_SPEAKER_ID)])
        if settings.MERLIN_VOICE_PIPER_LENGTH_SCALE is not None:
            cmd.extend(
                ["--length_scale", str(settings.MERLIN_VOICE_PIPER_LENGTH_SCALE)]
            )
        if settings.MERLIN_VOICE_PIPER_NOISE_SCALE is not None:
            cmd.extend(["--noise_scale", str(settings.MERLIN_VOICE_PIPER_NOISE_SCALE)])
        if settings.MERLIN_VOICE_PIPER_NOISE_W is not None:
            cmd.extend(["--noise_w", str(settings.MERLIN_VOICE_PIPER_NOISE_W)])
        return cmd

    def synthesize_to_file(self, text: str, output_path: Path) -> Optional[Path]:
        if not self.is_available():
            return None
        try:
            cmd = self._build_command(output_path)
            subprocess.run(cmd, input=_safe_text(text), text=True, check=True)
            return output_path
        except Exception as exc:
            merlin_logger.error(f"Piper synthesis failed: {exc}")
            return None

    def speak(self, text: str) -> bool:
        output_path = _temp_voice_path("piper")
        result = self.synthesize_to_file(text, output_path)
        if not result:
            return False
        _play_audio_file(result)
        return True


class XttsEngine(VoiceEngine):
    name = "xtts"

    def __init__(self) -> None:
        self._tts = None
        self._load_attempted = False

    def _load(self) -> bool:
        if self._load_attempted:
            return self._tts is not None
        self._load_attempted = True
        if not settings.MERLIN_VOICE_XTTS_MODEL:
            merlin_logger.warning("XTTS model not configured.")
            return False
        try:
            from TTS.api import TTS
        except Exception as exc:
            merlin_logger.warning(f"XTTS import failed: {exc}")
            return False
        try:
            self._tts = TTS(settings.MERLIN_VOICE_XTTS_MODEL)
            self._tts = self._tts.to(settings.MERLIN_VOICE_XTTS_DEVICE)
            return True
        except Exception as exc:
            merlin_logger.error(f"XTTS load failed: {exc}")
            self._tts = None
            return False

    def is_available(self) -> bool:
        return self._load()

    def synthesize_to_file(self, text: str, output_path: Path) -> Optional[Path]:
        if not self._load():
            return None
        try:
            kwargs = {
                "text": _safe_text(text),
                "file_path": str(output_path),
            }
            if settings.MERLIN_VOICE_REFERENCE_WAV:
                kwargs["speaker_wav"] = settings.MERLIN_VOICE_REFERENCE_WAV
            if settings.MERLIN_VOICE_XTTS_LANGUAGE:
                kwargs["language"] = settings.MERLIN_VOICE_XTTS_LANGUAGE
            self._tts.tts_to_file(**kwargs)
            return output_path
        except Exception as exc:
            merlin_logger.error(f"XTTS synthesis failed: {exc}")
            return None

    def speak(self, text: str) -> bool:
        output_path = _temp_voice_path("xtts")
        result = self.synthesize_to_file(text, output_path)
        if not result:
            return False
        _play_audio_file(result)
        return True


def _temp_voice_path(engine_name: str) -> Path:
    base_dir = Path(settings.MERLIN_VOICE_CACHE_DIR or "artifacts/voice")
    _ensure_dir(base_dir)
    filename = f"{engine_name}_{uuid.uuid4().hex}.wav"
    return base_dir / filename


class MerlinVoiceRouter:
    def __init__(self) -> None:
        self._engines = {
            "pyttsx3": Pyttsx3Engine(),
            "piper": PiperEngine(),
            "xtts": XttsEngine(),
        }
        self._last_tts_metadata: dict[str, Any] = {
            "fallback_to_text": False,
            "fallback_reason_code": None,
            "fallback_reason": None,
            "attempted_engines": [],
            "available_engines_attempted": [],
            "selected_engine": None,
        }

    def _record_tts_metadata(
        self,
        *,
        attempted_engines: list[str],
        available_engines_attempted: list[str],
        selected_engine: str | None,
        fallback_to_text: bool,
        fallback_reason_code: str | None,
        fallback_reason: str | None,
    ) -> None:
        self._last_tts_metadata = {
            "fallback_to_text": fallback_to_text,
            "fallback_reason_code": fallback_reason_code,
            "fallback_reason": fallback_reason,
            "attempted_engines": attempted_engines,
            "available_engines_attempted": available_engines_attempted,
            "selected_engine": selected_engine,
        }

    def get_last_tts_metadata(self) -> dict[str, Any]:
        return dict(self._last_tts_metadata)

    def _route_order(self, preferred: str | list[str] | None = None) -> list[str]:
        order: list[str] = []
        if preferred:
            if isinstance(preferred, (list, tuple)):
                order.extend([str(name) for name in preferred if name])
            else:
                order.append(str(preferred))
        primary = settings.MERLIN_VOICE_PRIMARY_ENGINE
        fallback = settings.MERLIN_VOICE_FALLBACK_ENGINE
        order.extend([primary, fallback, "pyttsx3"])
        cleaned: list[str] = []
        seen = set()
        for name in order:
            if not name:
                continue
            key = str(name).strip().lower()
            if key in seen or key not in self._engines:
                continue
            seen.add(key)
            cleaned.append(key)
        return cleaned

    def available_engines(self) -> dict[str, dict[str, bool]]:
        return {
            name: {"available": engine.is_available()}
            for name, engine in self._engines.items()
        }

    def speak(self, text: str, engine: str | list[str] | None = None) -> bool:
        attempted_engines: list[str] = []
        available_engines_attempted: list[str] = []

        for name in self._route_order(engine):
            attempted_engines.append(name)
            engine_instance = self._engines.get(name)
            if not engine_instance or not engine_instance.is_available():
                continue
            available_engines_attempted.append(name)
            if engine_instance.speak(text):
                self._record_tts_metadata(
                    attempted_engines=attempted_engines,
                    available_engines_attempted=available_engines_attempted,
                    selected_engine=name,
                    fallback_to_text=False,
                    fallback_reason_code=None,
                    fallback_reason=None,
                )
                return True

        fallback_reason_code = (
            "voice_engine_unavailable"
            if not available_engines_attempted
            else "voice_engine_failed"
        )
        fallback_reason = (
            "No configured voice engines are available."
            if not available_engines_attempted
            else "All available voice engines failed."
        )
        self._record_tts_metadata(
            attempted_engines=attempted_engines,
            available_engines_attempted=available_engines_attempted,
            selected_engine=None,
            fallback_to_text=True,
            fallback_reason_code=fallback_reason_code,
            fallback_reason=fallback_reason,
        )
        return False

    def synthesize_to_file(
        self,
        text: str,
        output_path: Optional[Path] = None,
        engine: str | list[str] | None = None,
    ) -> Optional[Path]:
        if output_path is None:
            output_path = _temp_voice_path("tts")
        elif not isinstance(output_path, Path):
            output_path = Path(output_path)
        attempted_engines: list[str] = []
        available_engines_attempted: list[str] = []

        for name in self._route_order(engine):
            attempted_engines.append(name)
            engine_instance = self._engines.get(name)
            if not engine_instance or not engine_instance.is_available():
                continue
            available_engines_attempted.append(name)
            result = engine_instance.synthesize_to_file(text, output_path)
            if result:
                self._record_tts_metadata(
                    attempted_engines=attempted_engines,
                    available_engines_attempted=available_engines_attempted,
                    selected_engine=name,
                    fallback_to_text=False,
                    fallback_reason_code=None,
                    fallback_reason=None,
                )
                return result

        fallback_reason_code = (
            "voice_engine_unavailable"
            if not available_engines_attempted
            else "voice_engine_failed"
        )
        fallback_reason = (
            "No configured voice engines are available."
            if not available_engines_attempted
            else "All available voice engines failed."
        )
        self._record_tts_metadata(
            attempted_engines=attempted_engines,
            available_engines_attempted=available_engines_attempted,
            selected_engine=None,
            fallback_to_text=True,
            fallback_reason_code=fallback_reason_code,
            fallback_reason=fallback_reason,
        )
        return None
