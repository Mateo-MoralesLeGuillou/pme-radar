import json

import pytest

from pme_radar.enrich import normalize
from pme_radar.llm.analysis import analyze_company, analyze_top, get_provider
from pme_radar.llm.base import LLMProvider
from pme_radar.llm.mock_provider import MockLLM
from pme_radar.llm.prompts import build_user_prompt, parse_analysis
from pme_radar.models import Stage
from pme_radar.scoring import score_all

from .conftest import AS_OF, raw_company


def company(scoring_cfg, thesis, **over):
    c = normalize(raw_company(**over), AS_OF)
    return score_all([c], scoring_cfg, thesis)[0]


def test_mock_is_deterministic_and_valid(scoring_cfg, thesis):
    c = company(scoring_cfg, thesis)
    p = MockLLM()
    a = analyze_company(c, p).analysis
    b = analyze_company(company(scoring_cfg, thesis), p).analysis
    assert a == b and len(a.mini_thesis) == 3 and a.provider == "mock" and a.prompt_version == "v1"
    assert "parfaitement" in a.email_body  # le refus est explicitement entendable
    assert "6,0 M€" in a.mini_thesis[1]


def test_llm_never_changes_score(scoring_cfg, thesis):
    c = company(scoring_cfg, thesis)
    before = c.score.model_copy(deep=True)
    analyze_company(c, MockLLM())
    assert c.score == before


def test_missing_accounts_flagged(scoring_cfg, thesis):
    a = analyze_company(company(scoring_cfg, thesis, finances={}), MockLLM()).analysis
    assert any("Comptes non publiés" in f for f in a.red_flags)


def _payload(**over):
    base = {"mini_thesis": ["a", "b", "c"], "red_flags": [], "email_subject": "s",
            "email_body": "Bonjour, un message respectueux."}
    base.update(over)
    return json.dumps(base)


def test_parse_accepts_json_with_surrounding_text():
    assert parse_analysis("Voici :\n" + _payload() + "\nFin", "x").email_subject == "s"


@pytest.mark.parametrize("raw", [
    "pas de json", "{not json}", _payload(mini_thesis=["a", "b"]),
    _payload(email_body="Offre garantie, répondez c'est urgent"), _payload(email_body="mot " * 250),
    json.dumps({"mini_thesis": ["a", "b", "c"]}),
])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_analysis(raw, "x")


class Flaky(LLMProvider):
    name = "flaky"

    def __init__(self):
        self.n = 0

    def complete(self, system, user):
        self.n += 1
        return "garbage" if self.n == 1 else _payload()


def test_retry_once_on_invalid_output(scoring_cfg, thesis):
    p = Flaky()
    analyze_company(company(scoring_cfg, thesis), p)
    assert p.n == 2


def test_gives_up_after_retry(scoring_cfg, thesis):
    class Bad(Flaky):
        def complete(self, s, u):
            return "garbage"

    with pytest.raises(ValueError):
        analyze_company(company(scoring_cfg, thesis), Bad())


def test_top_n_only_qualified(scoring_cfg, thesis):
    cs = [company(scoring_cfg, thesis, siren=f"99900000{i}") for i in range(3)]
    cs[2].stage = Stage.IDENTIFIED
    cs[0].score.total, cs[1].score.total = 90, 95
    analyze_top(cs, MockLLM(), top_n=1)
    assert [c.analysis is not None for c in cs] == [False, True, False]


def test_prompt_contains_minimized_facts_only(scoring_cfg, thesis):
    prompt = build_user_prompt(company(scoring_cfg, thesis))
    assert "<facts>" in prompt and "999000001" not in prompt  # pas de SIREN envoyé au LLM


def test_provider_factory():
    assert get_provider("mock").name == "mock"
    with pytest.raises(ValueError):
        get_provider("nope")


def test_anthropic_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_provider("anthropic")
