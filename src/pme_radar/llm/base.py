"""Interface commune des fournisseurs LLM (interchangeables)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Retourne la réponse brute du modèle (JSON attendu par `analysis`)."""
