"""Client HTTP partagé : limitation de débit, retries exponentiels, cache disque.

Le cache évite de rappeler une même requête pendant sa durée de validité (reproductibilité +
politesse API). Il expire (défaut 6 jours, `PME_RADAR_CACHE_TTL_DAYS`) pour qu'un run hebdomadaire
voie les nouvelles entreprises et les nouvelles procédures BODACC (ADR-014).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

DEFAULT_TTL_DAYS = 6.0  # < 7 : le run hebdomadaire repart toujours de données fraîches


def ttl_from_env() -> float | None:
    """Durée de validité du cache en secondes ; `0` ou négatif = cache sans expiration."""
    days = float(os.getenv("PME_RADAR_CACHE_TTL_DAYS", DEFAULT_TTL_DAYS))
    return days * 86400 if days > 0 else None


class JsonFetcher(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...


class RetryableStatus(Exception):
    """Statut HTTP qui justifie un nouvel essai (429, 5xx)."""


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, RetryableStatus | httpx.TransportError)


class CachedClient:
    """GET JSON avec débit maximal (`min_interval` s entre deux appels), retry et cache disque."""

    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        min_interval: float = 0.5,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        ttl_seconds: float | None = DEFAULT_TTL_DAYS * 86400,
        refresh: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds  # None = jamais expiré
        self.refresh = refresh  # True = ignorer le cache existant (mais le réécrire)
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
        ua = os.getenv("PME_RADAR_USER_AGENT", "pme-radar/0.1 (projet open source)")
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": ua})
        self.calls = 0  # appels réseau réels (hors cache)
        self.cache_hits = 0

    def _cache_path(self, url: str, params: dict[str, Any] | None) -> Path:
        key = json.dumps([url, sorted((params or {}).items())], default=str)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _fresh(self, path: Path) -> bool:
        if self.ttl_seconds is None:
            return True
        return (time.time() - path.stat().st_mtime) < self.ttl_seconds

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def _fetch(self, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self._throttle()
        self.calls += 1
        resp = self._client.get(url, params=params)
        if (
            resp.status_code in (429, 302) or resp.status_code >= 500
        ):  # 302 = page « sorry » (quota)
            raise RetryableStatus(f"HTTP {resp.status_code} sur {url}")
        resp.raise_for_status()
        return resp.json()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._cache_path(url, params)
        if path.exists() and not self.refresh and self._fresh(path):
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                self.cache_hits += 1
                return cached
            except json.JSONDecodeError:  # fichier corrompu : on le refait
                pass
        data = self._fetch(url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # écriture atomique : un run interrompu ne laisse pas de JSON tronqué
        return data


class FixtureFetcher:
    """Mode `--offline` : sert les fixtures JSON de `tests/fixtures/` (aucun accès réseau).

    Les filtres de requête sont ignorés ; seules la pagination et la recherche par SIREN
    (`q=<9 chiffres>`) sont simulées.
    """

    def __init__(self, fixtures_dir: str | Path = "tests/fixtures") -> None:
        from ..config import resolve

        self.dir = resolve(fixtures_dir)

    def _load(self, name: str) -> Any:
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if "recherche-entreprises" in url:
            q = str(params.get("q", ""))
            if q.isdigit() and len(q) == 9:  # recherche d'une société par SIREN
                pool = self._load("recherche_entreprises_search.json")["results"]
                holdings = self.dir / "recherche_entreprises_holdings.json"
                if holdings.exists():
                    pool = pool + self._load(holdings.name)["results"]
                hits = [r for r in pool if r["siren"] == q]
                return {
                    "results": hits,
                    "total_results": len(hits),
                    "page": 1,
                    "per_page": 1,
                    "total_pages": 1,
                }
            data = self._load("recherche_entreprises_search.json")
            per_page = int(params.get("per_page", 25))
            page = int(params.get("page", 1))
            results = data["results"]
            start = (page - 1) * per_page
            return {
                "results": results[start : start + per_page],
                "total_results": len(results),
                "page": page,
                "per_page": per_page,
                "total_pages": -(-len(results) // per_page),
            }
        if "ratios_inpi_bce" in url:
            wanted = set(re.findall(r'"(\d{9})"', str(params.get("where", ""))))
            rows = [r for r in self._load("inpi_ratios.json")["results"] if r["siren"] in wanted]
            rows.sort(key=lambda r: r["date_cloture_exercice"], reverse=True)
            offset, limit = int(params.get("offset", 0)), int(params.get("limit", 100))
            return {"total_count": len(rows), "results": rows[offset : offset + limit]}
        if "opendatasoft" in url:
            return self._load("bodacc_records.json")
        raise ValueError(f"Aucune fixture pour {url}")
