"""Chaîne de la vidéo : narration, voix off ElevenLabs (API simulée), mixage, cohérence de timeline."""

import json
import re
import sys

import httpx
import numpy as np
import pytest

from .conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts" / "promo" / "motion"))
import narration  # noqa: E402
import soundtrack  # noqa: E402
import voiceover  # noqa: E402


def test_timeline_duration_matches_animation():
    js = (ROOT / "scripts/promo/motion/motion.js").read_text(encoding="utf-8")
    shift = float(re.search(r"const SHIFT = ([\d.]+);", js).group(1))
    base = float(re.search(r"const DURATION = ([\d.]+) \+ SHIFT;", js).group(1))
    assert base + shift == narration.DURATION


def test_narration_fits_its_slots():
    segs = narration.SEGMENTS
    assert [s.start for s in segs] == sorted(s.start for s in segs)
    for seg, slot in zip(segs, narration.slots(), strict=True):
        assert slot > 2
        # débit français prudent : 2,6 mots/s ; l'accéléré de x1,15 doit suffire au pire
        assert len(seg.spoken.split()) / 2.6 <= slot * voiceover.MAX_TEMPO, seg.text
    assert all("0" not in s.say for s in segs if s.say)  # nombres en toutes lettres pour la voix


def test_srt_format():
    out = narration.srt([(0.9, 6.09, "Bonjour."), (61.5, 3725.25, "Fin.")])
    assert out.startswith("1\n00:00:00,900 --> 00:00:06,090\nBonjour.\n")
    assert "2\n00:01:01,500 --> 01:02:05,250\nFin.\n" in out


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_elevenlabs_request_shape():
    seen = {}

    def handler(req):
        seen["url"], seen["headers"], seen["json"] = str(req.url), req.headers, req.read()
        return httpx.Response(200, content=b"ID3mp3")

    audio = voiceover.synthesize("Bonjour", key="sk-test", voice_id="VOIX", model="eleven_multilingual_v2",
                                 client=_client(handler))  # fmt: skip
    assert audio == b"ID3mp3"
    assert seen["url"].startswith("https://api.elevenlabs.io/v1/text-to-speech/VOIX")
    assert "output_format=mp3_44100_128" in seen["url"]
    assert seen["headers"]["xi-api-key"] == "sk-test"
    body = json.loads(seen["json"])
    assert body["text"] == "Bonjour" and body["model_id"] == "eleven_multilingual_v2"
    assert set(body["voice_settings"]) >= {"stability", "similarity_boost"}


def test_elevenlabs_retries_then_fails_cleanly():
    calls = []

    def flaky(req):
        calls.append(1)
        return httpx.Response(429 if len(calls) < 3 else 200, content=b"ok")

    assert (
        voiceover.synthesize("x", key="k", voice_id="v", model="m", client=_client(flaky)) == b"ok"
    )
    with pytest.raises(RuntimeError, match="401"):
        voiceover.synthesize("x", key="k", voice_id="v", model="m",
                             client=_client(lambda r: httpx.Response(401, text="clé invalide")))  # fmt: skip


def test_voice_segments_are_cached(tmp_path):
    calls = []

    def synth(text):
        calls.append(text)
        return b"mp3"

    seg = narration.SEGMENTS[0]
    p1 = voiceover.fetch(seg, tmp_path, synth, "v", "m")
    p2 = voiceover.fetch(seg, tmp_path, synth, "v", "m")
    assert p1 == p2 and p1.read_bytes() == b"mp3" and calls == [seg.spoken]
    voiceover.fetch(seg, tmp_path, synth, "autre-voix", "m")  # autre voix : nouvelle synthèse
    assert len(calls) == 2


def test_build_places_segments_and_speeds_up_long_ones(tmp_path):
    segs = [
        narration.Segment(1.0, "Un."),
        narration.Segment(4.0, "Deux."),
    ]  # créneaux : 2,75 s et 4,95 s
    lengths = {"Un.": 3.0, "Deux.": 2.0}  # le premier déborde de 0,25 s

    def fake_decode(path, tempo):
        text = path.read_text()
        return np.full(int(lengths[text] / tempo * voiceover.SR), 0.5, dtype=np.float32)

    def fake_fetch(seg):
        p = tmp_path / f"{seg.start}.txt"
        p.write_text(seg.text)
        return p

    report = voiceover.build(
        tmp_path / "v.wav", tmp_path / "v.srt", fake_fetch, fake_decode, segs, 10.0
    )
    assert report[0]["tempo"] == pytest.approx(3.0 / 2.75, abs=1e-3) and report[0]["overflow"] == 0
    assert report[1]["tempo"] == 1.0
    srt = (tmp_path / "v.srt").read_text()
    assert (
        "00:00:01,000 --> 00:00:03,750\nUn." in srt
        and "00:00:04,000 --> 00:00:06,000\nDeux." in srt
    )
    import wave

    with wave.open(str(tmp_path / "v.wav")) as w:
        assert w.getframerate() == voiceover.SR and w.getnframes() == 10 * voiceover.SR


def test_voiceover_requires_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ELEVENLABS_API_KEY"):
        voiceover.main(["voiceover.py", "v.wav", "v.srt"])


def test_music_ducks_under_voice():
    sr = soundtrack.SR
    music = np.vstack([np.sin(2 * np.pi * 220 * np.arange(8 * sr) / sr) * 0.5] * 2)
    voice = np.zeros(8 * sr)
    voice[3 * sr : 5 * sr] = np.random.default_rng(1).normal(0, 0.2, 2 * sr)
    out = soundtrack.duck_and_mix(music, np.zeros(8 * sr))
    quiet = soundtrack.duck_and_mix(music, voice)
    rms = lambda a: float(np.sqrt((a**2).mean()))  # noqa: E731
    before = rms(out[0, : 2 * sr])
    # sous la voix, la musique (mélange moins la voix recalée) descend d'au moins 10 dB
    v = voice[int(3.5 * sr) : int(4.5 * sr)]
    scaled = v * (10 ** (-16 / 20) / np.sqrt((voice[3 * sr : 5 * sr] ** 2).mean()))
    under = quiet[0, int(3.5 * sr) : int(4.5 * sr)] - scaled
    assert 20 * np.log10(before / rms(under)) > 10
