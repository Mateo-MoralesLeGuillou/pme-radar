"""Voix off de la vidéo avec ElevenLabs (optionnelle).

Synthétise chaque segment de narration.py avec l'API text-to-speech d'ElevenLabs, le cale sur la
timeline (léger accéléré, x1,15 au plus, si un segment déborde) et écrit la piste voix (WAV) et
les sous-titres (SRT). Chaque segment est mis en cache : relancer la vidéo ne repaie rien.

Usage : ELEVENLABS_API_KEY=... python scripts/promo/motion/voiceover.py <voix.wav> <sous-titres.srt> [cache]
Variables : ELEVENLABS_VOICE_ID (voix ; prendre de préférence une voix française de la bibliothèque),
            ELEVENLABS_MODEL (défaut eleven_multilingual_v2).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import wave
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration import DURATION, SEGMENTS, Segment, slots, srt  # noqa: E402

SR = 48_000
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # voix « George » des voix prédéfinies ; à remplacer par une voix française
DEFAULT_MODEL = "eleven_multilingual_v2"
VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.15,
    "use_speaker_boost": True,
}
MAX_TEMPO = 1.15


def synthesize(text: str, *, key: str, voice_id: str, model: str, client: httpx.Client) -> bytes:
    """Un appel text-to-speech ; renvoie l'audio MP3. Réessaie deux fois sur 429 / 5xx."""
    for attempt in range(3):
        resp = client.post(
            API.format(voice_id=voice_id),
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": model, "voice_settings": VOICE_SETTINGS},
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < 2:
                continue
        if resp.status_code >= 400:
            raise RuntimeError(f"ElevenLabs a répondu {resp.status_code} : {resp.text[:300]}")
        return resp.content
    raise RuntimeError("ElevenLabs indisponible après trois essais")  # pragma: no cover


def cache_key(text: str, voice_id: str, model: str) -> str:
    payload = json.dumps(
        [text, voice_id, model, VOICE_SETTINGS], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def fetch(
    seg: Segment, cache: Path, synth: Callable[[str], bytes], voice_id: str, model: str
) -> Path:
    """MP3 du segment, depuis le cache si possible."""
    path = cache / f"{cache_key(seg.spoken, voice_id, model)}.mp3"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(synth(seg.spoken))
    return path


def decode(path: Path, tempo: float = 1.0) -> np.ndarray:
    """MP3 -> échantillons mono 48 kHz (float32), avec accéléré éventuel (ffmpeg atempo)."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)]
    if abs(tempo - 1) > 1e-3:
        cmd += ["-filter:a", f"atempo={tempo:.4f}"]
    cmd += ["-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def build(
    out_wav: Path,
    out_srt: Path,
    fetch_seg: Callable[[Segment], Path],
    decode_fn: Callable[[Path, float], np.ndarray] = decode,
    segments: list[Segment] = SEGMENTS,
    duration: float = DURATION,
) -> list[dict[str, float | str]]:
    """Assemble la piste voix et les sous-titres ; renvoie le bilan de calage par segment."""
    track = np.zeros(int(duration * SR), dtype=np.float32)
    entries, report = [], []
    for seg, slot in zip(segments, slots(segments, duration), strict=True):
        mp3 = fetch_seg(seg)
        audio = decode_fn(mp3, 1.0)
        length = len(audio) / SR
        tempo = 1.0
        if length > slot:
            tempo = min(MAX_TEMPO, length / slot)
            audio = decode_fn(mp3, tempo)
            length = len(audio) / SR
        i0 = int(seg.start * SR)
        n = min(len(audio), len(track) - i0)
        track[i0 : i0 + n] += audio[:n]
        entries.append((seg.start, seg.start + length, seg.text))
        report.append({"start": seg.start, "length": round(length, 2), "slot": slot,
                       "tempo": round(tempo, 3), "overflow": round(max(0.0, length - slot), 2)})  # fmt: skip
    peak = float(np.abs(track).max()) or 1.0
    pcm = (np.clip(track / peak * 10 ** (-3 / 20), -1, 1) * 32767).astype("<i2")  # crête à -3 dBFS
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    out_srt.write_text(srt(entries), encoding="utf-8")
    return report


def main(argv: list[str]) -> None:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit(
            "ELEVENLABS_API_KEY absente : la voix off est ignorée (voir .env.example)."
        )
    out_wav, out_srt = Path(argv[1]), Path(argv[2])
    cache = Path(argv[3]) if len(argv) > 3 else Path("data/cache/voice")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)
    model = os.getenv("ELEVENLABS_MODEL", DEFAULT_MODEL)
    with httpx.Client(timeout=120) as client:

        def synth(text: str) -> bytes:
            return synthesize(text, key=key, voice_id=voice_id, model=model, client=client)

        report = build(out_wav, out_srt, lambda s: fetch(s, cache, synth, voice_id, model))
    for r in report:
        flag = f" ⚠ déborde de {r['overflow']} s" if r["overflow"] else ""
        print(
            f"  {r['start']:>5} s : {r['length']} s / {r['slot']} s (x{r['tempo']}){flag}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main(sys.argv)
