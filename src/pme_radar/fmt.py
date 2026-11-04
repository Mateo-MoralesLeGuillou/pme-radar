"""Formats d'affichage français partagés (montants, pourcentages)."""

from __future__ import annotations


def eur(v: float | None, signed: bool = False) -> str:
    """Montant lisible : « 1,25 M€ », « 850 k€ », « n.d. »."""
    if v is None:
        return "n.d."
    sign = "+" if signed and v > 0 else ""
    if abs(v) >= 1e6:
        return f"{sign}{v / 1e6:,.2f} M€".replace(",", " ").replace(".", ",")
    return f"{sign}{v / 1e3:,.0f} k€".replace(",", " ")


NNBSP = "\u202f"  # espace fine insécable avant « % »


def pct(v: float | None, digits: int = 1, signed: bool = False) -> str:
    """Pourcentage à la française : « 12,5 % », « +7,9 % »."""
    if v is None:
        return "n.d."
    text = f"{v * 100:+.{digits}f}" if signed else f"{v * 100:.{digits}f}"
    return text.replace(".", ",") + f"{NNBSP}%"


def mult(v: float | None) -> str:
    """Multiple : « 1,36x »."""
    return "n.d." if v is None else f"{v:.2f}x".replace(".", ",")
