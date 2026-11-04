"""Ratios financiers BCE/INPI : enrichissement optionnel, volontairement non branché (ADR-005)."""

from __future__ import annotations


def load_ratios(path: str) -> dict[str, dict[str, float]]:  # pragma: no cover
    """Point d'extension : retournerait {siren: {"ebe": …, "endettement": …}}."""
    raise NotImplementedError("Ratios INPI non implémentés : voir docs/decisions.md (ADR-005).")
