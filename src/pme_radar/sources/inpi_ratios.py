"""Source : jeu « Ratios financiers BCE/INPI » (data.economie.gouv.fr, Opendatasoft v2.1).

Apporte EBE, endettement et un historique pluriannuel là où l'API Recherche d'entreprises ne
publie rien. Pour les bilans « partiellement confidentiels », le jeu masque CA et EBE en les mettant
à 0 : ces valeurs sont ignorées (ADR-005).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from ._http import JsonFetcher

URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/ratios_inpi_bce/records"
)
BATCH = 10  # SIREN par requête
LIMIT = 100  # maximum Opendatasoft par page
FIELDS = (
    "siren,date_cloture_exercice,chiffre_d_affaires,ebe,resultat_net,"
    "taux_d_endettement,confidentiality"
)


def fetch_ratios(fetcher: JsonFetcher, sirens: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """{siren: [lignes d'exercice, de la plus récente à la plus ancienne]}."""
    wanted = list(dict.fromkeys(sirens))
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i in range(0, len(wanted), BATCH):
        in_clause = ",".join(f'"{s}"' for s in wanted[i : i + BATCH])
        offset = 0
        while True:
            data = fetcher.get_json(
                URL,
                {
                    "where": f"siren IN ({in_clause})",
                    "select": FIELDS,
                    "order_by": "date_cloture_exercice desc",
                    "limit": LIMIT,
                    "offset": offset,
                },
            )
            rows = data.get("results", [])
            for r in rows:
                out[r["siren"]].append(r)
            offset += LIMIT
            if len(rows) < LIMIT:
                break
    return dict(out)


def usable(row: dict[str, Any]) -> bool:
    """Ligne publique avec un CA réel : seule base fiable pour CA et EBE."""
    return row.get("confidentiality") == "Public" and (row.get("chiffre_d_affaires") or 0) > 0
