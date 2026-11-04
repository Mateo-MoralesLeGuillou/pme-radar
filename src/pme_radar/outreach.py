"""Brouillons d'emails et suivi de campagne en CSV. Le pipeline n'envoie JAMAIS d'email."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .models import Company

STATUSES = ("draft", "contacted", "replied", "meeting", "declined", "bounced")
CAMPAIGN_COLS = [
    "siren",
    "campaign_id",
    "status",
    "sent_date",
    "replied_date",
    "meeting_date",
    "updated_date",
    "note",
]
_DATE_FIELD = {
    "contacted": "sent_date",
    "replied": "replied_date",
    "declined": "replied_date",
    "meeting": "meeting_date",
}


def with_footer(body: str, footer: str | None) -> str:
    """Ajoute la mention de conformité (source des données + droit d'opposition), déterministe :
    elle ne dépend pas du LLM et ne peut donc pas être oubliée ou reformulée (ADR-016)."""
    footer = (footer or "").strip()
    return f"{body.rstrip()}\n\n--\n{footer}" if footer else body


def drafts_frame(companies: list[Company], footer: str | None = None) -> pd.DataFrame:
    """Brouillons à RELIRE par un humain avant tout envoi."""
    rows = []
    for c in companies:
        if c.analysis is None:
            continue
        person = c.main_person()
        director = person.name if person else None
        rows.append(
            {
                "siren": c.siren,
                "name": c.name,
                "director": director,
                "score": c.score.total if c.score else None,
                "subject": c.analysis.email_subject,
                "body": with_footer(c.analysis.email_body, footer),
                "review_status": "À RELIRE - ne pas envoyer sans validation humaine",
            }
        )
    return pd.DataFrame(rows)


def load_campaign(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CAMPAIGN_COLS)
    return pd.read_csv(path, dtype=str).fillna("")


def init_campaign(companies: list[Company], campaign_id: str, path: Path) -> pd.DataFrame:
    """Ajoute les cibles ayant un brouillon au suivi (statut `draft`), sans écraser l'existant."""
    df = load_campaign(path)
    known = set(df["siren"])
    new = [
        {
            "siren": c.siren,
            "campaign_id": campaign_id,
            "status": "draft",
            "sent_date": "",
            "replied_date": "",
            "meeting_date": "",
            "updated_date": date.today().isoformat(),
            "note": "",
        }
        for c in companies
        if c.analysis is not None and c.siren not in known
    ]
    df = pd.concat([df, pd.DataFrame(new, columns=CAMPAIGN_COLS)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def update_status(
    path: Path, siren: str, status: str, on: date | None = None, note: str = ""
) -> None:
    """Met à jour le statut d'une cible (saisie manuelle après envoi/réponse)."""
    if status not in STATUSES:
        raise ValueError(f"Statut inconnu : {status} (attendu : {', '.join(STATUSES)})")
    df = load_campaign(path)
    mask = df["siren"] == siren
    if not mask.any():
        raise KeyError(f"SIREN {siren} absent du suivi de campagne")
    day = (on or date.today()).isoformat()
    df.loc[mask, "status"] = status
    df.loc[mask, "updated_date"] = day
    if status in _DATE_FIELD:
        df.loc[mask, _DATE_FIELD[status]] = day
    if note:
        df.loc[mask, "note"] = note
    df.to_csv(path, index=False)
