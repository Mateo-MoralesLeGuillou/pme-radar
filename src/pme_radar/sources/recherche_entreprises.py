"""Source : API Recherche d'entreprises (data.gouv). Une requête par code NAF, pagination complète."""

from __future__ import annotations

from collections.abc import Callable, Iterator
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


def iter_search(fetcher: JsonFetcher, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Parcourt toutes les pages d'une recherche."""
    page = 1
    while page <= MAX_PAGES:
        data = fetcher.get_json(BASE_URL, {**params, "page": page})
        yield from data.get("results", [])
        if page >= int(data.get("total_pages", 1)):
            return
        page += 1


def fetch_companies(
    fetcher: JsonFetcher,
    thesis: dict[str, Any],
    on_progress: Callable[[str, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Retourne les résultats bruts dédupliqués par SIREN, pour tous les NAF de la thèse.

    `on_progress(naf, n)` est appelé après chaque code NAF (n = résultats de ce code).
    """
    seen: dict[str, dict[str, Any]] = {}
    for naf in thesis["naf_codes"]:
        n = 0
        for item in iter_search(fetcher, build_params(naf["code"], thesis)):
            seen.setdefault(item["siren"], item)
            n += 1
        if on_progress:
            on_progress(naf["code"], n)
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


def fetch_company_by_siren(fetcher: JsonFetcher, siren: str) -> dict[str, Any] | None:
    """Fiche d'une société via `q=<SIREN>` (l'API accepte un SIREN comme terme de recherche).

    Retourne None si la société n'est pas trouvée (ou si l'API renvoie un autre SIREN).
    """
    data = fetcher.get_json(BASE_URL, {"q": siren, "per_page": 1})
    for item in data.get("results", []):
        if item.get("siren") == siren:
            return item
    return None
