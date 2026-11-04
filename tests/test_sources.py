import httpx
import pytest

from pme_radar.sources import bodacc
from pme_radar.sources._http import CachedClient, FixtureFetcher
from pme_radar.sources.recherche_entreprises import (
    build_params,
    fetch_companies,
    load_raw,
    save_raw,
)


def make_client(handler, tmp_path):
    return CachedClient(tmp_path, min_interval=0,
                        client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_cache_prevents_second_call(tmp_path):
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(200, json={"ok": 1})

    c = make_client(handler, tmp_path)
    assert c.get_json("https://x.test/a", {"q": 1}) == {"ok": 1}
    assert c.get_json("https://x.test/a", {"q": 1}) == {"ok": 1}
    assert n["c"] == 1
    c.get_json("https://x.test/a", {"q": 2})
    assert n["c"] == 2


def test_retry_on_429_then_success(tmp_path, monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda s: None)
    calls = iter([429, 503, 200])

    def handler(req):
        code = next(calls)
        return httpx.Response(code, json={"ok": 1})

    assert make_client(handler, tmp_path).get_json("https://x.test/a") == {"ok": 1}


def test_4xx_not_retried(tmp_path):
    c = make_client(lambda r: httpx.Response(404, json={}), tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        c.get_json("https://x.test/a")
    assert c.calls == 1


def test_full_pagination_and_dedup(tmp_path, thesis):
    thesis = {**thesis, "naf_codes": thesis["naf_codes"][:2]}

    def handler(req):
        page = int(req.url.params["page"])
        assert req.url.params["per_page"] == "25"
        assert req.url.params["activite_principale"] in ("33.12Z", "33.14Z")
        items = [{"siren": f"{page}{i:08d}"} for i in range(2)] + [{"siren": "dup"}]
        return httpx.Response(200, json={"results": items, "total_pages": 3, "page": page})

    res = fetch_companies(make_client(handler, tmp_path), thesis)
    assert len(res) == 3 * 2 + 1  # 6 SIREN uniques + le doublon "dup" compté une fois


def test_build_params_from_thesis(thesis):
    p = build_params("43.21A", thesis)
    assert p["tranche_effectif_salarie"] == "11,12,21,22,31"
    assert p["departement"].startswith("75,") and p["etat_administratif"] == "A"


def test_raw_roundtrip(tmp_path):
    save_raw([{"siren": "1", "x": "é"}], tmp_path / "r.parquet")
    assert load_raw(tmp_path / "r.parquet") == [{"siren": "1", "x": "é"}]


def test_bodacc_detects_registered_sirens(tmp_path):
    seen = {}

    def handler(req):
        seen["where"] = req.url.params["where"]
        return httpx.Response(200, json={"results": [
            {"registre": ["999 000 008"]}, {"registre": ["111 111 111"]}, {"registre": None}]})

    found = bodacc.collective_procedure_sirens(make_client(handler, tmp_path),
                                               ["999000008", "999000015"])
    assert found == {"999000008"}
    assert 'familleavis="collective"' in seen["where"] and "999 000 008" in seen["where"]


def test_bodacc_batches(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"results": []})

    bodacc.collective_procedure_sirens(make_client(handler, tmp_path),
                                       [f"{i:09d}" for i in range(45)])
    assert len(calls) == 3


def test_fixture_fetcher_paginates():
    f = FixtureFetcher("tests/fixtures")
    p1 = f.get_json("https://recherche-entreprises.api.gouv.fr/search", {"page": 1, "per_page": 25})
    p2 = f.get_json("https://recherche-entreprises.api.gouv.fr/search", {"page": 2, "per_page": 25})
    assert p1["total_pages"] == 2 and len(p1["results"]) == 25 and len(p2["results"]) == 20
    with pytest.raises(ValueError):
        f.get_json("https://unknown.test")
