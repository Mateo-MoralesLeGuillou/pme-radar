"""Client HTTP partagé : limitation de débit, retries exponentiels, cache disque.

Le cache garantit qu'une même requête n'est jamais rappelée (reproductibilité + politesse API).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


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
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
        ua = os.getenv("PME_RADAR_USER_AGENT", "pme-radar/0.1 (projet open source)")
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": ua})
        self.calls = 0  # appels réseau réels (hors cache)

    def _cache_path(self, url: str, params: dict[str, Any] | None) -> Path:
        key = json.dumps([url, sorted((params or {}).items())], default=str)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

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
        if resp.status_code in (429, 302) or resp.status_code >= 500:  # 302 = page « sorry » (quota)
            raise RetryableStatus(f"HTTP {resp.status_code} sur {url}")
        resp.raise_for_status()
        return resp.json()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._cache_path(url, params)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = self._fetch(url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


class FixtureFetcher:
    """Mode `--offline` : sert les fixtures JSON de `tests/fixtures/` (aucun accès réseau).

    Les filtres de requête sont ignorés ; seules la pagination et la recherche par SIREN
    (`q=<9 chiffres>`) sont simulées.
    """

    def __init__(self, fixtures_dir: str | Path = "tests/fixtures") -> None:
        self.dir = Path(fixtures_dir)

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
        if "opendatasoft" in url:
            return self._load("bodacc_records.json")
        raise ValueError(f"Aucune fixture pour {url}")
