"""Bande-son de la vidéo, synthétisée avec numpy (aucun fichier audio tiers, aucun droit à gérer).

Calée sur les repères produits par motion.js (cues.json) :
- nappe d'accords (la mineur 9, fa majeur 7, do add9, sol 6) à 100 BPM ;
- pulsation douce (grosse caisse, charleston), basse et arpège pendant le corps de la vidéo ;
- effets synchronisés : échos radar, transitions, compteurs, cloche du score, tampon, clics, frappe.

Usage : python scripts/promo/motion/soundtrack.py <cues.json> <sortie.wav>
"""

from __future__ import annotations

import json
import sys
import wave

import numpy as np

SR = 48_000
BEAT = 0.6  # 100 BPM
BAR = 4 * BEAT
RNG = np.random.default_rng(2026)

NOTE = {
    "F1": 43.65, "G1": 49.00, "A1": 55.00, "C2": 65.41,
    "F2": 87.31, "G2": 98.00, "A2": 110.00, "C3": 130.81, "D3": 146.83, "E3": 164.81,
    "G3": 196.00, "A3": 220.00, "B3": 246.94, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25, "D5": 587.33,
    "E5": 659.25,
}  # fmt: skip
CHORDS = [  # (basse, nappe, arpège)
    ("A1", ["A2", "E3", "G3", "B3", "C4"], ["A4", "C5", "E5", "B4"]),
    ("F1", ["F2", "C3", "E3", "A3"], ["F4", "A4", "C5", "E5"]),
    ("C2", ["C3", "G3", "D4", "E4"], ["G4", "C5", "D5", "E5"]),
    ("G1", ["G2", "D3", "E3", "B3"], ["G4", "B4", "D5", "E5"]),
]
SEG = 2 * BAR  # un accord toutes les deux mesures


def chord_at(t: float, outro_from: float) -> int:
    return 2 if t >= outro_from else int(t // SEG) % len(CHORDS)


def tvec(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def add(buf: np.ndarray, sig: np.ndarray, t0: float, gain: float = 1.0, pan: float = 0.0) -> None:
    """Ajoute un signal mono dans le tampon stéréo à t0 (pan -1 gauche … +1 droite)."""
    i0 = int(t0 * SR)
    if i0 >= buf.shape[1] or i0 + len(sig) <= 0:
        return
    s0 = max(0, -i0)
    i0 = max(0, i0)
    n = min(len(sig) - s0, buf.shape[1] - i0)
    left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i0 : i0 + n] += sig[s0 : s0 + n] * gain * left * np.sqrt(2)
    buf[1, i0 : i0 + n] += sig[s0 : s0 + n] * gain * right * np.sqrt(2)


def lowpass(x: np.ndarray, cutoff: np.ndarray | float) -> np.ndarray:
    """Passe-bas à un pôle (fréquence de coupure fixe ou variable dans le temps)."""
    a = 1 - np.exp(-2 * np.pi * np.broadcast_to(cutoff, x.shape) / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


# ---------------------------------------------------------------- instruments
def pad_note(freq: float, dur: float, t_abs0: float) -> np.ndarray:
    t = tvec(dur)
    bright = 0.55 + 0.45 * np.sin(2 * np.pi * 0.05 * (t + t_abs0))  # « filtre » qui respire
    sig = np.zeros_like(t)
    for h in range(1, 9):
        amp = 1 / h**1.35 * (1 if h < 3 else bright)
        for det in (-0.0025, 0.0025):
            sig += amp * np.sin(2 * np.pi * freq * h * (1 + det) * t + RNG.uniform(0, 2 * np.pi))
    attack, release = 1.3, 1.8
    env = np.minimum(1, t / attack) * np.minimum(1, np.maximum(0, (dur - t) / release))
    return sig * env


def kick() -> np.ndarray:
    t = tvec(0.42)
    freq = 46 + 95 * np.exp(-t * 28)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 7.5)
    click = RNG.normal(0, 1, len(t)) * np.exp(-t * 400) * 0.25
    return body + click


def hat(accent: float) -> np.ndarray:
    t = tvec(0.07)
    n = RNG.normal(0, 1, len(t))
    n = np.diff(np.diff(n, prepend=0), prepend=0)  # passe-haut grossier
    return n * np.exp(-t * 70) * 0.35 * accent


def pluck(freq: float) -> np.ndarray:
    t = tvec(0.9)
    sig = (
        np.sin(2 * np.pi * freq * t)
        + 0.35 * np.sin(4 * np.pi * freq * t) * np.exp(-t * 9)
        + 0.18 * np.sin(6 * np.pi * freq * t) * np.exp(-t * 14)
        + 0.08 * np.sin(10 * np.pi * freq * t) * np.exp(-t * 22)
    )
    return sig * np.exp(-t * 6.5) * np.minimum(1, t / 0.004)


def bass_note(freq: float, dur: float) -> np.ndarray:
    t = tvec(dur)
    sig = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return sig * np.minimum(1, t / 0.08) * np.minimum(1, np.maximum(0, (dur - t) / 0.3))


# ---------------------------------------------------------------- effets
def blip() -> np.ndarray:
    t = tvec(0.5)
    f = 1250 + 120 * np.exp(-t * 40)
    ping = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 16)
    echo = np.zeros_like(ping)
    d = int(0.19 * SR)
    echo[d:] = ping[:-d] * 0.32
    return ping + echo


