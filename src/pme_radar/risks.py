"""Signaux factuels : règles déterministes appliquées aux données d'une cible.

Chaque signal porte le thème de due diligence concerné et la question à poser. À la différence des
« signaux d'alerte » rédigés par l'IA (des hypothèses), ils découlent directement des données et
sont reproductibles d'un run à l'autre (ADR-020).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .fmt import eur, pct
from .models import Company

DEFAULTS: dict[str, float] = {
    "high_debt_ratio": 150,
    "low_ebe_margin": 0.05,
    "low_net_margin": 0.03,
    "declining_cagr": -0.03,
    "stale_accounts_years": 3,
    "min_confidence": 0.7,
}
LEVELS = ("élevé", "moyen", "info")
HEADCOUNT_MID = {"11": 15, "12": 35, "21": 75, "22": 150, "31": 225}  # milieu de tranche INSEE


@dataclass(frozen=True)
class Signal:
    level: str  # élevé | moyen | info
    theme: str  # Transmission | Commercial | Financier | RH & organisation | Juridique | Opérations
    title: str
    detail: str
    question: str


def thresholds(scoring_cfg: dict[str, Any] | None) -> dict[str, float]:
    return {**DEFAULTS, **((scoring_cfg or {}).get("risk_thresholds") or {})}


def assess(
    c: Company, scoring_cfg: dict[str, Any] | None = None, as_of: date | None = None
) -> list[Signal]:
    """Signaux factuels de la cible, du plus grave au plus informatif."""
    th = thresholds(scoring_cfg)
    as_of = as_of or date.today()
    out: list[Signal] = []

    def add(level: str, theme: str, title: str, detail: str, question: str) -> None:
        out.append(Signal(level, theme, title, detail, question))

    if c.has_collective_procedure:
        add("élevé", "Juridique", "Procédure collective au BODACC",
            "Annonce de la famille « procédure collective » publiée pour ce SIREN.",
            "Nature, date et issue de la procédure ? Un plan de continuation est-il en cours ?")  # fmt: skip
    if c.debt_ratio is not None and c.debt_ratio > th["high_debt_ratio"]:
        add("élevé", "Financier", "Endettement élevé",
            f"Dettes à {c.debt_ratio:.0f} % des capitaux propres (ratios BCE/INPI).",
            "Échéancier de la dette, covenants, garanties et nantissements en place ?")  # fmt: skip
    if c.has_corporate_director:
        add("moyen", "Juridique", "Société dirigée par une autre société",
            "Le dirigeant principal est une personne morale qui n'est pas une holding personnelle.",
            "Qui détient le capital ? Quelles conventions avec le groupe (frais de gestion, "
            "trésorerie, garanties) ?")  # fmt: skip
    if c.n_natural_directors == 1:
        add("moyen", "Transmission", "Dépendance au dirigeant",
            "Un seul dirigeant personne physique identifié.",
            "Quelle part du chiffre d'affaires repose sur la relation personnelle du dirigeant ? "
            "Qui encadre les équipes au quotidien ?")  # fmt: skip
    if not c.accounts_available:
        add("moyen", "Financier", "Comptes non publiés", "Chiffre d'affaires absent ou confidentiel.",
            "Obtenir les trois dernières liasses fiscales et une situation intermédiaire.")  # fmt: skip
    if c.ebe_margin is not None and c.ebe_margin < th["low_ebe_margin"]:
        add("moyen", "Financier", "Rentabilité faible", f"Marge d'EBE de {pct(c.ebe_margin)}.",
            "La structure de coûts, la politique de prix ou des éléments non récurrents "
            "expliquent-ils cette marge ?")  # fmt: skip
    elif c.ebe_margin is None and c.net_margin is not None and c.net_margin < th["low_net_margin"]:
        add("moyen", "Financier", "Rentabilité faible",
            f"Marge nette de {pct(c.net_margin)} (EBE non disponible).",
            "Quel est l'EBE retraité (rémunération du dirigeant, loyers, éléments exceptionnels) ?")  # fmt: skip
    if c.net_income_last is not None and c.net_income_last < 0:
        add("moyen", "Financier", "Dernier exercice déficitaire",
            f"Résultat net de {eur(c.net_income_last)}.",
            "Origine de la perte : ponctuelle ou structurelle ?")  # fmt: skip
    if c.revenue_cagr is not None and c.revenue_cagr < th["declining_cagr"]:
        add("moyen", "Commercial", "Chiffre d'affaires en baisse",
            f"{pct(c.revenue_cagr, signed=True)} par an en moyenne.",
            "Causes de la baisse : perte de clients, fin d'un contrat, cycle du secteur ?")  # fmt: skip
    if c.holding_owner is not None:
        add("info", "Transmission", "Détention via une holding personnelle",
            f"Le dirigeant agit via {c.holding_name}.",
            "La cession porterait-elle sur les titres de la société ou de la holding ? "
            "Quels autres actifs la holding détient-elle ?")  # fmt: skip
    if c.director_age is not None and c.director_age >= 70:
        add("info", "Transmission", "Transmission potentiellement urgente",
            f"Dirigeant de {c.director_age} ans.",
            "Quel horizon de départ ? Le cédant accepterait-il d'accompagner la transition ?")  # fmt: skip
    if c.director_age is None:
        add("info", "Transmission", "Âge du dirigeant inconnu", "Date de naissance non publiée.",
            "Quel calendrier de transmission le dirigeant envisage-t-il ?")  # fmt: skip
    if c.ebe_year is not None and as_of.year - c.ebe_year >= th["stale_accounts_years"]:
        add("info", "Financier", "Comptes anciens", f"Dernier EBE publié : exercice {c.ebe_year}.",
            "Comptes du dernier exercice clos et situation de l'année en cours ?")  # fmt: skip
    if c.ebe is None:
        add("info", "Financier", "EBE non disponible", "Aucun ratio BCE/INPI exploitable.",
            "Quel EBE normalisé après retraitement de la rémunération du dirigeant ?")  # fmt: skip
    mid = HEADCOUNT_MID.get(c.headcount_band or "")
    if mid and c.revenue_last:
        per = c.revenue_last / mid
        if per > 400_000:
            add("info", "Opérations", "Chiffre d'affaires par salarié élevé",
                f"≈ {per / 1e3:.0f} k€ par salarié (tranche {c.headcount_band}).",
                "Quelle part de négoce, de sous-traitance ou de refacturation dans le CA ?")  # fmt: skip
        elif per < 50_000:
            add("info", "Opérations", "Chiffre d'affaires par salarié faible",
                f"≈ {per / 1e3:.0f} k€ par salarié (tranche {c.headcount_band}).",
                "Sous-activité, temps partiels, ou effectif surestimé par la tranche INSEE ?")  # fmt: skip
    if c.company_age_years is not None and c.company_age_years < 10:
        add("info", "Commercial", "Entreprise jeune", f"{c.company_age_years} ans d'existence.",
            "Le modèle a-t-il traversé un cycle complet ? Quelle récurrence du chiffre d'affaires ?")  # fmt: skip
    rank = {lv: i for i, lv in enumerate(LEVELS)}
    return sorted(out, key=lambda s: rank[s.level])
