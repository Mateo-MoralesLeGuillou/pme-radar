"""Source : API Recherche d'entreprises (data.gouv). Une requête par code NAF, pagination complète."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ._http import JsonFetcher

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25  # maximum documenté par l'API
MAX_PAGES = 400  # garde-fou : l'API plafonne à 10 000 résultats par requête


def build_params(naf: str, thesis: dict[str, Any]) -> dict[str, Any]:
    """Traduit la thèse en paramètres de l'API (noms à vérifier au 1er run réel, cf. PLAN.md)."""
    return {
        "activite_principale": naf,
        "tranche_effectif_salarie": ",".join(thesis["headcount_bands"]),
        "departement": ",".join(thesis["departments"]),
        "etat_administratif": thesis.get("administrative_status", "A"),
        "categorie_entreprise": ",".join(thesis.get("categories", ["PME"])),
        "per_page": PER_PAGE,
    }


def iter_search(fetcher: JsonFetcher, params: dict[str, Any]):
    """Parcourt toutes les pages d'une recherche."""
    page = 1
    while page <= MAX_PAGES:
        data = fetcher.get_json(BASE_URL, {**params, "page": page})
        yield from data.get("results", [])
        if page >= int(data.get("total_pages", 1)):
            return
        page += 1


def fetch_companies(fetcher: JsonFetcher, thesis: dict[str, Any]) -> list[dict[str, Any]]:
    """Retourne les résultats bruts dédupliqués par SIREN, pour tous les NAF de la thèse."""
    seen: dict[str, dict[str, Any]] = {}
    for naf in thesis["naf_codes"]:
        for item in iter_search(fetcher, build_params(naf["code"], thesis)):
            seen.setdefault(item["siren"], item)
    return list(seen.values())


def save_raw(results: list[dict[str, Any]], path: Path) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "siren": [r["siren"] for r in results],
            "payload": [json.dumps(r, ensure_ascii=False) for r in results],
        }
    )
    df.to_parquet(path, index=False)


def load_raw(path: Path) -> list[dict[str, Any]]:
    import json

    return [json.loads(p) for p in pd.read_parquet(path)["payload"]]