def whoosh() -> np.ndarray:
    t = tvec(1.2)
    noise = RNG.normal(0, 1, len(t))
    sweep = 300 + 3200 * np.sin(np.pi * np.clip(t / 1.1, 0, 1)) ** 2
    env = np.sin(np.pi * np.clip(t / 1.15, 0, 1)) ** 2.2
    return lowpass(noise, sweep) * env * 2.2


def tick() -> np.ndarray:
    t = tvec(0.08)
    return (np.sin(2 * np.pi * 2100 * t) + 0.5 * np.sin(2 * np.pi * 3150 * t)) * np.exp(-t * 60)


def ding() -> np.ndarray:
    t = tvec(2.6)
    sig = np.zeros_like(t)
    for ratio, decay, amp in ((1, 1.6, 1), (2.0, 1.1, 0.45), (2.76, 0.8, 0.3), (5.4, 0.35, 0.12)):
        sig += amp * np.sin(2 * np.pi * 1046.5 * ratio * t) * np.exp(-t / decay)
    return sig * np.minimum(1, t / 0.003)


def stamp() -> np.ndarray:
    t = tvec(0.45)
    thump = np.sin(2 * np.pi * np.cumsum(55 + 60 * np.exp(-t * 30)) / SR) * np.exp(-t * 11)
    burst = lowpass(RNG.normal(0, 1, len(t)), 2500.0) * np.exp(-t * 90) * 1.5
    return thump + burst


def click() -> np.ndarray:
    t = tvec(0.05)
    n = np.diff(RNG.normal(0, 1, len(t)), prepend=0)
    return n * np.exp(-t * 300) * 0.6


def key_tap() -> np.ndarray:
    t = tvec(0.035)
    n = np.diff(RNG.normal(0, 1, len(t)), prepend=0)
    return lowpass(n, 6000.0) * np.exp(-t * 220)


