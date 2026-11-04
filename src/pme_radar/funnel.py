"""Métriques d'entonnoir et seuils d'alerte de campagne."""

from __future__ import annotations

from typing import Any

import pandas as pd

SENT_STATUSES = {"contacted", "replied", "meeting", "declined", "bounced"}
REPLIED_STATUSES = {"replied", "meeting", "declined"}  # un refus est une réponse


def funnel_counts(targets: pd.DataFrame, campaign: pd.DataFrame | None) -> pd.DataFrame:
    """Entonnoir identifiées → qualifiées → contactées → RDV, avec taux de conversion."""
    camp = campaign if campaign is not None else pd.DataFrame(columns=["siren", "status"])
    steps = [
        ("Identifiées", len(targets)),
        ("Qualifiées", int((targets["stage"] == "qualified").sum())),
        ("Contactées", int(camp["status"].isin(SENT_STATUSES).sum())),
        ("Ont répondu", int(camp["status"].isin(REPLIED_STATUSES).sum())),
        ("RDV", int((camp["status"] == "meeting").sum())),
    ]
    df = pd.DataFrame(steps, columns=["étape", "nombre"])
    prev = df["nombre"].shift(1)
    df["conversion_vs_précédente"] = (df["nombre"] / prev).where(prev > 0)
    df["conversion_vs_identifiées"] = df["nombre"] / df["nombre"].iloc[0] if steps[0][1] else None
    return df


def campaign_metrics(campaign: pd.DataFrame, thresholds: dict[str, Any]) -> pd.DataFrame:
    """Taux par campagne. Réponse et RDV sont rapportés aux emails délivrés (envoyés - rebonds)."""
    cols = ["campaign_id", "sent", "bounced", "bounce_rate", "reply_rate", "meeting_rate", "alerts"]
    if campaign is None or campaign.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for cid, g in campaign.groupby("campaign_id"):
        sent = int(g["status"].isin(SENT_STATUSES).sum())
        bounced = int((g["status"] == "bounced").sum())
        delivered = sent - bounced
        replied = int(g["status"].isin(REPLIED_STATUSES).sum())
        meetings = int((g["status"] == "meeting").sum())
        bounce = bounced / sent if sent else None
        reply = replied / delivered if delivered > 0 else None
        meet = meetings / delivered if delivered > 0 else None
        rows.append(
            {
                "campaign_id": cid,
                "sent": sent,
                "bounced": bounced,
                "bounce_rate": bounce,
                "reply_rate": reply,
                "meeting_rate": meet,
                "alerts": "; ".join(alerts(sent, bounce, reply, meet, thresholds)),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def alerts(
    sent: int, bounce: float | None, reply: float | None, meet: float | None, t: dict[str, Any]
) -> list[str]:
    if sent < t.get("min_sample", 20):
        return [f"échantillon insuffisant ({sent} envois) : taux non jugés"]
    out = []
    if bounce is not None:
        if bounce >= t["bounce_rate"]["critical"]:
            out.append(f"CRITIQUE rebonds {bounce:.1%} : stopper l'envoi, nettoyer la liste")
        elif bounce >= t["bounce_rate"]["warning"]:
            out.append(f"rebonds {bounce:.1%} au-dessus du seuil d'alerte")
    if reply is not None and reply < t["reply_rate"]["warning_below"]:
        out.append(f"taux de réponse {reply:.1%} faible : revoir ciblage ou message")
    if meet is not None and meet < t["meeting_rate"]["warning_below"]:
        out.append(f"taux de RDV {meet:.1%} faible")
    return out
