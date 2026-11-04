"""Faits affichés dans la vidéo : rien n'est inventé.

- Chiffres agrégés du run réel du 2026-11-04 (Hauts-de-Seine), repris du README (data/ n'est pas
  versionné, ces agrégats sont la source).
- Cible, dossier de pré-DD et brouillon : meilleure cible d'un run hors ligne (données SYNTHÉTIQUES).
- Nombre de tests : collecté par pytest au moment du rendu.
- Positions du curseur de score : détectées sur les captures du dashboard (pixels cyan).

Usage : python scripts/promo/motion/facts.py <dossier_captures> <dossier_data> > facts.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
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


def main(captures: Path, data_dir: Path) -> None:
    from pme_radar.config import load_scoring, load_thesis, load_yaml
    from pme_radar.deal import DD_BANK, DD_THEMES, dd_questions
    from pme_radar.models import Stage
    from pme_radar.outreach import with_footer
    from pme_radar.report import evaluate
    from pme_radar.store import read_companies

    scoring_cfg = load_scoring(ROOT / "config/scoring.yaml")
    thesis = load_thesis(ROOT / "config/thesis.yaml")
    footer = load_yaml(ROOT / "config/campaign.yaml").get("compliance_footer")
    companies = read_companies(data_dir / "processed" / "analyzed.jsonl")
    qualified = [c for c in companies if c.stage == Stage.QUALIFIED and c.score and c.analysis]
    top = max(qualified, key=lambda c: c.score.total if c.score else 0)
    dossier = next(
        d for d in evaluate(companies, scoring_cfg, thesis) if d.company.siren == top.siren
    )
    plan, s, a = dossier.plan, top.score, top.analysis
    assert plan is not None and s is not None and a is not None, (
        "la cible de la vidéo doit avoir un EBE"
    )
    triggered = [x.question.split("?")[0].rstrip() + " ?" for x in dossier.signals]
    generic = [DD_BANK["Commercial"][0], DD_BANK["Financier"][0], DD_BANK["Transmission"][0]]
    examples = (triggered + generic)[:3]
    questions = dd_questions(dossier.signals)
    person = top.main_person()
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout  # fmt: skip
    fin = thesis.get("financing") or {}
    val = thesis.get("valuation") or {}
    facts = {
        "run": RUN_92,
        "target": {
            "name": top.name,
            "city": top.city,
            "department": top.department,
            "naf_label": top.naf_label,
            "score": s.total,
            "confidence": s.confidence,
            "detail": [
                {"critère": r.label, "points": r.points, "max": r.max_points, "détail": r.detail}
                for r in s.criteria + s.penalties
            ],
            "mini_thesis": a.mini_thesis,
            "red_flags": a.red_flags,
        },
        "draft": {
            "to": person.name if person else "Madame, Monsieur",
            "subject": a.email_subject,
            "body": with_footer(a.email_body, footer),
        },
        "dd": {
            "recommendation": dossier.rec.label,
            "ev_low": plan.ev_low,
            "ev_high": plan.ev_high,
            "ebe": plan.ebe,
            "ebe_year": plan.ebe_year,
            "multiple_low": val.get("ebe_multiple_low", 4),
            "multiple_high": val.get("ebe_multiple_high", 6),
            "senior_debt": plan.senior_debt,
            "vendor_loan": plan.vendor_loan,
            "equity": plan.equity,
            "equity_share": plan.equity_share,
            "coverage": plan.coverage,
            "min_coverage": fin.get("min_coverage", 1.3),
            "signals": [{"level": x.level, "title": x.title} for x in dossier.signals],
            "questions_total": sum(len(v) for v in questions.values()),
            "themes": len(DD_THEMES),
            "questions": examples,
            "triggered": [i < len(triggered) for i in range(len(examples))],
            "pages": ["report_p1.png", "report_p2.png", "report_p3.png"],
        },
        "tests": sum(1 for line in collected.splitlines() if "::" in line),
        "threshold": scoring_cfg["qualified_threshold"],
        "repo": "github.com/Mateo-MoralesLeGuillou/pme-radar",
        "layout": {
            "slider_from": slider_handle(captures / "overview_top.png"),
            "slider_to": slider_handle(captures / "overview_filtered.png"),
        },
    }
    print(json.dumps(facts, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
