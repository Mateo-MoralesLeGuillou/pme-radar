"""Fiche cible d'une page (Markdown) : identité, chiffres clés, score, mini-thèse, alertes, valeur."""

from __future__ import annotations

from typing import Any

from .models import Company

HEADCOUNT = {"11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199", "31": "200-249"}
DISCLAIMER = (
    "⚠️ **Ordre de grandeur, pas une valorisation.** Fourchette = EBE × multiples configurés, "
    "sans dette nette, BFR, normalisation de l'EBE, rémunération du dirigeant ni due diligence. "
    "Elle ne remplace ni une évaluation ni un avis."
)


def _eur(v: float | None) -> str:
    return "n.d." if v is None else f"{v / 1e6:,.2f} M€".replace(",", " ").replace(".", ",")


def _pct(v: float | None, signed: bool = False) -> str:
    return (
        "n.d."
        if v is None
        else f"{v:+.1%}".replace(".", ",")
        if signed
        else f"{v:.1%}".replace(".", ",")
    )


def valuation_range(c: Company, cfg: dict[str, Any]) -> tuple[float, float] | None:
    """(bas, haut) de la valeur d'entreprise, None si l'EBE manque ou n'est pas positif."""
    if c.ebe is None or c.ebe <= 0:
        return None
    return c.ebe * cfg["ebe_multiple_low"], c.ebe * cfg["ebe_multiple_high"]


def render(c: Company, valuation_cfg: dict[str, Any]) -> str:
    person = c.main_person()
    s, a = c.score, c.analysis
    L = [
        f"# {c.name}",
        "",
        f"**SIREN {c.siren}** · score **{s.total:.0f}/100** · statut `{c.stage.value}`",
        "",
    ]
    L += ["## Identité", "", "| | |", "|---|---|"]
    L += [
        f"| Activité | {c.naf_code or 'n.d.'} — {c.naf_label or 'n.d.'} |",
        f"| Localisation | {c.city or 'n.d.'} ({c.department or 'n.d.'}) |",
        f"| Effectif | {HEADCOUNT.get(c.headcount_band or '', 'n.d.')} salariés |",
        f"| Ancienneté | {c.company_age_years if c.company_age_years is not None else 'n.d.'} ans |",
        f"| Dirigeant | {person.name if person else 'n.d.'}"
        + (f", {c.director_age} ans" if c.director_age is not None else "")
        + (f" (via {c.holding_name})" if c.holding_name else "")
        + " |",
        f"| Dirigeant-exploitant | {'oui' if c.is_owner_operator else 'non' if c.is_owner_operator is False else 'n.d.'} |",
        "",
        "## Chiffres clés (dernier exercice connu)",
        "",
        "| | |",
        "|---|---|",
        f"| Chiffre d'affaires | {_eur(c.revenue_last)} |",
        f"| CAGR du CA | {_pct(c.revenue_cagr, True)}/an |"
        if c.revenue_cagr is not None
        else "| CAGR du CA | n.d. |",
        f"| EBE | {_eur(c.ebe)}" + (f" ({c.ebe_year})" if c.ebe_year else "") + " |",
        f"| Marge d'EBE | {_pct(c.ebe_margin)} |",
        f"| Résultat net | {_eur(c.net_income_last)} |",
        f"| Marge nette | {_pct(c.net_margin)} |",
        f"| Endettement (dettes / capitaux propres) | {'n.d.' if c.debt_ratio is None else f'{c.debt_ratio:.0f} %'} |",
        "",
        "## Détail du score",
        "",
        "| Critère | Points | Détail |",
        "|---|---:|---|",
    ]
    L += [f"| {r.label} | {r.points:g}/{r.max_points:g} | {r.detail} |" for r in s.criteria]
    L += [f"| *{p.label}* | {p.points:g} | {p.detail} |" for p in s.penalties]
    L += ["", "## Mini-thèse", ""]
    L += [f"- {t}" for t in a.mini_thesis] if a else ["_Non générée : lancer `pme-radar draft`._"]
    L += ["", "## Signaux d'alerte", ""]
    L += [f"- {t}" for t in a.red_flags] if a else ["_Non générés : lancer `pme-radar draft`._"]
    L += ["", "## Valorisation indicative", ""]
    v = valuation_range(c, valuation_cfg)
    lo, hi = valuation_cfg["ebe_multiple_low"], valuation_cfg["ebe_multiple_high"]
    if v:
        L.append(
            f"EBE {_eur(c.ebe)} × {lo:g} à {hi:g} = **{_eur(v[0])} à {_eur(v[1])}** de valeur d'entreprise."
        )
    else:
        L.append("Non calculable : EBE indisponible ou négatif.")
    L += ["", DISCLAIMER, ""]
    return "\n".join(L)
