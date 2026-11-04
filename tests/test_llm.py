import json

import pytest

from pme_radar.enrich import normalize
from pme_radar.llm.analysis import analyze_company, analyze_top, get_provider
from pme_radar.llm.base import LLMProvider
from pme_radar.llm.mock_provider import MockLLM
from pme_radar.llm.prompts import PROMPT_VERSION, build_user_prompt, company_facts, parse_analysis
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
    assert a == b and len(a.mini_thesis) == 3 and a.provider == "mock"
    assert a.prompt_version == PROMPT_VERSION
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
    base = {
        "mini_thesis": ["a", "b", "c"],
        "red_flags": [],
        "email_subject": "s",
        "email_body": "Bonjour, un message respectueux.",
    }
    base.update(over)
    return json.dumps(base)


def test_parse_accepts_json_with_surrounding_text():
    assert parse_analysis("Voici :\n" + _payload() + "\nFin", "x").email_subject == "s"


@pytest.mark.parametrize(
    "raw",
    [
        "pas de json",
        "{not json}",
        _payload(mini_thesis=["a", "b"]),
        _payload(email_body="Offre garantie, répondez c'est urgent"),
        _payload(email_body="mot " * 250),
        json.dumps({"mini_thesis": ["a", "b", "c"]}),
    ],
)
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


def _no_credentials(monkeypatch, tmp_path):
    from pme_radar.llm import anthropic_provider as ap

    for name in ap.CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ap.Path, "home", lambda: tmp_path)  # aucun profil `ant auth login`


def test_anthropic_requires_credentials(monkeypatch, tmp_path):
    _no_credentials(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="ant auth login"):
        get_provider("anthropic")


def test_anthropic_accepts_cli_profile(monkeypatch, tmp_path):
    from pme_radar.llm import anthropic_provider as ap

    _no_credentials(monkeypatch, tmp_path)
    (tmp_path / ".config" / "anthropic").mkdir(parents=True)
    assert ap.has_credentials()


class FakeMessages:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def _fake_client(stop_reason="end_turn", text="{}", category=None):
    from types import SimpleNamespace as NS

    reply = NS(
        stop_reason=stop_reason,
        stop_details=NS(category=category) if category else None,
        content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
    )
    return NS(beta=NS(messages=FakeMessages(reply)))


def test_anthropic_request_shape_and_text_extraction(monkeypatch):
    from pme_radar.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider

    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_FALLBACKS", raising=False)
    client = _fake_client(text='{"ok": 1}')
    p = AnthropicProvider(client=client)
    assert p.complete("sys", "user") == '{"ok": 1}'  # blocs thinking ignorés
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["max_tokens"] >= 16000
    assert call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]


def test_anthropic_fallbacks_only_where_supported(monkeypatch):
    from pme_radar.llm.anthropic_provider import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-5-5")  # pas de repli serveur
    assert "fallbacks" not in AnthropicProvider(client=_fake_client()).request("s", "u")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_FALLBACKS", "off")
    assert "fallbacks" not in AnthropicProvider(client=_fake_client()).request("s", "u")


def test_anthropic_refusal_is_not_retried(scoring_cfg, thesis):
    from pme_radar.llm.anthropic_provider import AnthropicProvider, LLMRefusal

    client = _fake_client(stop_reason="refusal", text="", category="general_harms")
    p = AnthropicProvider(client=client)
    with pytest.raises(LLMRefusal, match="general_harms"):
        p.complete("s", "u")
    report = analyze_top([company(scoring_cfg, thesis)], p, top_n=1)
    assert "refus du modèle" in next(iter(report.failed.values()))
    assert len(client.beta.messages.calls) == 2  # 1 appel direct + 1 dans le lot, sans retry


def test_anthropic_truncated_answer_is_explicit():
    from pme_radar.llm.anthropic_provider import AnthropicProvider

    p = AnthropicProvider(client=_fake_client(stop_reason="max_tokens", text='{"mini'))
    with pytest.raises(RuntimeError, match="tronquée"):
        p.complete("s", "u")


def test_factual_signals_reach_the_model(scoring_cfg, thesis):
    c = company(scoring_cfg, thesis, finances={})
    facts = company_facts(c)
    assert any(f.startswith("Comptes non publiés") for f in facts["signaux_factuels"])
    flags = analyze_company(c, MockLLM()).analysis.red_flags
    assert flags[0].endswith("(signal factuel).") and flags[-1].startswith("Hypothèse")
