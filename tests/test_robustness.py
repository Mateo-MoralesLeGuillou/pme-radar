"""Tests des correctifs de l'audit (cache, config, données aberrantes, IA, conformité, DNS)."""

import copy
import json
import os
import time
from datetime import date

import httpx
import pytest
from typer.testing import CliRunner

from pme_radar import outreach
from pme_radar.cli import app
from pme_radar.config import ConfigError, resolve, validate_scoring, validate_thesis
from pme_radar.deliverability import check_dmarc, check_spf
from pme_radar.enrich import company_age, director_age, normalize, parse_director
from pme_radar.export import export_sheets, targets_frame
from pme_radar.llm.analysis import analyze_top
from pme_radar.llm.base import LLMProvider
from pme_radar.llm.mock_provider import MockLLM
from pme_radar.llm.prompts import parse_analysis
from pme_radar.scoring import score_all
from pme_radar.sources._http import CachedClient, ttl_from_env

from .conftest import AS_OF, ROOT, raw_company
from .test_campaign import FakeResolver


# ---------------------------------------------------------------- cache
def _client(tmp_path, counter, **kw):
    def handler(req):
        counter.append(1)
        return httpx.Response(200, json={"n": len(counter)})

    return CachedClient(
        tmp_path, min_interval=0, client=httpx.Client(transport=httpx.MockTransport(handler)), **kw
    )


def test_cache_expires_after_ttl(tmp_path):
    calls = []
    c = _client(tmp_path, calls, ttl_seconds=60)
    assert c.get_json("https://x.test/a") == {"n": 1}
    assert c.get_json("https://x.test/a") == {"n": 1} and c.cache_hits == 1
    f = next(tmp_path.glob("*.json"))
    old = time.time() - 120
    os.utime(f, (old, old))  # fichier vieux de 2 min > TTL de 60 s
    assert c.get_json("https://x.test/a") == {"n": 2}


def test_cache_without_ttl_never_expires(tmp_path):
    calls = []
    c = _client(tmp_path, calls, ttl_seconds=None)
    c.get_json("https://x.test/a")
    f = next(tmp_path.glob("*.json"))
    os.utime(f, (0, 0))
    c.get_json("https://x.test/a")
    assert len(calls) == 1


def test_refresh_bypasses_cache_and_rewrites_it(tmp_path):
    calls = []
    _client(tmp_path, calls).get_json("https://x.test/a")
    assert _client(tmp_path, calls, refresh=True).get_json("https://x.test/a") == {"n": 2}
    assert _client(tmp_path, calls).get_json("https://x.test/a") == {"n": 2}  # cache réécrit


def test_corrupted_cache_file_is_refetched(tmp_path):
    calls = []
    c = _client(tmp_path, calls)
    c.get_json("https://x.test/a")
    next(tmp_path.glob("*.json")).write_text("{tronqué", encoding="utf-8")
    assert c.get_json("https://x.test/a") == {"n": 2}
    assert not list(tmp_path.glob("*.tmp"))  # écriture atomique : aucun résidu


def test_ttl_from_env(monkeypatch):
    monkeypatch.setenv("PME_RADAR_CACHE_TTL_DAYS", "2")
    assert ttl_from_env() == 2 * 86400
    monkeypatch.setenv("PME_RADAR_CACHE_TTL_DAYS", "0")
    assert ttl_from_env() is None
    monkeypatch.delenv("PME_RADAR_CACHE_TTL_DAYS")
    assert ttl_from_env() < 7 * 86400  # un run hebdomadaire repart toujours de données fraîches


# ---------------------------------------------------------------- configuration
def test_shipped_configs_are_valid(thesis, scoring_cfg):
    validate_thesis(thesis)
    validate_scoring(scoring_cfg)


def test_scoring_total_must_be_100(scoring_cfg):
    bad = copy.deepcopy(scoring_cfg)
    bad["criteria"]["revenue"]["max_points"] = 20
    with pytest.raises(ConfigError, match="105"):
        validate_scoring(bad)


def test_scoring_reports_all_problems(scoring_cfg):
    bad = copy.deepcopy(scoring_cfg)
    del bad["criteria"]["director_age"]["bands"][0]["points"]
    bad["penalties"]["corporate_director"] = 10
    bad["qualified_threshold"] = 150
    msg = str(pytest.raises(ConfigError, validate_scoring, bad).value)
    assert "points" in msg and "penalties.corporate_director" in msg and "entre 0 et 100" in msg


