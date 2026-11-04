"""Prompts versionnés + validation de la sortie JSON par pydantic.

Le LLM ne touche jamais au score : il rédige une analyse qualitative et un brouillon d'email.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError, field_validator

from ..models import Company, TargetAnalysis

PROMPT_VERSION = "v1"
FACTS_OPEN, FACTS_CLOSE = "<facts>", "</facts>"

# Promesses ou pressions interdites dans un email d'approche à un cédant.
FORBIDDEN = (
    "garantie",
    "garanti",
    "urgent",
    "dernière chance",
    "offre ferme",
    "prix exceptionnel",
    "sans engagement de votre part et à très court terme",
)

SYSTEM_PROMPT = """Tu es analyste dans un search fund français qui cherche à reprendre une PME \
et à la diriger sur le long terme. Tu t'appuies UNIQUEMENT sur les faits fournis entre balises \
<facts>. N'invente aucun chiffre, aucun client, aucun événement. Si une donnée manque, dis-le.
Réponds par un unique objet JSON, sans texte autour, avec exactement les clés :
- "mini_thesis" : liste de 3 phrases courtes (pourquoi un repreneur pourrait s'y intéresser) ;
- "red_flags" : liste de signaux d'alerte (dépendance client, cyclicité, activité liée à la \
personne du dirigeant, données manquantes…), formulés comme des hypothèses à vérifier ;
- "email_subject" : objet court et sobre ;
- "email_body" : email d'approche de 90 à 140 mots, en français, vouvoiement, ton respectueux, \
axé sur la transmission et la continuité de l'entreprise et des équipes. Jamais agressif, \
aucune fausse promesse, aucune pression, aucun prix annoncé. Mentionne qu'un refus est \
parfaitement entendable. Termine par une signature générique « [Prénom Nom] »."""

_FIELDS = (
    "name",
    "naf_label",
    "city",
    "department",
    "headcount_band",
    "company_age_years",
    "director_age",
    "revenue_last",
    "net_margin",
    "ebe",
    "ebe_margin",
    "debt_ratio",
    "revenue_cagr",
    "accounts_available",
    "is_owner_operator",
    "n_natural_directors",
)


def company_facts(c: Company) -> dict:
    """Faits minimisés transmis au LLM (RGPD : nom du dirigeant seulement pour la salutation)."""
    facts = {k: getattr(c, k) for k in _FIELDS}
    person = c.main_person()
    facts["director_name"] = person.name if person else None
    facts["score_summary"] = c.score.summary if c.score else None
    return facts


def build_user_prompt(c: Company) -> str:
    facts = json.dumps(company_facts(c), ensure_ascii=False, default=str)
    return f"Prépare l'analyse de cette cible.\n{FACTS_OPEN}{facts}{FACTS_CLOSE}"


class _Validated(TargetAnalysis):
    @field_validator("mini_thesis")
    @classmethod
    def _three(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("mini_thesis doit contenir exactement 3 lignes")
        return v

    @field_validator("email_body")
    @classmethod
    def _tone(cls, v: str) -> str:
        low = v.lower()
        bad = [w for w in FORBIDDEN if w in low]
        if bad:
            raise ValueError(f"formulation interdite dans l'email : {bad}")
        if len(v.split()) > 200:
            raise ValueError("email trop long")
        return v


def parse_analysis(raw: str, provider: str) -> TargetAnalysis:
    """Extrait et valide le JSON. Lève ValueError si la sortie n'est pas conforme."""
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError("aucun JSON dans la réponse")
    try:
        obj = _Validated.model_validate(
            {**json.loads(match.group(0)), "prompt_version": PROMPT_VERSION, "provider": provider}
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"sortie LLM invalide : {exc}") from exc
    return TargetAnalysis(**obj.model_dump())
