"""Chargement et validation des fichiers YAML de configuration, chemins de données."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# Racine du dépôt (src/pme_radar/config.py -> parents[2]) : permet de lancer la CLI hors du dépôt.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NAF_RE = re.compile(r"^\d{2}\.\d{2}[A-Z]$")
HEADCOUNT_BANDS = {
    "00",
    "01",
    "02",
    "03",
    "11",
    "12",
    "21",
    "22",
    "31",
    "32",
    "41",
    "42",
    "51",
    "52",
    "53",
}
TIERS = {"core", "adjacent"}


class ConfigError(ValueError):
    """Configuration invalide : le message liste tous les problèmes détectés."""


def resolve(path: str | Path) -> Path:
    """Chemin tel quel s'il existe, sinon relatif à la racine du dépôt."""
    p = Path(path)
    if p.exists() or p.is_absolute():
        return p
    alt = PROJECT_ROOT / p
    return alt if alt.exists() else p


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {path}")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} : le fichier doit contenir un dictionnaire YAML")
    return data


def _check_bands(name: str, bands: Any, errors: list[str]) -> None:
    if not isinstance(bands, list) or not bands:
        errors.append(f"{name} : liste de paliers attendue")
        return
    for b in bands:
        if not isinstance(b, dict) or "min" not in b or "points" not in b:
            errors.append(f"{name} : chaque palier doit avoir `min` et `points` ({b})")


def validate_scoring(cfg: dict[str, Any]) -> dict[str, Any]:
    """Vérifie structure et total de 100 points ; lève ConfigError avec tous les problèmes."""
    errors: list[str] = []
    crit = cfg.get("criteria")
    if not isinstance(crit, dict):
        raise ConfigError("scoring.yaml : section `criteria` manquante")
    for key in ("director_age", "revenue", "revenue_cagr", "company_age"):
        if key not in crit:
            errors.append(f"criteria.{key} manquant")
        else:
            _check_bands(f"criteria.{key}.bands", crit[key].get("bands"), errors)
    prof = crit.get("profitability", {})
    for key in ("ebe_margin_bands", "net_margin_bands"):
        _check_bands(f"criteria.profitability.{key}", prof.get(key), errors)
    for key in ("owner_operator", "no_obvious_successor", "headcount", "thesis_fit"):
        if key not in crit:
            errors.append(f"criteria.{key} manquant")
    for key, spec in crit.items():
        if not isinstance(spec, dict) or "max_points" not in spec:
            errors.append(f"criteria.{key} : `max_points` manquant")
    total = sum(s.get("max_points", 0) for s in crit.values() if isinstance(s, dict))
    if total != 100:
        errors.append(f"la somme des max_points vaut {total}, 100 attendu")
    for key in ("qualified_threshold", "top_n_drafts"):
        if not isinstance(cfg.get(key), int | float):
            errors.append(f"`{key}` doit être un nombre")
    if not 0 <= cfg.get("qualified_threshold", 0) <= 100:
        errors.append("`qualified_threshold` doit être entre 0 et 100")
    for key in ("corporate_director", "missing_financials"):
        if cfg.get("penalties", {}).get(key, 0) > 0:
            errors.append(f"penalties.{key} doit être négatif ou nul")
    if errors:
        raise ConfigError("scoring.yaml invalide :\n- " + "\n- ".join(errors))
    return cfg


def validate_thesis(t: dict[str, Any]) -> dict[str, Any]:
    """Vérifie NAF, tranches d'effectif, départements et valorisation."""
    errors: list[str] = []
    nafs = t.get("naf_codes")
    if not isinstance(nafs, list) or not nafs:
        errors.append("`naf_codes` doit être une liste non vide")
        nafs = []
    seen: set[str] = set()
    for n in nafs:
        code = str(n.get("code", "")) if isinstance(n, dict) else ""
        if not NAF_RE.match(code):
            errors.append(f"code NAF invalide : {n!r} (format attendu 43.21A)")
        elif code in seen:
            errors.append(f"code NAF en double : {code}")
        seen.add(code)
        if isinstance(n, dict) and n.get("tier") not in TIERS:
            errors.append(f"{code} : tier doit valoir core ou adjacent")
    bad = [b for b in t.get("headcount_bands", []) if str(b) not in HEADCOUNT_BANDS]
    if not t.get("headcount_bands") or bad:
        errors.append(f"`headcount_bands` invalides : {bad or 'liste vide'}")
    if not t.get("departments"):
        errors.append("`departments` doit être une liste non vide")
    val = t.get("valuation")
    if val is not None and not 0 < val.get("ebe_multiple_low", 0) <= val.get(
        "ebe_multiple_high", 0
    ):
        errors.append("valuation : 0 < ebe_multiple_low <= ebe_multiple_high attendu")
    if errors:
        raise ConfigError("thesis.yaml invalide :\n- " + "\n- ".join(errors))
    return t


def load_scoring(path: str | Path) -> dict[str, Any]:
    return validate_scoring(load_yaml(path))


def load_thesis(path: str | Path) -> dict[str, Any]:
    return validate_thesis(load_yaml(path))


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