# ---------------------------------------------------------------- composition
def render(meta: dict) -> np.ndarray:
    dur = float(meta["duration"])
    sec = meta["sections"]
    groove, hats_s, arp_s, outro = sec["groove"], sec["hats"], sec["arp"], sec["outro"][0]
    n = int(dur * SR) + SR
    music = np.zeros((2, n))
    fxb = np.zeros((2, n))

    # nappe : un segment par accord (fondus enchaînés), dernier accord tenu jusqu'à la fin
    t0 = 0.0
    while t0 < dur:
        idx = chord_at(t0, outro)
        t1 = dur + 1.5 if t0 >= outro else min(t0 + SEG, outro) if t0 < outro else dur
        seg = (t1 - t0) + 1.8
        for k, name in enumerate(CHORDS[idx][1]):
            add(music, pad_note(NOTE[name] * 2, seg, t0), t0, 0.042, pan=(-0.5 + k / 4) * 0.8)
        t0 = t1 if t0 < outro and t1 > t0 else dur

    # rythme : demi-temps au début du groove, puis chaque temps
    beats = np.arange(np.ceil(groove[0] / BEAT) * BEAT, groove[1], BEAT)
    kick_times = [b for b in beats if b >= hats_s[0] or round(b / BEAT) % 2 == 0]
    for b in kick_times:
        add(music, kick(), b, 0.45)
    for b in np.arange(np.ceil(hats_s[0] / BEAT) * BEAT, hats_s[1], BEAT):
        add(music, hat(1.0), b + BEAT / 2, 0.42, pan=0.25)
        add(music, hat(0.5), b + BEAT / 4 * 3, 0.26, pan=-0.2)

    # basse : fondamentale de l'accord, une mesure à la fois
    for bar0 in np.arange(np.ceil(groove[0] / BAR) * BAR, groove[1], BAR):
        add(music, bass_note(NOTE[CHORDS[chord_at(bar0, outro)][0]] * 2, BAR), bar0, 0.12)

    # arpège en croches, avec écho stéréo
    pattern = [0, 1, 2, 3, 2, 1, 2, 3]
    for k, tt in enumerate(
        np.arange(np.ceil(arp_s[0] / (BEAT / 2)) * BEAT / 2, arp_s[1], BEAT / 2)
    ):
        notes = CHORDS[chord_at(tt, outro)][2]
        f = NOTE[notes[pattern[k % len(pattern)]]]
        add(music, pluck(f), tt, 0.07, pan=0.35 if k % 2 else -0.35)
        add(music, pluck(f), tt + 0.45, 0.025, pan=-0.6 if k % 2 else 0.6)

    # respiration et final : notes de cloche espacées
    for i, tt in enumerate(np.arange(sec["breath"][0], dur - 2, BEAT * 2)):
        notes = CHORDS[chord_at(tt, outro)][2]
        add(music, pluck(NOTE[notes[i % 4]] / 2), tt, 0.05, pan=0.3 * np.sin(i))

    # « air » : souffle filtré très discret qui donne de la brillance
    air = np.diff(np.diff(RNG.normal(0, 1, n), prepend=0), prepend=0)
    air *= 0.012 * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * np.arange(n) / SR))
    music[0] += air
    music[1] += np.roll(air, 37)

    # « pompage » discret de la nappe sur la grosse caisse
    duck = np.ones(n)
    for b in kick_times:
        i0 = int(b * SR)
        k = np.arange(min(int(0.35 * SR), n - i0))
        duck[i0 : i0 + len(k)] *= 1 - 0.28 * np.exp(-k / SR * 9)
    music *= duck

    # effets synchronisés
    fx = {"blip": (blip, 0.2), "whoosh": (whoosh, 0.11), "tick": (tick, 0.12), "ding": (ding, 0.2),
          "stamp": (stamp, 0.42), "click": (click, 0.3)}  # fmt: skip
    typing = []
    for c in meta["cues"]:
        if c["type"] in fx:
            gen, gain = fx[c["type"]]
            add(
                fxb,
                gen(),
                c["t"] - (0.25 if c["type"] == "whoosh" else 0),
                gain,
                pan=RNG.uniform(-0.3, 0.3),
            )
        elif c["type"] in ("type_start", "type_end"):
            typing.append(c["t"])
    if len(typing) == 2:
        tt = typing[0]
        while tt < typing[1]:
            add(fxb, key_tap(), tt, RNG.uniform(0.05, 0.1), pan=RNG.uniform(-0.2, 0.2))
            tt += RNG.uniform(0.045, 0.11)

    mix = music + fxb
    mix = mix[:, : int(dur * SR)]
    t = np.arange(mix.shape[1]) / SR
    mix *= np.minimum(1, t / 0.6) * np.minimum(1, np.maximum(0, (dur - t) / 2.5))
    # niveau calé sur le 99,9e centile (pas sur une crête isolée), puis saturation douce
    mix = mix * (0.72 / max(1e-9, np.percentile(np.abs(mix), 99.9)))
    mix = np.tanh(mix * 1.25) / np.tanh(1.25)
    return mix / max(1e-9, np.abs(mix).max()) * 10 ** (-1 / 20)  # crête à -1 dBFS


def main(cues_path: str, out_path: str) -> None:
    meta = json.load(open(cues_path, encoding="utf-8"))
    mix = render(meta)
    rms = 20 * np.log10(np.sqrt((mix**2).mean()))
    pcm = (np.clip(mix.T, -1, 1) * 32767).astype("<i2")
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(
        f"{out_path} : {mix.shape[1] / SR:.1f} s, crête -1 dBFS, RMS {rms:.1f} dBFS",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
