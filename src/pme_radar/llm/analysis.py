"""Orchestration : analyse + brouillon d'email pour le top N des cibles qualifiées.

Un échec sur une cible n'interrompt pas le lot (ADR-015) et une analyse dont les faits n'ont pas
changé est réutilisée sans nouvel appel LLM (maîtrise des coûts sur un run hebdomadaire).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Company, Stage, TargetAnalysis
from .base import LLMProvider
from .prompts import SYSTEM_PROMPT, build_user_prompt, facts_fingerprint, parse_analysis


def get_provider(name: str) -> LLMProvider:
    if name == "mock":
        from .mock_provider import MockLLM

        return MockLLM()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"Fournisseur LLM inconnu : {name} (attendu : mock ou anthropic)")


@dataclass
class DraftReport:
    """Bilan d'un lot d'analyses."""

    generated: int = 0
    reused: int = 0
    failed: dict[str, str] = field(default_factory=dict)  # siren -> raison


def analyze_company(c: Company, provider: LLMProvider, retries: int = 1) -> Company:
    """Remplit `c.analysis`. Un JSON invalide est retenté ; le score n'est jamais modifié."""
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            raw = provider.complete(SYSTEM_PROMPT, build_user_prompt(c))
            c.analysis = parse_analysis(raw, provider.name)
            c.analysis.facts_hash = facts_fingerprint(c, provider.name)
            return c
        except ValueError as exc:
            last_err = exc
    raise ValueError(f"Analyse impossible pour {c.siren} : {last_err}")


def analyze_top(
    companies: list[Company],
    provider: LLMProvider,
    top_n: int,
    previous: dict[str, TargetAnalysis] | None = None,
) -> DraftReport:
    """Analyse en place les `top_n` meilleures cibles qualifiées.

    `previous` : analyses d'un run antérieur, réutilisées si l'empreinte des faits est identique.
    """
    report = DraftReport()
    qualified = sorted(
        (c for c in companies if c.stage == Stage.QUALIFIED),
        key=lambda c: -(c.score.total if c.score else 0.0),
    )
    for c in qualified[:top_n]:
        old = (previous or {}).get(c.siren)
        if old is not None and old.facts_hash == facts_fingerprint(c, provider.name):
            c.analysis = old
            report.reused += 1
            continue
        try:
            analyze_company(c, provider)
            report.generated += 1
        except Exception as exc:  # erreur réseau, quota, sortie invalide : on continue le lot
            report.failed[c.siren] = str(exc)[:300]
    return report
