from __future__ import annotations

from pathlib import Path

from merlin_voice import MerlinVoice
from merlin_voice_router import MerlinVoiceRouter


class _UnavailableEngine:
    def is_available(self) -> bool:
        return False

    def speak(self, text: str) -> bool:
        return False

    def synthesize_to_file(self, text: str, output_path: Path):
        return None


class _FailingEngine:
    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> bool:
        return False

    def synthesize_to_file(self, text: str, output_path: Path):
        return None


class _MetadataStubRouter:
    def __init__(self):
        self._metadata = {
            "fallback_to_text": True,
            "fallback_reason_code": "voice_engine_unavailable",
            "fallback_reason": "No configured voice engines are available.",
            "attempted_engines": ["xtts", "pyttsx3"],
            "available_engines_attempted": [],
            "selected_engine": None,
        }

    def speak(self, text: str, engine=None) -> bool:
        return False

    def synthesize_to_file(self, text: str, output_path=None, engine=None):
        return None

    def get_last_tts_metadata(self):
        return dict(self._metadata)

    def available_engines(self):
        return {"xtts": {"available": False}, "pyttsx3": {"available": False}}


def test_voice_router_records_failed_and_unavailable_fallback_codes(tmp_path: Path):
    router = MerlinVoiceRouter()
    router._engines = {
        "failing": _FailingEngine(),
        "down": _UnavailableEngine(),
    }

    assert router.speak("test", engine=["failing", "down"]) is False
    metadata = router.get_last_tts_metadata()
    assert metadata["fallback_to_text"] is True
    assert metadata["fallback_reason_code"] == "voice_engine_failed"
    assert metadata["attempted_engines"] == ["failing", "down"]
    assert metadata["available_engines_attempted"] == ["failing"]

    assert (
        router.synthesize_to_file(
            "test",
            output_path=tmp_path / "out.wav",
            engine=["down"],
        )
        is None
    )
    unavailable_metadata = router.get_last_tts_metadata()
    assert unavailable_metadata["fallback_reason_code"] == "voice_engine_unavailable"


def test_merlin_voice_emits_deterministic_text_fallback_metadata():
    voice = MerlinVoice()
    voice.router = _MetadataStubRouter()

    assert voice.speak("Need deterministic fallback metadata") is False
    first = voice.get_last_tts_fallback_metadata()
    fallback_id_first = first["text_fallback"]["fallback_id"]

    assert voice.speak("Need deterministic fallback metadata") is False
    second = voice.get_last_tts_fallback_metadata()
    fallback_id_second = second["text_fallback"]["fallback_id"]

    assert fallback_id_first == fallback_id_second
    assert second["text_fallback"]["mode"] == "text"
    assert second["text_fallback"]["reason_code"] == "voice_engine_unavailable"

    status = voice.status()
    assert "last_route" in status["tts"]