def test_thesis_validation(thesis):
    bad = copy.deepcopy(thesis)
    bad["naf_codes"].append({"code": "4321A", "label": "x", "tier": "core"})
    bad["naf_codes"].append(dict(bad["naf_codes"][0]))
    bad["naf_codes"][1]["tier"] = "prioritaire"
    bad["headcount_bands"] = ["99"]
    bad["valuation"] = {"ebe_multiple_low": 6, "ebe_multiple_high": 4}
    msg = str(pytest.raises(ConfigError, validate_thesis, bad).value)
    for needle in ("4321A", "en double", "tier", "headcount_bands", "valuation"):
        assert needle in msg


def test_resolve_falls_back_to_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve("config/thesis.yaml") == ROOT / "config" / "thesis.yaml"
    assert resolve("absent.yaml").name == "absent.yaml"


def test_cli_invalid_config_fails_cleanly(tmp_path, scoring_cfg):
    import yaml

    bad = copy.deepcopy(scoring_cfg)
    bad["criteria"]["revenue"]["max_points"] = 1
    p = tmp_path / "scoring.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    r = CliRunner().invoke(app, ["check-config", "--scoring", str(p)])
    assert r.exit_code == 1 and "100 attendu" in r.output
    r = CliRunner().invoke(app, ["check-config"])
    assert r.exit_code == 0 and "Configuration valide" in r.output


# ---------------------------------------------------------------- données aberrantes
@pytest.mark.parametrize("birth,expected", [("1900-01", None), ("2015-01", None), ("1960-01", 66)])
def test_implausible_director_age_is_missing(birth, expected):
    d = parse_director({"type_dirigeant": "personne physique", "date_de_naissance": birth})
    assert director_age(d, AS_OF) == expected


def test_company_age_exact_and_future_dates():
    assert company_age(date(2016, 11, 5), AS_OF) == 9  # anniversaire pas encore atteint
    assert company_age(date(2016, 11, 4), AS_OF) == 10
    assert company_age(date(2027, 1, 1), AS_OF) is None


def test_ratios_sorted_and_bad_dates_ignored():
    rows = [
        {
            "date_cloture_exercice": "2023-12-31",
            "chiffre_d_affaires": 1e6,
            "ebe": 1e5,
            "confidentiality": "Public",
        },
        {
            "date_cloture_exercice": None,
            "chiffre_d_affaires": 9e6,
            "ebe": 9e5,
            "confidentiality": "Public",
        },
        {
            "date_cloture_exercice": "2025-12-31",
            "chiffre_d_affaires": 2e6,
            "ebe": 4e5,
            "confidentiality": "Public",
        },
    ]  # ordre volontairement mélangé + une date absente
    c = normalize(raw_company(finances={}), AS_OF, ratios=rows)
    assert c.ebe_year == 2025 and c.ebe_margin == 0.2


# ---------------------------------------------------------------- couche IA
class Boom(LLMProvider):
    name = "boom"

    def complete(self, system, user):
        raise ConnectionError("quota dépassé")


def _scored(scoring_cfg, thesis, n=3):
    cs = [normalize(raw_company(siren=f"99900000{i}"), AS_OF) for i in range(n)]
    return score_all(cs, scoring_cfg, thesis)


def test_one_failure_does_not_stop_the_batch(scoring_cfg, thesis):
    class SecondCallFails(MockLLM):
        def __init__(self):
            self.calls = 0

        def complete(self, system, user):
            self.calls += 1
            if self.calls == 2:  # la 2e cible échoue (erreur réseau, non retentée)
                raise ConnectionError("quota dépassé")
            return super().complete(system, user)

    cs = _scored(scoring_cfg, thesis)
    report = analyze_top(cs, SecondCallFails(), top_n=3)
    assert report.generated == 2 and len(report.failed) == 1
    assert "quota" in next(iter(report.failed.values()))
    assert sum(c.analysis is not None for c in cs) == 2
    report = analyze_top(_scored(scoring_cfg, thesis), Boom(), top_n=3)
    assert report.generated == 0 and len(report.failed) == 3


def test_unchanged_facts_reuse_previous_analysis(scoring_cfg, thesis):
    first = _scored(scoring_cfg, thesis, 1)
    analyze_top(first, MockLLM(), top_n=1)
    previous = {first[0].siren: first[0].analysis}

    class Counting(MockLLM):
        calls = 0

        def complete(self, system, user):
            Counting.calls += 1
            return super().complete(system, user)

    again = _scored(scoring_cfg, thesis, 1)
    r = analyze_top(again, Counting(), top_n=1, previous=previous)
    assert (r.reused, r.generated, Counting.calls) == (1, 0, 0)
    changed = _scored(scoring_cfg, thesis, 1)
    changed[0].revenue_last = 7_000_000  # un fait transmis change -> nouvel appel
    r = analyze_top(changed, Counting(), top_n=1, previous=previous)
    assert (r.reused, r.generated, Counting.calls) == (0, 1, 1)


