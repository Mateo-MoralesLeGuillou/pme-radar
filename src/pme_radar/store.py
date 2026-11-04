"""Persistance JSONL des `Company` entre les étapes du pipeline."""

from __future__ import annotations

from pathlib import Path

from .models import Company


def write_companies(companies: list[Company], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(c.model_dump_json() for c in companies) + "\n", encoding="utf-8")


def read_companies(path: Path) -> list[Company]:
    if not path.exists():
        raise FileNotFoundError(f"{path} introuvable : lancer l'étape précédente du pipeline.")
    return [
        Company.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
