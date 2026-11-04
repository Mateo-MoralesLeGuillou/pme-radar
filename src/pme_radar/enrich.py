"""Normalisation des résultats bruts de l'API en `Company` + champs dérivés.

Règle d'or : une donnée absente ou confidentielle reste `None`, jamais 0.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from .models import Company, Director, FinancialYear
from .sources import inpi_ratios as inpi

MAX_RATIO_AGE = 4  # ans, par rapport à la date de calcul
AGE_BOUNDS = (18, 100)  # âge plausible d'un dirigeant ; au-delà : erreur de saisie => None
HOLDING_NAF = "64.20Z"  # activités des sociétés holding
HoldingLookup = Callable[[str], dict[str, Any] | None]

ROLE_PRIORITY = ("président", "gérant", "directeur général", "dirigeant", "directeur", "associé")


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_director(raw: dict[str, Any]) -> Director:
    natural = "physique" in (raw.get("type_dirigeant") or "").lower()
    year = month = None
    dob = raw.get("date_de_naissance")  # « AAAA-MM » ou « AAAA-MM-JJ » selon les cas
    if dob:
        parts = str(dob).split("-")
        year = int(parts[0]) if parts[0].isdigit() else None
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    if year is None and raw.get("annee_de_naissance"):
        year = int(raw["annee_de_naissance"])
    if natural:
        name = " ".join(x for x in (raw.get("prenoms"), raw.get("nom")) if x) or None
    else:
        name = raw.get("denomination")
    return Director(
        is_natural_person=natural,
        name=name,
        siren=raw.get("siren") if not natural else None,
        role=raw.get("qualite"),
        birth_year=year if natural else None,
        birth_month=month if natural else None,
    )


def closing_year(row: dict[str, Any]) -> int | None:
    """Année de clôture d'une ligne de ratios ; None si absente ou illisible."""
    value = str(row.get("date_cloture_exercice") or "")[:4]
    return int(value) if value.isdigit() else None


def parse_financials(raw: dict[str, Any] | None) -> list[FinancialYear]:
    out = []
    for year, vals in sorted((raw or {}).items()):
        vals = vals or {}
        out.append(
            FinancialYear(
                year=int(year),
                revenue=vals.get("ca") or None,  # l'API renvoie ca=0 quand le CA n'est pas publié
                net_income=vals.get("resultat_net"),
            )
        )
    return out


def merge_ratios(fin: list[FinancialYear], rows: list[dict[str, Any]]) -> list[FinancialYear]:
    """Complète les exercices de l'API avec l'historique INPI (l'API prime sur une année commune)."""
    by_year = {f.year: f for f in fin}
    for r in rows:
        year = closing_year(r)
        if year is None:
            continue
        have = by_year.get(year)
        if have and have.revenue is not None:
            continue
        rev = r["chiffre_d_affaires"] if inpi.usable(r) else None
        net = r.get("resultat_net") if have is None else have.net_income
        by_year[year] = FinancialYear(year=year, revenue=rev, net_income=net)
    return [by_year[y] for y in sorted(by_year)]


def principal_director(directors: list[Director]) -> Director | None:
    """Dirigeant principal : rôle le plus « exécutif », à défaut le premier de la liste."""

    def rank(d: Director) -> int:
        role = (d.role or "").lower()
        for i, key in enumerate(ROLE_PRIORITY):
            if key in role:
                return i
        return len(ROLE_PRIORITY)

    return min(directors, key=rank) if directors else None


def personal_holding_owner(holding_raw: dict[str, Any] | None) -> Director | None:
    """Personne physique derrière une holding personnelle, sinon None.

    Holding personnelle = NAF 64.20Z ET dirigeant principal personne physique. Une holding dirigée
    par une société, ou une société d'un autre NAF (siège de groupe…), reste un « vrai groupe ».
    """
    if not holding_raw:
        return None
    naf = holding_raw.get("activite_principale") or (holding_raw.get("siege") or {}).get(
        "activite_principale"
    )
    if naf != HOLDING_NAF:
        return None
    main = principal_director([parse_director(d) for d in holding_raw.get("dirigeants") or []])
    return main if main and main.is_natural_person else None


def director_age(d: Director | None, as_of: date) -> int | None:
    """Âge en années. Si seule l'année de naissance est connue : estimation (±1 an)."""
    if d is None or not d.is_natural_person or d.birth_year is None:
        return None
    age = as_of.year - d.birth_year
    if d.birth_month is not None and as_of.month < d.birth_month:
        age -= 1
    return age if AGE_BOUNDS[0] <= age <= AGE_BOUNDS[1] else None


def company_age(creation: date | None, as_of: date) -> int | None:
    """Ancienneté en années révolues ; None si date absente ou postérieure à `as_of`."""
    if creation is None or creation > as_of:
        return None
    return as_of.year - creation.year - ((as_of.month, as_of.day) < (creation.month, creation.day))