def test_forbidden_words_match_whole_words_only():
    def payload(body):
        return json.dumps(
            {
                "mini_thesis": ["a", "b", "c"],
                "red_flags": [],
                "email_subject": "s",
                "email_body": body,
            }
        )

    assert parse_analysis(payload("Je ne peux rien garantir à ce stade."), "x")
    for body in ("Résultat garanti.", "Une offre garantie.", "C'est une demande urgente."):
        with pytest.raises(ValueError):
            parse_analysis(payload(body), "x")


def test_cli_draft_exits_1_when_every_analysis_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    data = str(tmp_path / "data")
    runner = CliRunner()
    for step in (["source", "--offline"], ["enrich", "--offline"], ["score"]):
        assert runner.invoke(app, [*step, "--data-dir", data]).exit_code == 0
    monkeypatch.setattr("pme_radar.cli.get_provider", lambda name: Boom())
    r = runner.invoke(app, ["draft", "--data-dir", data])
    assert r.exit_code == 1 and "Aucune analyse produite" in r.output


# ---------------------------------------------------------------- conformité des brouillons
def test_compliance_footer_is_appended_to_every_draft(scoring_cfg, thesis):
    cs = _scored(scoring_cfg, thesis, 2)
    analyze_top(cs, MockLLM(), top_n=2)
    df = outreach.drafts_frame(cs, footer="Données publiques. Opposition : répondez simplement.")
    assert len(df) == 2 and all(b.endswith("Opposition : répondez simplement.") for b in df.body)
    assert outreach.drafts_frame(cs).body.iloc[0] == cs[0].analysis.email_body  # sans footer


def test_shipped_footer_mentions_source_and_opposition():
    from pme_radar.config import load_yaml

    footer = load_yaml("config/campaign.yaml")["compliance_footer"].lower()
    assert "sources publiques" in footer and "recontacté" in footer


# ---------------------------------------------------------------- délivrabilité
def test_spf_redirect_is_valid():
    r = FakeResolver(txt={"a.fr": ["v=spf1 redirect=_spf.provider.com"]})
    assert check_spf(r, "a.fr").status == "ok"


def test_spf_all_qualifier_anywhere_and_whitespace():
    r = FakeResolver(txt={"a.fr": ["  v=spf1 -all include:x  "]})
    assert check_spf(r, "a.fr").status == "ok"
    assert check_spf(FakeResolver(txt={"a.fr": ["v=spf1 all"]}), "a.fr").status == "fail"


def test_multiple_dmarc_records_fail_and_tags_case_insensitive():
    two = FakeResolver(txt={"_dmarc.a.fr": ["v=DMARC1; p=reject", "v=DMARC1; p=none"]})
    assert check_dmarc(two, "a.fr").status == "fail"
    upper = FakeResolver(txt={"_dmarc.a.fr": ["v=DMARC1; P=reject; RUA=mailto:d@a.fr"]})
    assert check_dmarc(upper, "a.fr").status == "ok"


# ---------------------------------------------------------------- export Sheets
def test_sheets_auth_errors_are_not_swallowed():
    class Denied:
        def worksheet(self, name):
            raise PermissionError("403 : classeur non partagé avec le compte de service")

        def add_worksheet(self, **kw):  # pragma: no cover
            raise AssertionError("ne doit pas créer d'onglet sur une erreur d'accès")

    t = targets_frame([normalize(raw_company(), AS_OF)])
    with pytest.raises(PermissionError):
        export_sheets(Denied(), {"Identified": t})


# ---------------------------------------------------------------- CLI
def test_version_and_track_with_date(tmp_path):
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0 and "pme-radar" in r.output
    camp = tmp_path / "out" / "campaign.csv"
    camp.parent.mkdir(parents=True)
    camp.write_text(
        "siren,campaign_id,status,sent_date,replied_date,meeting_date,updated_date,"
        "note\n123456789,c1,draft,,,,,\n",
        encoding="utf-8",
    )
    ok = CliRunner().invoke(
        app,
        ["track", "123456789", "contacted", "--date", "2026-10-01", "--data-dir", str(tmp_path)],
    )
    assert ok.exit_code == 0 and "2026-10-01" in camp.read_text()
    bad = CliRunner().invoke(app, ["track", "123456789", "sent", "--data-dir", str(tmp_path)])
    assert bad.exit_code == 1 and "Statut inconnu" in bad.output
