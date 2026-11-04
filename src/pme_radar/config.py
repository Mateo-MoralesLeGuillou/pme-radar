"""Chargement des fichiers YAML de configuration et des chemins de données."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class DataPaths:
    """Chemins des artefacts de run (dossier `data/`, gitignoré)."""

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.cache = self.root / "cache"
        self.raw = self.root / "raw" / "companies.parquet"
        self.enriched = self.root / "processed" / "enriched.jsonl"
        self.scored = self.root / "processed" / "scored.jsonl"
        self.analyzed = self.root / "processed" / "analyzed.jsonl"
        self.out = self.root / "out"

    def ensure(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
