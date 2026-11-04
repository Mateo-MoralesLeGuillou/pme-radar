"""Évaluation « deal » d'une cible : valorisation, montage LBO indicatif, recommandation, pré-DD.

Tout est déterministe et paramétré (config/thesis.yaml : valuation, financing ; config/scoring.yaml :
risk_thresholds). Les montants sont des ordres de grandeur pour décider d'un premier appel, pas une
évaluation : ni dette nette, ni BFR, ni EBE normalisé (ADR-020).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fmt import eur, pct
from .models import Company, Stage
from .risks import Signal, thresholds

DEFAULT_FINANCING: dict[str, float] = {
    "senior_debt_multiple": 2.5,
    "max_debt_share": 0.6,
    "vendor_loan_share": 0.10,
    "interest_rate": 0.055,
    "amortization_years": 7,
    "cash_conversion": 0.6,
    "min_coverage": 1.3,
    "max_equity_ticket": 6_000_000,
    "transaction_fees": 0.04,
}
DEFAULT_VALUATION = {"ebe_multiple_low": 4.0, "ebe_multiple_high": 6.0}


@dataclass(frozen=True)
class Financing:
    """Montage indicatif au milieu de la fourchette de valeur d'entreprise.

    Emplois = prix (valeur d'entreprise, milieu de fourchette) + frais de transaction ;
    Ressources = dette senior + crédit vendeur + fonds propres (qui bouclent le tableau)."""

    ebe: float
    ebe_year: int | None
    ev_low: float
    ev_mid: float
    ev_high: float
    fees: float
    senior_debt: float
    vendor_loan: float
    equity: float
    annual_debt_service: float
    coverage: float  # flux disponible pour la dette / service annuel de la dette

    @property
    def uses(self) -> float:
        return self.ev_mid + self.fees

    @property
    def equity_share(self) -> float:
        return self.equity / self.uses


@dataclass
class Recommendation:
    label: str  # À approcher | À creuser | À documenter | Non prioritaire | Écartée
    tone: str  # go | dig | doc | low | out (classes CSS du rapport)
    reasons: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


def financing_plan(c: Company, thesis: dict[str, Any]) -> Financing | None:
    """None si l'EBE manque ou n'est pas positif : pas de valeur ni de montage sans EBE."""
    if c.ebe is None or c.ebe <= 0:
        return None
    val = {**DEFAULT_VALUATION, **(thesis.get("valuation") or {})}
    fin = {**DEFAULT_FINANCING, **(thesis.get("financing") or {})}
    low, high = c.ebe * val["ebe_multiple_low"], c.ebe * val["ebe_multiple_high"]
    mid = (low + high) / 2
    debt = min(c.ebe * fin["senior_debt_multiple"], mid * fin["max_debt_share"])
    vendor = mid * fin["vendor_loan_share"]
    fees = mid * fin["transaction_fees"]
    rate, years = fin["interest_rate"], fin["amortization_years"]
    annuity = debt * rate / (1 - (1 + rate) ** -years) if rate > 0 else debt / years
    available = c.ebe * fin["cash_conversion"]
    return Financing(
        ebe=c.ebe,
        ebe_year=c.ebe_year,
        ev_low=low,
        ev_mid=mid,
        ev_high=high,
        fees=fees,
        senior_debt=debt,
        vendor_loan=vendor,
        equity=mid + fees - debt - vendor,
        annual_debt_service=annuity,
        coverage=available / annuity if annuity else float("inf"),
    )


NEXT_STEPS = {
    "go": [
        "Relire, adapter puis envoyer le brouillon d'approche.",
        "Préparer l'appel découverte avec les questions prioritaires du plan de due diligence.",
        "Après un premier échange positif : demander les trois dernières liasses fiscales.",
    ],
    "dig": [
        "Lever d'abord le signal fort (voir les signaux factuels).",
        "Vérifier les comptes déposés et l'historique BODACC.",
        "Décider ensuite d'une approche, ou classer.",
    ],
    "doc": [
        "Compléter les données manquantes listées dans ce dossier.",
        "Relancer `pme-radar score` : la cible peut franchir le seuil.",
        "Approcher si le score confirmé atteint le seuil.",
    ],
    "low": ["Conserver en veille ; réévaluer au prochain run hebdomadaire."],
    "out": ["Aucune approche. Surveiller l'issue de la procédure au BODACC."],
}


def recommend(
    c: Company,
    signals: list[Signal],
    plan: Financing | None,
    scoring_cfg: dict[str, Any],
    thesis: dict[str, Any],
) -> Recommendation:
    """Recommandation par règles explicites, dans cet ordre : exclusion, signal fort, fiabilité,
    ticket de fonds propres, puis qualification. La couverture de la dette n'entre pas dans la
    règle : avec des hypothèses proportionnelles à l'EBE, elle ne dépend que des hypothèses."""
    s = c.score
    threshold = scoring_cfg.get("qualified_threshold", 70)
    min_conf = thresholds(scoring_cfg)["min_confidence"]
    fin = {**DEFAULT_FINANCING, **(thesis.get("financing") or {})}

    def rec(label: str, tone: str, *reasons: str) -> Recommendation:
        return Recommendation(label, tone, list(reasons), NEXT_STEPS[tone])

    if s is None:
        return rec("Non prioritaire", "low", "Cible non notée : lancer `pme-radar score`.")
    if s.excluded:
        return rec("Écartée", "out", f"Exclue : {s.exclusion_reason}.")
    strong = [x.title.lower() for x in signals if x.level == "élevé"]
    if c.stage == Stage.QUALIFIED:
        if strong:
            return rec("À creuser", "dig", f"Qualifiée ({s.total:.0f}/100) mais signal fort : "
                       f"{', '.join(strong)}.")  # fmt: skip
        if s.confidence < min_conf:
            return rec("À documenter", "doc",
                       f"Score de {s.total:.0f}/100 établi sur {pct(s.confidence, 0)} du barème "
                       "seulement.",
                       f"Plafond à {s.ceiling:.0f}/100 si les données manquantes sont favorables.")  # fmt: skip
        if plan is not None and plan.equity > fin["max_equity_ticket"]:
            return rec("À creuser", "dig", f"Qualifiée ({s.total:.0f}/100), mais ticket de fonds "
                       f"propres de {eur(plan.equity)} au-delà du plafond de "
                       f"{eur(fin['max_equity_ticket'])}.")  # fmt: skip
        reasons = [
            f"Score {s.total:.0f}/100 au-dessus du seuil de {threshold}.",
            f"Fiabilité des données : {pct(s.confidence, 0)} du barème.",
        ]
        if plan is not None:
            reasons.append(f"Valeur indicative {eur(plan.ev_low)} à {eur(plan.ev_high)} ; "
                           f"fonds propres à réunir ≈ {eur(plan.equity)}.")  # fmt: skip
        else:
            reasons.append(
                "Valorisation non calculable (EBE indisponible) : à obtenir au 1er appel."
            )
        return rec("À approcher", "go", *reasons)
    if s.to_document:
        return rec("À documenter", "doc",
                   f"Score de {s.total:.0f}/100 sous le seuil de {threshold}, mais plafond à "
                   f"{s.ceiling:.0f} : les données manquantes peuvent la qualifier.")  # fmt: skip
    return rec("Non prioritaire", "low",
               f"Score {s.total:.0f}/100 et plafond {s.ceiling:.0f} sous le seuil de {threshold}.")  # fmt: skip


# ---------------------------------------------------------------- pré-due diligence
DD_THEMES = (
    "Transmission",
    "Commercial",
    "Financier",
    "RH & organisation",
    "Juridique",
    "Opérations",
)
DD_BANK: dict[str, list[str]] = {
    "Transmission": [
        "Pourquoi céder maintenant, et selon quel calendrier ?",
        "Le cédant accepterait-il un accompagnement de 6 à 12 mois et un crédit vendeur ?",
        "Un repreneur familial ou interne est-il envisagé ?",
    ],
    "Commercial": [
        "Poids des 5 et 10 premiers clients dans le chiffre d'affaires ?",
        "Part du chiffre d'affaires sous contrat récurrent (maintenance) et durée des contrats ?",
        "Carnet de commandes et taux de renouvellement sur trois ans ?",
    ],
    "Financier": [
        "EBE normalisé : rémunération du dirigeant, loyers, éléments exceptionnels ?",
        "Besoin en fonds de roulement : délais clients et fournisseurs ?",
        "Investissements de maintien annuels (véhicules, outillage, informatique) ?",
    ],
    "RH & organisation": [
        "Organigramme, encadrement intermédiaire et personnes clés ?",
        "Turnover, pyramide des âges, difficultés de recrutement des techniciens ?",
        "Habilitations et certifications nominatives (électriques, sécurité) ?",
    ],
    "Juridique": [
        "Litiges en cours, contrôles fiscaux ou URSSAF récents ?",
        "Baux commerciaux : échéances, et le bailleur est-il une SCI du dirigeant ?",
        "Contrats clés : clauses de changement de contrôle ?",
    ],
    "Opérations": [
        "Part de la sous-traitance et dépendance à des fournisseurs ?",
        "Outils de pilotage (ERP, GMAO) et fiabilité des données de suivi ?",
        "Sinistralité, assurances et conformité HSE ?",
    ],
}
DOCUMENTS = [
    "Trois dernières liasses fiscales et comptes annuels",
    "Situation intermédiaire de l'exercice en cours",
    "Chiffre d'affaires par client (top 20) sur trois ans",
    "Balance âgée clients et fournisseurs",
    "Contrats clients et fournisseurs significatifs",
    "Organigramme et registre du personnel",
    "Statuts, Kbis, pacte d'associés, baux",
    "Tableau des immobilisations et plan d'investissement",
]
GAP_LABELS = {
    "director_age": "Âge du dirigeant (calendrier de transmission)",
    "owner_operator": "Identité du dirigeant opérationnel",
    "no_obvious_successor": "Composition de la direction",
    "revenue": "Chiffre d'affaires du dernier exercice",
    "headcount": "Effectif",
    "profitability": "EBE ou résultat net (rentabilité)",
    "revenue_cagr": "Historique du chiffre d'affaires (au moins deux exercices)",
    "company_age": "Date de création",
    "thesis_fit": "Code NAF",
}


def dd_questions(signals: list[Signal]) -> dict[str, list[str]]:
    """Questions par thème : celles déclenchées par les signaux d'abord, puis la base générique."""
    out: dict[str, list[str]] = {t: [] for t in DD_THEMES}
    for s in signals:
        out.setdefault(s.theme, []).append(s.question)
    for theme, questions in DD_BANK.items():
        out[theme].extend(q for q in questions if q not in out[theme])
    return out


def data_gaps(c: Company) -> list[str]:
    """Données manquantes au score, formulées comme informations à obtenir."""
    if c.score is None:
        return []
    gaps = [GAP_LABELS.get(r.key, r.label) for r in c.score.criteria if r.missing]
    if c.ebe is None and "EBE ou résultat net (rentabilité)" not in gaps:
        gaps.append("EBE (valorisation et capacité d'endettement)")
    return gaps


# ---------------------------------------------------------------- analyses complémentaires
def sensitivity(
    plan: Financing, thesis: dict[str, Any]
) -> tuple[list[float], list[float], list[list[float]]]:
    """Grille de valeur d'entreprise : lignes = EBE (-20 % à +20 %), colonnes = multiples encadrant
    la fourchette de la thèse. Renvoie (multiples, variations d'EBE, valeurs)."""
    val = {**DEFAULT_VALUATION, **(thesis.get("valuation") or {})}
    lo, hi = val["ebe_multiple_low"], val["ebe_multiple_high"]
    multiples = [lo - 0.5, lo, (lo + hi) / 2, hi, hi + 0.5]
    deltas = [-0.2, -0.1, 0.0, 0.1, 0.2]
    grid = [[plan.ebe * (1 + d) * m for m in multiples] for d in deltas]
    return multiples, deltas, grid


def highlights(c: Company, tier: str | None) -> list[str]:
    """Points forts établis à partir des données (aucune appréciation de l'IA)."""
    out: list[str] = []
    if c.director_age is not None and c.director_age >= 58:
        via = f", via {c.holding_name}" if c.holding_name else ""
        out.append(f"Dirigeant de {c.director_age} ans{via} : fenêtre de transmission plausible.")
    if c.revenue_last is not None and 3e6 <= c.revenue_last <= 30e6:
        out.append(f"Chiffre d'affaires de {eur(c.revenue_last)} : dans la cible d'un search fund.")
    if c.ebe_margin is not None and c.ebe_margin >= 0.08:
        out.append(f"Rentabilité solide : marge d'EBE de {pct(c.ebe_margin)}.")
    elif c.ebe_margin is None and c.net_margin is not None and c.net_margin >= 0.05:
        out.append(f"Rentabilité solide : marge nette de {pct(c.net_margin)}.")
    if c.revenue_cagr is not None and c.revenue_cagr >= 0:
        out.append(
            f"Chiffre d'affaires en progression : {pct(c.revenue_cagr, signed=True)} par an."
        )
    if c.company_age_years is not None and c.company_age_years >= 20:
        out.append(f"{c.company_age_years} ans d'existence : modèle éprouvé sur plusieurs cycles.")
    if tier == "core":
        out.append(f"Activité au cœur de la thèse (NAF {c.naf_code}).")
    if c.debt_ratio is not None and c.debt_ratio <= 50:
        out.append(f"Endettement modéré : {c.debt_ratio:.0f} % des capitaux propres.")
    return out


# Documents prioritaires selon les signaux de la cible ; les documents absents de DOCUMENTS sont ajoutés.
SIGNAL_DOCUMENTS: dict[str, list[str]] = {
    "Procédure collective au BODACC": ["Jugements, plan de continuation et état du passif"],
    "Endettement élevé": ["Tableau d'endettement : échéancier, taux, covenants et garanties"],
    "Société dirigée par une autre société": ["Organigramme juridique et conventions intra-groupe"],
    "Dépendance au dirigeant": ["Organigramme et registre du personnel",
                                "Chiffre d'affaires par client (top 20) sur trois ans"],
    "Comptes non publiés": ["Trois dernières liasses fiscales et comptes annuels"],
    "Rentabilité faible": ["Situation intermédiaire de l'exercice en cours",
                           "Détail des charges et des éléments non récurrents"],
    "Dernier exercice déficitaire": ["Détail des charges et des éléments non récurrents"],
    "Chiffre d'affaires en baisse": ["Chiffre d'affaires par client (top 20) sur trois ans"],
    "Comptes anciens": ["Situation intermédiaire de l'exercice en cours"],
    "Détention via une holding personnelle": ["Statuts, Kbis, pacte d'associés, baux",
                                              "Comptes annuels de la holding"],
    "EBE non disponible": ["Trois dernières liasses fiscales et comptes annuels"],
}  # fmt: skip


def information_requests(signals: list[Signal]) -> list[tuple[str, str]]:
    """Liste de demandes d'informations : (document, priorité), priorité haute d'abord."""
    high: list[str] = []
    for s in signals:
        for doc in SIGNAL_DOCUMENTS.get(s.title, []):
            if doc not in high:
                high.append(doc)
    normal = [d for d in DOCUMENTS if d not in high]
    return [(d, "Haute") for d in high] + [(d, "Normale") for d in normal]


THEME_CODES = {"Transmission": "T", "Commercial": "C", "Financier": "F", "RH & organisation": "R",
               "Juridique": "J", "Opérations": "O"}  # fmt: skip


def dd_plan(signals: list[Signal]) -> list[tuple[str, str, str, str]]:
    """Plan de due diligence numéroté : (code, chantier, question, priorité)."""
    triggered = {s.question for s in signals}
    rows = []
    for theme, questions in dd_questions(signals).items():
        for i, q in enumerate(questions, 1):
            rows.append((f"{THEME_CODES.get(theme, theme[:1])}.{i}", theme, q,
                         "Haute" if q in triggered else "Normale"))  # fmt: skip
    return rows
