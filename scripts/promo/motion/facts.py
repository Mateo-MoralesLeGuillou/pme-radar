"""Faits affichés dans la vidéo : rien n'est inventé.

- Chiffres agrégés du run réel du 2026-11-04 (Hauts-de-Seine), repris du README (data/ n'est pas
  versionné, ces agrégats sont la source).
- Cible et brouillon : première cible de l'échantillon SYNTHÉTIQUE (examples/).
- Nombre de tests : collecté par pytest au moment du rendu.
- Positions du curseur de score : détectées sur les captures du dashboard (pixels cyan).

Usage : python scripts/promo/motion/facts.py <dossier_captures> > facts.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
RUN_92 = {"sourced": 343, "excluded": 29, "scored": 314, "qualified": 35, "date": "4 novembre 2026"}


def slider_handle(path: Path) -> list[float]:
    """Centre de la poignée du curseur « Score minimum » (coordonnées CSS d'une page de 1440 px)."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(int)
    scale = im.shape[1] / 1440
    y0, y1, x1 = int(300 * scale), int(800 * scale), int(300 * scale)
    zone = im[y0:y1, :x1]
    cyan = (
        (abs(zone[..., 0] - 37) < 45)
        & (abs(zone[..., 1] - 194) < 45)
        & (abs(zone[..., 2] - 245) < 45)
    )
    cols = cyan.sum(axis=0)
    tall = np.where(cols >= 22 * scale / 2)[0]  # colonnes traversant le disque (pas le texte)
    if len(tall) == 0:
        raise SystemExit(f"Poignée du curseur introuvable dans {path}")
    groups = np.split(tall, np.where(np.diff(tall) > 2)[0] + 1)
    best = max(groups, key=lambda g: cols[g].sum())
    ys = np.where(cyan[:, best].any(axis=1))[0]
    return [round(float(best.mean()) / scale, 1), round((y0 + float(np.median(ys))) / scale, 1)]


def main(captures: Path) -> None:
    targets = pd.read_csv(
        ROOT / "examples/sample_targets.csv", dtype={"siren": str, "department": str}
    )
    top = targets.sort_values("score", ascending=False).iloc[0]
    drafts = pd.read_csv(ROOT / "examples/sample_drafts.csv", dtype={"siren": str})
    draft = drafts.set_index("siren").loc[top["siren"]]
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout  # fmt: skip
    facts = {
        "run": RUN_92,
        "target": {
            "name": str(top["name"]),
            "city": str(top["city"]),
            "department": str(top["department"]),
            "naf_label": str(top["naf_label"]),
            "score": float(top["score"]),
            "detail": json.loads(top["score_detail"]),
            "mini_thesis": top["mini_thesis"].split(" | "),
            "red_flags": top["red_flags"].split(" | "),
        },
        "draft": {
            "to": str(draft["director"]),
            "subject": str(draft["subject"]),
            "body": str(draft["body"]),
        },
        "tests": sum(1 for line in collected.splitlines() if "::" in line),
        "threshold": 70,
        "repo": "github.com/Mateo-MoralesLeGuillou/pme-radar",
        "layout": {
            "slider_from": slider_handle(captures / "overview_top.png"),
            "slider_to": slider_handle(captures / "overview_filtered.png"),
        },
    }
    print(json.dumps(facts, ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
