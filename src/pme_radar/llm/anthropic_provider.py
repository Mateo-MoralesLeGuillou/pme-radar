"""Fournisseur Anthropic (optionnel : `pip install -e .[llm]` + identifiants Anthropic).

- `stop_reason` est vérifié avant de lire la réponse : un refus des classifieurs de sécurité
  (`refusal`) ou une réponse tronquée (`max_tokens`) lève une erreur explicite, sans nouvel
  essai payant (ADR-015).
- Repli serveur `fallbacks: "default"` (beta) sur les modèles qui l'acceptent : une demande
  déclinée est rejouée par Anthropic sur le modèle recommandé pour la catégorie de refus.
  Désactivable avec `ANTHROPIC_FALLBACKS=off`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import LLMProvider

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Modèles acceptant `fallbacks: "default"` (Claude API). Les autres sont appelés sans repli.
FALLBACK_MODELS = frozenset(
    {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
)
# Sources d'identifiants résolues par le SDK, dans l'ordre (clé, jeton, profil `ant auth login`,
# fédération d'identité de charge de travail).
CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_PROFILE",
    "ANTHROPIC_FEDERATION_RULE_ID",
)


class LLMRefusal(RuntimeError):
    """Le modèle a décliné la demande : un nouvel essai identique serait refusé et facturé."""


def has_credentials() -> bool:
    """Vrai si le SDK peut trouver des identifiants (variable d'environnement ou profil)."""
    if any(os.getenv(name) for name in CREDENTIAL_ENV):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self, model: str | None = None, max_tokens: int = 16000, client: Any = None
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Installer l'extra : pip install -e .[llm]") from exc
            if not has_credentials():
                raise RuntimeError(
                    "Identifiants Anthropic introuvables : renseigner ANTHROPIC_API_KEY dans "
                    ".env (voir .env.example) ou lancer `ant auth login`."
                )
            client = anthropic.Anthropic()
        self._client = client
        self.model: str = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        # La réflexion adaptative (active par défaut sur les modèles récents) consomme aussi ce
        # plafond : trop bas, le JSON serait coupé. Seuls les jetons produits sont facturés.
        self.max_tokens = max_tokens
        self.fallbacks = (
            os.getenv("ANTHROPIC_FALLBACKS", "default").strip().lower() != "off"
            and self.model in FALLBACK_MODELS
        )

    def request(self, system: str, user: str) -> dict[str, Any]:
        """Paramètres de l'appel (séparés pour être testés sans réseau)."""
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def complete(self, system: str, user: str) -> str:
        msg = self._client.beta.messages.create(**self.request(system, user))
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            category = getattr(details, "category", None) or "non précisée"
            raise LLMRefusal(f"refus du modèle (catégorie : {category})")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError(f"réponse tronquée : plafond de {self.max_tokens} jetons atteint")
        return "".join(block.text for block in msg.content if block.type == "text")
