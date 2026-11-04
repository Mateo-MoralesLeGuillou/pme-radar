"""Source : BODACC (Opendatasoft v2.1). Détecte les procédures collectives par SIREN."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ._http import JsonFetcher

URL = (
    "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "annonces-commerciales/records"
)
BATCH = 20  # SIREN par requête (clause `where` OR)


def _fmt(siren: str) -> str:
    return f"{siren[:3]} {siren[3:6]} {siren[6:]}"  # format du champ `registre`


def _norm(registre_item: str) -> str:
    return registre_item.replace(" ", "")


def collective_procedure_sirens(fetcher: JsonFetcher, sirens: Iterable[str]) -> set[str]:
    """SIREN ayant au moins une annonce de famille « collective » (redressement, liquidation…)."""
    wanted = list(dict.fromkeys(sirens))
    found: set[str] = set()
    for i in range(0, len(wanted), BATCH):
        chunk = wanted[i : i + BATCH]
        clause = " or ".join(f'registre:"{_fmt(s)}"' for s in chunk)
        params: dict[str, Any] = {
            "where": f'familleavis="collective" and ({clause})',
            "select": "registre,typeavis,dateparution",
            "limit": 100,
        }
        data = fetcher.get_json(URL, params)
        for rec in data.get("results", []):
            for reg in rec.get("registre") or []:
                if _norm(reg) in chunk:
                    found.add(_norm(reg))
    return found
