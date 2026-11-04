"""Export : CSV toujours, Google Sheets si identifiants présents (optionnel)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .funnel import SENT_STATUSES, funnel_counts
from .models import Company


def company_row(c: Company) -> dict[str, Any]:
    a, s = c.analysis, c.score
    return {
        "siren": c.siren,
        "name": c.name,
        "naf_code": c.naf_code,
        "naf_label": c.naf_label,
        "city": c.city,
        "department": c.department,
        "headcount_band": c.headcount_band,
        "company_age_years": c.company_age_years,
        "director_age": c.director_age,
        "is_owner_operator": c.is_owner_operator,
        "revenue_last": c.revenue_last,
        "net_income_last": c.net_income_last,
        "net_margin": c.net_margin,
        "ebe": c.ebe,
        "ebe_margin": c.ebe_margin,
        "debt_ratio": c.debt_ratio,
        "revenue_cagr": c.revenue_cagr,
        "accounts_available": c.accounts_available,
        "has_collective_procedure": c.has_collective_procedure,
        "stage": c.stage.value,
        "score": s.total if s else None,
        "score_ceiling": s.ceiling if s else None,
        "confidence": s.confidence if s else None,
        "to_document": s.to_document if s else None,
        "score_summary": s.summary if s else None,
        "score_detail": json.dumps(
            [
                {"critère": x.label, "points": x.points, "max": x.max_points, "détail": x.detail}
                for x in (s.criteria + s.penalties)
            ],
            ensure_ascii=False,
        )
        if s
        else None,
        "mini_thesis": " | ".join(a.mini_thesis) if a else None,
        "red_flags": " | ".join(a.red_flags) if a else None,
        "email_subject": a.email_subject if a else None,
    }


def targets_frame(
    companies: list[Company],
    scoring_cfg: dict[str, Any] | None = None,
    thesis: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Une ligne par société. Avec les configurations : recommandation, signaux factuels,
    valeur indicative et fonds propres à réunir (rapport de deal flow, ADR-020)."""
    df = pd.DataFrame([company_row(c) for c in companies])
    if scoring_cfg is None or thesis is None or df.empty:
        return df
    from .report import evaluate  # import local : évite un cycle export -> report -> outreach

    extra = {
        d.company.siren: {
            "recommendation": d.rec.label,
            "signals": " | ".join(f"{s.level} : {s.title}" for s in d.signals),
            "ev_low": d.plan.ev_low if d.plan else None,
            "ev_high": d.plan.ev_high if d.plan else None,
            "equity_needed": d.plan.equity if d.plan else None,
        }
        for d in evaluate(companies, scoring_cfg, thesis)
    }
    cols = ["recommendation", "signals", "ev_low", "ev_high", "equity_needed"]
    for col in cols:
        df[col] = df["siren"].map(lambda s, col=col: extra.get(s, {}).get(col))
    return df


def build_tabs(targets: pd.DataFrame, campaign: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Un onglet par étape + « Funnel »."""
    camp = (
        campaign
        if campaign is not None
        else pd.DataFrame(columns=["siren", "campaign_id", "status", "sent_date"])
    )
    join = targets.merge(
        camp[["siren", "campaign_id", "status", "sent_date"]],
        on="siren",
        how="inner",
        suffixes=("", "_campaign"),
    )
    return {
        "Identified": targets,
        "Qualified": targets[targets["stage"] == "qualified"],
        "Contacted": join[join["status"].isin(SENT_STATUSES)],
        "Meeting": join[join["status"] == "meeting"],
        "Funnel": funnel_counts(targets, camp),
    }


def export_csv(tabs: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in tabs.items():
        p = out_dir / f"{name.lower()}.csv"
        df.to_csv(p, index=False)
        paths.append(p)
    return paths


def sheets_configured() -> bool:
    return bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.getenv("GOOGLE_SHEET_ID"))


def _worksheet_not_found() -> tuple[type[Exception], ...]:
    """Exception « onglet absent » : seule celle-ci déclenche la création d'un onglet (une erreur
    d'authentification ou de quota doit remonter telle quelle)."""
    try:
        from gspread.exceptions import WorksheetNotFound

        return (WorksheetNotFound, KeyError)
    except ImportError:  # gspread non installé (tests avec un faux classeur)
        return (KeyError,)


def export_sheets(spreadsheet: Any, tabs: dict[str, pd.DataFrame]) -> None:
    """Écrit un onglet par DataFrame (créé s'il n'existe pas, vidé sinon)."""
    not_found = _worksheet_not_found()
    for name, df in tabs.items():
        try:
            ws = spreadsheet.worksheet(name)
            ws.clear()
        except not_found:
            ws = spreadsheet.add_worksheet(
                title=name, rows=max(len(df) + 1, 10), cols=max(len(df.columns), 5)
            )
        clean = df.astype(object).where(df.notna(), "")
        ws.update([list(map(str, df.columns))] + clean.values.tolist())


def open_spreadsheet() -> Any:  # pragma: no cover (réseau)
    import gspread

    gc = gspread.service_account(filename=os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    return gc.open_by_key(os.environ["GOOGLE_SHEET_ID"])
