#!/usr/bin/env python3
import argparse
import csv
import json
import random
from pathlib import Path

DEFAULT_SOURCES_FILE = Path(__file__).with_name("merlin_voice_sources.json")


def _load_sources(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_sources(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _read_wav_duration(path: Path) -> float | None:
    import wave

    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def _pick_ljspeech(root: Path) -> Path | None:
    metadata_path = root / "metadata.csv"
    wav_dir = root / "wavs"
    if not metadata_path.exists() or not wav_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    with metadata_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="|")
        for row in reader:
            if not row:
                continue
            wav_name = row[0] + ".wav"
            wav_path = wav_dir / wav_name
            if not wav_path.exists():
                continue
            duration = _read_wav_duration(wav_path)
            if duration is None:
                continue
            if 10.0 <= duration <= 25.0:
                candidates.append((duration, wav_path))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    longest = None
    for wav_path in wav_dir.glob("*.wav"):
        duration = _read_wav_duration(wav_path)
        if duration is None:
            continue
        if longest is None or duration > longest[0]:
            longest = (duration, wav_path)
    return longest[1] if longest else None


def _parse_vctk_speaker_info(info_path: Path) -> list[dict]:
    entries = []
    with info_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("ID"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            speaker_id = parts[0]
            gender = parts[1]
            age = parts[2]
            region = " ".join(parts[3:])
            entries.append(
                {
                    "id": speaker_id,
                    "gender": gender,
                    "age": age,
                    "region": region,
                }
            )
    return entries


def _pick_vctk(root: Path) -> Path | None:
    info_path = root / "speaker-info.txt"
    wav_root = root / "wav48_silence_trimmed"
    if not wav_root.exists():
        wav_root = root / "wav48"
    if not info_path.exists() or not wav_root.exists():
        return None
    speakers = _parse_vctk_speaker_info(info_path)
    preferred = [
        s
        for s in speakers
        if s["gender"].lower() == "m"
        and any(
            tag in s["region"].lower()
            for tag in ("england", "english", "scotland", "wales")
        )
    ]
    pool = (
        preferred if preferred else [s for s in speakers if s["gender"].lower() == "m"]
    )
    if not pool:
        return None
    pool.sort(key=lambda item: item["id"])
    for speaker in pool:
        speaker_dir = wav_root / speaker["id"]
        if not speaker_dir.exists():
            continue
        candidates = []
        for wav_path in speaker_dir.glob("*.wav"):
            duration = _read_wav_duration(wav_path)
            if duration is None:
                continue
            if 10.0 <= duration <= 25.0:
                candidates.append((duration, wav_path))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]
        fallback = next(iter(speaker_dir.glob("*.wav")), None)
        if fallback:
            return fallback
    return None


def _pick_libritts(root: Path) -> Path | None:
    if not root.exists():
        return None
    audio_files = list(root.rglob("*.wav"))
    if not audio_files:
        audio_files = list(root.rglob("*.flac"))
    if not audio_files:
        return None
    random.shuffle(audio_files)
    # Prefer longer wavs when possible.
    for wav_path in audio_files[:500]:
        if wav_path.suffix.lower() != ".wav":
            continue
        duration = _read_wav_duration(wav_path)
        if duration and 10.0 <= duration <= 25.0:
            return wav_path
    return audio_files[0]


def update_sources(
    sources_file: Path,
    ljspeech_root: Path | None,
    vctk_root: Path | None,
    libritts_root: Path | None,
) -> dict:
    payload = _load_sources(sources_file)
    sources = payload.get("sources", [])
    for source in sources:
        source_id = source.get("id")
        if source_id == "ljspeech" and ljspeech_root:
            path = _pick_ljspeech(ljspeech_root)
            if path:
                source["reference_wav"] = str(path)
        if source_id == "vctk" and vctk_root:
            path = _pick_vctk(vctk_root)
            if path:
                source["reference_wav"] = str(path)
        if source_id == "libritts" and libritts_root:
            path = _pick_libritts(libritts_root)
            if path:
                source["reference_wav"] = str(path)
    payload["sources"] = sources
    _save_sources(sources_file, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate local voice references.")
    parser.add_argument(
        "--ljspeech", type=str, default="", help="Path to LJSpeech root."
    )
    parser.add_argument("--vctk", type=str, default="", help="Path to VCTK root.")
    parser.add_argument(
        "--libritts", type=str, default="", help="Path to LibriTTS root."
    )
    parser.add_argument("--sources-file", type=str, default=str(DEFAULT_SOURCES_FILE))
    args = parser.parse_args()

    sources_file = Path(args.sources_file)
    ljspeech_root = Path(args.ljspeech) if args.ljspeech else None
    vctk_root = Path(args.vctk) if args.vctk else None
    libritts_root = Path(args.libritts) if args.libritts else None

    update_sources(sources_file, ljspeech_root, vctk_root, libritts_root)
    print(f"Updated {sources_file}")


if __name__ == "__main__":
    main()
