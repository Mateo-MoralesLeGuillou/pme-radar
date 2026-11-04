"""Modèles pydantic du domaine."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Stage(StrEnum):
    """Étapes de l'entonnoir côté moteur (le suivi de campagne ajoute contacted/meeting)."""

    IDENTIFIED = "identified"
    QUALIFIED = "qualified"
    EXCLUDED = "excluded"


class Director(BaseModel):
    """Dirigeant (personne physique ou morale)."""

    is_natural_person: bool
    name: str | None = None
    role: str | None = None
    birth_year: int | None = None
    birth_month: int | None = None  # None si seule l'année est connue
    siren: str | None = None  # SIREN de la société, si dirigeant personne morale


class FinancialYear(BaseModel):
    year: int
    revenue: float | None = None  # None = donnée absente (jamais 0 par défaut)
    net_income: float | None = None


class CriterionScore(BaseModel):
    key: str
    label: str
    points: float
    max_points: float
    detail: str
    missing: bool = False  # donnée absente : 0 point, mais le critère reste « à documenter »


class ScoreBreakdown(BaseModel):
    """Score explicable : points par critère + phrase lisible."""

    total: float  # score officiel (plancher) : seules les données disponibles rapportent des points
    criteria: list[CriterionScore] = Field(default_factory=list)
    penalties: list[CriterionScore] = Field(default_factory=list)
    excluded: bool = False
    exclusion_reason: str | None = None
    summary: str = ""
    ceiling: float = 0.0  # score atteignable si toutes les données manquantes étaient favorables
    confidence: float = 1.0  # part des points du barème évaluée sur des données réelles (0 à 1)
    to_document: bool = False  # sous le seuil, mais le plafond l'atteint : un appel peut trancher


class TargetAnalysis(BaseModel):
    """Sortie de la couche IA (ne modifie jamais le score)."""

    mini_thesis: list[str]
    red_flags: list[str]
    email_subject: str
    email_body: str
    prompt_version: str = ""
    provider: str = ""
    facts_hash: str = ""  # empreinte des faits transmis (réutilisation sans nouvel appel)


class Company(BaseModel):
    siren: str
    name: str
    naf_code: str | None = None
    naf_label: str | None = None
    headcount_band: str | None = None
    creation_date: date | None = None
    legal_form: str | None = None
    category: str | None = None
    postal_code: str | None = None
    city: str | None = None
    department: str | None = None
    directors: list[Director] = Field(default_factory=list)
    financials: list[FinancialYear] = Field(default_factory=list)

    # --- champs dérivés (enrich.py) ---
    director_age: int | None = None
    company_age_years: int | None = None
    is_owner_operator: bool | None = None
    n_natural_directors: int = 0
    has_corporate_director: bool = False  # dirigeant société qui n'est PAS une holding personnelle
    holding_name: str | None = (
        None  # holding personnelle (NAF 64.20Z) dirigée par une personne physique
    )
    holding_owner: Director | None = None  # la personne physique derrière cette holding
    revenue_last: float | None = None
    net_income_last: float | None = None
    net_margin: float | None = None
    revenue_cagr: float | None = None
    ebe: float | None = None  # EBE du dernier exercice public (ratios INPI, ADR-005)
    ebe_margin: float | None = None  # EBE / CA du même exercice
    ebe_year: int | None = None
    debt_ratio: float | None = None  # taux d'endettement INPI (% des capitaux propres)
    accounts_available: bool = False
    has_collective_procedure: bool | None = None  # None = BODACC non interrogé

    # --- scoring / entonnoir ---
    stage: Stage = Stage.IDENTIFIED
    score: ScoreBreakdown | None = None
    analysis: TargetAnalysis | None = None

    def main_person(self) -> Director | None:
        """Personne physique à contacter : dirigeant direct, sinon propriétaire via holding."""
        natural = next((d for d in self.directors if d.is_natural_person and d.name), None)
        return natural or self.holding_owner
