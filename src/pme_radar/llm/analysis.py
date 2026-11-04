"""Orchestration : analyse + brouillon d'email pour le top N des cibles qualifiées."""

from __future__ import annotations

from ..models import Company, Stage
from .base import LLMProvider
from .prompts import SYSTEM_PROMPT, build_user_prompt, parse_analysis


def get_provider(name: str) -> LLMProvider:
    if name == "mock":
        from .mock_provider import MockLLM

        return MockLLM()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"Fournisseur LLM inconnu : {name}")


def analyze_company(c: Company, provider: LLMProvider, retries: int = 1) -> Company:
    """Remplit `c.analysis`. Un JSON invalide est retenté ; le score n'est jamais modifié."""
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            raw = provider.complete(SYSTEM_PROMPT, build_user_prompt(c))
            c.analysis = parse_analysis(raw, provider.name)
            return c
        except ValueError as exc:
            last_err = exc
    raise ValueError(f"Analyse impossible pour {c.siren} : {last_err}")


def analyze_top(companies: list[Company], provider: LLMProvider, top_n: int) -> list[Company]:
    """Analyse les `top_n` meilleures cibles qualifiées ; renvoie la liste complète."""
    qualified = sorted(
        (c for c in companies if c.stage == Stage.QUALIFIED), key=lambda c: -c.score.total
    )
    for c in qualified[:top_n]:
        analyze_company(c, provider)
    return companies