def revenue_cagr(fin: list[FinancialYear]) -> float | None:
    pts = [(f.year, f.revenue) for f in fin if f.revenue is not None and f.revenue > 0]
    if len(pts) < 2:
        return None
    (y0, first), (y1, last) = pts[0], pts[-1]
    n = y1 - y0
    if n <= 0:
        return None
    return float((last / first) ** (1 / n) - 1)


def normalize(
    raw: dict[str, Any],
    as_of: date,
    naf_labels: dict[str, str] | None = None,
    holding_lookup: HoldingLookup | None = None,
    ratios: list[dict[str, Any]] | None = None,
) -> Company:
    siege = raw.get("siege") or {}
    naf = raw.get("activite_principale") or siege.get("activite_principale")
    directors = [parse_director(d) for d in raw.get("dirigeants") or []]
    fin = parse_financials(raw.get("finances"))
    # bilans de plus de MAX_RATIO_AGE ans écartés : un EBE de 2016 ne dit rien de la société actuelle
    # tri explicite du plus récent au plus ancien : ne dépend pas de l'ordre renvoyé par l'API
    ratios = sorted(
        (r for r in ratios or [] if (closing_year(r) or 0) >= as_of.year - MAX_RATIO_AGE),
        key=lambda r: str(r["date_cloture_exercice"]),
        reverse=True,
    )
    if ratios:
        fin = merge_ratios(fin, ratios)
    ebe_row = next((r for r in ratios if inpi.usable(r) and r.get("ebe") is not None), None)
    debt_row = next((r for r in ratios if r.get("taux_d_endettement") is not None), None)
    creation = _parse_date(raw.get("date_creation"))
    principal = principal_director(directors)

    # Dirigeant société : holding personnelle de fondateur ou vrai groupe ? (ADR-009)
    owner: Director | None = None
    holding_name: str | None = None
    if principal and not principal.is_natural_person and principal.siren and holding_lookup:
        owner = personal_holding_owner(holding_lookup(principal.siren))
        holding_name = principal.name if owner else None
    corporate_group = bool(principal and not principal.is_natural_person and owner is None)

    with_rev = [f for f in fin if f.revenue is not None]
    last = with_rev[-1] if with_rev else None
    last_any = fin[-1] if fin else None
    margin = None
    if last and last.revenue and last.net_income is not None:
        margin = last.net_income / last.revenue

    return Company(
        siren=raw["siren"],
        name=raw.get("nom_complet") or raw.get("nom_raison_sociale") or raw["siren"],
        naf_code=naf,
        naf_label=(naf_labels or {}).get(naf or ""),
        headcount_band=raw.get("tranche_effectif_salarie") or siege.get("tranche_effectif_salarie"),
        creation_date=creation,
        legal_form=str(raw.get("nature_juridique")) if raw.get("nature_juridique") else None,
        category=raw.get("categorie_entreprise"),
        postal_code=siege.get("code_postal"),
        city=siege.get("libelle_commune"),
        department=siege.get("departement"),
        directors=directors,
        financials=fin,
        director_age=director_age(owner or principal, as_of),
        company_age_years=company_age(creation, as_of),
        is_owner_operator=(
            None if principal is None else (principal.is_natural_person or owner is not None)
        ),
        n_natural_directors=sum(d.is_natural_person for d in directors) + (1 if owner else 0),
        has_corporate_director=corporate_group,
        holding_name=holding_name,
        holding_owner=owner,
        revenue_last=last.revenue if last else None,
        net_income_last=last_any.net_income if last_any else None,
        net_margin=margin,
        revenue_cagr=revenue_cagr(with_rev),
        ebe=ebe_row["ebe"] if ebe_row else None,
        ebe_margin=ebe_row["ebe"] / ebe_row["chiffre_d_affaires"] if ebe_row else None,
        ebe_year=closing_year(ebe_row) if ebe_row else None,
        debt_ratio=debt_row["taux_d_endettement"] if debt_row else None,
        accounts_available=last is not None,  # CA publié (sinon pénalité)
    )


def enrich(
    raw_results: Iterable[dict[str, Any]],
    as_of: date,
    naf_labels: dict[str, str] | None = None,
    procedure_sirens: set[str] | None = None,
    holding_lookup: HoldingLookup | None = None,
    ratios: dict[str, list[dict[str, Any]]] | None = None,
) -> list[Company]:
    """`procedure_sirens=None` => BODACC non interrogé (flag laissé à None)."""
    memo: dict[str, dict[str, Any] | None] = {}

    def lookup(siren: str) -> dict[str, Any] | None:  # une seule requête par société dirigeante
        if siren not in memo:
            memo[siren] = holding_lookup(siren)  # type: ignore[misc]
        return memo[siren]

    companies = [
        normalize(
            r,
            as_of,
            naf_labels,
            lookup if holding_lookup else None,
            (ratios or {}).get(r["siren"]),
        )
        for r in raw_results
    ]
    if procedure_sirens is not None:
        for c in companies:
            c.has_collective_procedure = c.siren in procedure_sirens
    return companies
