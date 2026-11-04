"""Score « search fund fit » déterministe et explicable (barèmes dans config/scoring.yaml)."""

from __future__ import annotations

from typing import Any

from .models import Company, CriterionScore, ScoreBreakdown, Stage


def _band_points(value: float | None, bands: list[dict[str, Any]]) -> float:
    """Premier palier (ordre du YAML) dont min est atteint et max non dépassé."""
    if value is None:
        return 0.0
    for b in bands:
        if value >= b["min"] and ("max" not in b or value <= b["max"]):
            return float(b["points"])
    return 0.0


def _fmt_m(v: float | None) -> str:
    return "n.d." if v is None else f"{v / 1e6:.1f} M€".replace(".", ",")


def score_company(c: Company, cfg: dict[str, Any], tiers: dict[str, str]) -> ScoreBreakdown:
    """Calcule le ScoreBreakdown. Les critères manquants valent 0 et sont signalés « n.d. »."""
    k = cfg["criteria"]
    rows: list[CriterionScore] = []

    def add(key: str, label: str, pts: float, detail: str, spec: dict[str, Any]) -> None:
        rows.append(
            CriterionScore(
                key=key, label=label, points=pts, max_points=spec["max_points"], detail=detail
            )
        )

    age = c.director_age
    add(
        "director_age",
        "Âge du dirigeant",
        _band_points(age, k["director_age"]["bands"]),
        f"{age} ans" if age is not None else "n.d.",
        k["director_age"],
    )
    oo = k["owner_operator"]
    add(
        "owner_operator",
        "Dirigeant-exploitant (personne physique)",
        oo["max_points"] if c.is_owner_operator else 0,
        "oui (via holding personnelle)"
        if c.holding_owner
        else {True: "oui", False: "non (groupe)", None: "n.d."}[c.is_owner_operator],
        oo,
    )
    ns = k["no_obvious_successor"]
    solo = c.n_natural_directors == 1
    add(
        "no_obvious_successor",
        "Pas de successeur évident",
        ns["max_points"] if solo else 0,
        f"{c.n_natural_directors} dirigeant(s) personne physique",
        ns,
    )

    rev_m = None if c.revenue_last is None else c.revenue_last / 1e6
    add(
        "revenue",
        "Chiffre d'affaires",
        _band_points(rev_m, k["revenue"]["bands"]),
        _fmt_m(c.revenue_last),
        k["revenue"],
    )
    hc = k["headcount"]
    add(
        "headcount",
        "Effectif",
        float(hc["by_band"].get(c.headcount_band or "", 0)),
        f"tranche {c.headcount_band or 'n.d.'}",
        hc,
    )

    prof = k["profitability"]
    if c.ebe_margin is not None:  # EBE : métrique principale, insensible à la structure financière
        add(
            "profitability",
            "Rentabilité : marge d'EBE",
            _band_points(c.ebe_margin, prof["ebe_margin_bands"]),
            f"{c.ebe_margin:.0%} (EBE {_fmt_m(c.ebe)}, {c.ebe_year})",
            prof,
        )
    else:
        add(
            "profitability",
            "Rentabilité : marge nette (repli, EBE n.d.)",
            _band_points(c.net_margin, prof["net_margin_bands"]),
            "n.d." if c.net_margin is None else f"{c.net_margin:.0%}",
            prof,
        )
    add(
        "revenue_cagr",
        "Régularité / croissance du CA",
        _band_points(c.revenue_cagr, k["revenue_cagr"]["bands"]),
        "n.d." if c.revenue_cagr is None else f"{c.revenue_cagr:+.1%}/an",
        k["revenue_cagr"],
    )
    add(
        "company_age",
        "Ancienneté",
        _band_points(c.company_age_years, k["company_age"]["bands"]),
        "n.d." if c.company_age_years is None else f"{c.company_age_years} ans",
        k["company_age"],
    )

    tier = tiers.get(c.naf_code or "")
    th = k["thesis_fit"]
    add(
        "thesis_fit",
        "Adéquation à la thèse",
        float(th["by_tier"].get(tier or "", 0)),
        f"NAF {c.naf_code or 'n.d.'} ({tier or 'hors thèse'})",
        th,
    )

    penalties: list[CriterionScore] = []
    pen = cfg["penalties"]
    if c.has_corporate_director:
        penalties.append(
            CriterionScore(
                key="corporate_director",
                label="Dirigeant personne morale",
                points=pen["corporate_director"],
                max_points=0,
                detail="société dirigeante = probable groupe/filiale",
            )
        )
    if not c.accounts_available:
        penalties.append(
            CriterionScore(
                key="missing_financials",
                label="Comptes non disponibles",
                points=pen["missing_financials"],
                max_points=0,
                detail="comptes absents ou confidentiels",
            )
        )

    excl = cfg.get("exclusions", {})
    if excl.get("collective_procedure") and c.has_collective_procedure:
        return ScoreBreakdown(
            total=0,
            criteria=rows,
            penalties=penalties,
            excluded=True,
            exclusion_reason="procédure collective (BODACC)",
            summary="Exclue : procédure collective en cours ou passée (BODACC).",
        )

    total = max(0.0, min(100.0, sum(r.points for r in rows) + sum(p.points for p in penalties)))
    return ScoreBreakdown(
        total=round(total, 1),
        criteria=rows,
        penalties=penalties,
        summary=_summary(c, total, penalties),
    )


def _summary(c: Company, total: float, penalties: list[CriterionScore]) -> str:
    parts = [
        f"dirigeant {c.director_age} ans"
        if c.director_age is not None
        else "âge du dirigeant n.d.",
        f"CA {_fmt_m(c.revenue_last)}",
        f"marge d'EBE {c.ebe_margin:.0%}"
        if c.ebe_margin is not None
        else f"marge nette {c.net_margin:.0%}"
        if c.net_margin is not None
        else "marge n.d.",
        f"{c.company_age_years} ans d'ancienneté" if c.company_age_years is not None else "",
    ]
    text = f"{total:.0f}/100 : " + ", ".join(p for p in parts if p)
    if penalties:
        text += " ; pénalités : " + ", ".join(p.label.lower() for p in penalties)
    return text + "."


def score_all(
    companies: list[Company], cfg: dict[str, Any], thesis: dict[str, Any]
) -> list[Company]:
    """Score + statut (`excluded` / `qualified` / `identified`). Tri par score décroissant."""
    tiers = {n["code"]: n["tier"] for n in thesis["naf_codes"]}
    threshold = cfg["qualified_threshold"]
    for c in companies:
        c.score = score_company(c, cfg, tiers)
        if c.score.excluded:
            c.stage = Stage.EXCLUDED
        elif c.score.total >= threshold:
            c.stage = Stage.QUALIFIED
        else:
            c.stage = Stage.IDENTIFIED
    return sorted(
        companies,
        key=lambda c: (c.stage == Stage.EXCLUDED, -(c.score.total if c.score else 0.0)),
    )
