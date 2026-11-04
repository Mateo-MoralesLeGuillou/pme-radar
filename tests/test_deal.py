"""Modèle enrichi (fourchette, fiabilité, endettement), signaux factuels, montage, rapport de deal flow."""

import copy
from datetime import date

import pandas as pd
import pytest
from typer.testing import CliRunner

from pme_radar.cli import app
from pme_radar.config import ConfigError, validate_scoring, validate_thesis
from pme_radar.deal import data_gaps, dd_questions, financing_plan, recommend
from pme_radar.enrich import normalize
from pme_radar.llm.analysis import analyze_top
from pme_radar.llm.mock_provider import MockLLM
from pme_radar.models import Stage
from pme_radar.report import build_report, evaluate
from pme_radar.risks import Signal, assess
from pme_radar.scoring import score_all, score_company

from .conftest import AS_OF, ROOT, raw_company


def tiers(thesis):
    return {n["code"]: n["tier"] for n in thesis["naf_codes"]}


def scored(scoring_cfg, thesis, **over):
    c = normalize(raw_company(**over), AS_OF)
    return score_all([c], scoring_cfg, thesis)[0]


# ---------------------------------------------------------------- fourchette et fiabilité
def test_complete_data_has_no_upside(scoring_cfg, thesis):
    s = score_company(normalize(raw_company(), AS_OF), scoring_cfg, tiers(thesis))
    assert s.confidence == 1.0 and s.ceiling == s.total
    assert not any(r.missing for r in s.criteria)


def test_missing_age_raises_ceiling_and_lowers_confidence(scoring_cfg, thesis):
    raw = raw_company(
        dirigeants=[{"type_dirigeant": "personne physique", "nom": "X", "qualite": "Gérant"}]
    )
    s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
    age = next(r for r in s.criteria if r.key == "director_age")
    assert age.missing and age.points == 0
    assert s.ceiling == s.total + 25 and s.confidence == 0.75
    assert "jusqu'à" in s.summary


def test_missing_accounts_upside_includes_lifted_penalty(scoring_cfg, thesis):
    s = score_company(normalize(raw_company(finances={}), AS_OF), scoring_cfg, tiers(thesis))
    missing = {r.key for r in s.criteria if r.missing}
    assert missing == {"revenue", "profitability", "revenue_cagr"}
    # 15 + 8 + 6 points manquants, plus la pénalité de 5 levée si les comptes existent
    assert s.ceiling == min(100, s.total + 15 + 8 + 6 + 5)
    assert s.confidence == pytest.approx(0.71)


def test_to_document_flag(scoring_cfg, thesis):
    # données lacunaires : sous le seuil, mais le plafond l'atteint
    c = scored(scoring_cfg, thesis, finances={},
               dirigeants=[{"type_dirigeant": "personne physique", "nom": "X", "qualite": "Gérant"}])  # fmt: skip
    assert c.stage == Stage.IDENTIFIED
    assert c.score.total < scoring_cfg["qualified_threshold"] <= c.score.ceiling
    assert c.score.to_document
    full = scored(scoring_cfg, thesis)
    assert not full.score.to_document  # qualifiée : pas « à documenter »


def test_high_debt_penalty(scoring_cfg, thesis):
    c = normalize(raw_company(), AS_OF)
    base = score_company(c, scoring_cfg, tiers(thesis)).total
    c.debt_ratio = 220
    s = score_company(c, scoring_cfg, tiers(thesis))
    pen = next(p for p in s.penalties if p.key == "high_debt")
    assert pen.points == -5 and "220" in pen.detail and s.total == base - 5
    c.debt_ratio = 120
    assert "high_debt" not in [
        p.key for p in score_company(c, scoring_cfg, tiers(thesis)).penalties
    ]


def test_excluded_keeps_confidence(scoring_cfg, thesis):
    c = normalize(raw_company(), AS_OF)
    c.has_collective_procedure = True
    s = score_company(c, scoring_cfg, tiers(thesis))
    assert s.excluded and s.total == 0 and s.confidence == 1.0


def test_scoring_details_in_french(scoring_cfg, thesis):
    s = score_company(normalize(raw_company(), AS_OF), scoring_cfg, tiers(thesis))
    details = {r.key: r.detail for r in s.criteria}
    assert details["headcount"] == "20-49 salariés"
    assert details["revenue_cagr"].endswith("%/an") and "," in details["revenue_cagr"]


# ---------------------------------------------------------------- configuration
def test_validation_of_new_settings(scoring_cfg, thesis):
    bad = copy.deepcopy(scoring_cfg)
    bad["penalties"]["high_debt"] = 5
    bad["risk_thresholds"]["low_ebe_margin"] = "faible"
    msg = str(pytest.raises(ConfigError, validate_scoring, bad).value)
    assert "penalties.high_debt" in msg and "risk_thresholds.low_ebe_margin" in msg
    bad_t = copy.deepcopy(thesis)
    bad_t["financing"]["max_debt_share"] = 1.5
    bad_t["financing"]["interest_rate"] = "cinq"
    msg = str(pytest.raises(ConfigError, validate_thesis, bad_t).value)
    assert "financing.max_debt_share" in msg and "financing.interest_rate" in msg


# ---------------------------------------------------------------- signaux factuels
def _titles(c, cfg):
    return [s.title for s in assess(c, cfg, AS_OF)]


def test_signals_by_rule(scoring_cfg):
    c = normalize(raw_company(), AS_OF)
    c.has_collective_procedure = True
    c.debt_ratio = 300
    c.revenue_cagr = -0.10
    c.ebe, c.ebe_margin, c.ebe_year = 100_000, 0.02, 2021
    sig = assess(c, scoring_cfg, AS_OF)
    titles = [s.title for s in sig]
    for expected in ("Procédure collective au BODACC", "Endettement élevé", "Chiffre d'affaires en baisse",
                     "Rentabilité faible", "Comptes anciens", "Dépendance au dirigeant"):  # fmt: skip
        assert expected in titles
    levels = [s.level for s in sig]
    assert levels == sorted(
        levels, key=("élevé", "moyen", "info").index
    )  # du plus grave au moins grave
    assert all(s.question.endswith((".", "?")) for s in sig)


def test_signals_absent_on_healthy_company(scoring_cfg):
    titles = _titles(normalize(raw_company(), AS_OF), scoring_cfg)
    assert "Endettement élevé" not in titles and "Rentabilité faible" not in titles
    assert "Procédure collective au BODACC" not in titles


def test_revenue_per_employee_signals(scoring_cfg):
    c = normalize(
        raw_company(tranche_effectif_salarie="11", finances={"2024": {"ca": 30_000_000}}), AS_OF
    )
    assert "Chiffre d'affaires par salarié élevé" in _titles(c, scoring_cfg)
    c = normalize(
        raw_company(tranche_effectif_salarie="22", finances={"2024": {"ca": 2_000_000}}), AS_OF
    )
    assert "Chiffre d'affaires par salarié faible" in _titles(c, scoring_cfg)


def test_signals_thresholds_from_config(scoring_cfg):
    c = normalize(raw_company(), AS_OF)
    c.debt_ratio = 120
    assert "Endettement élevé" not in _titles(c, scoring_cfg)
    stricter = {
        **scoring_cfg,
        "risk_thresholds": {**scoring_cfg["risk_thresholds"], "high_debt_ratio": 100},
    }
    assert "Endettement élevé" in _titles(c, stricter)


# ---------------------------------------------------------------- montage et recommandation
def test_financing_plan_math(thesis):
    c = normalize(raw_company(), AS_OF)
    c.ebe = 1_000_000
    p = financing_plan(c, thesis)
    assert (p.ev_low, p.ev_mid, p.ev_high) == (4_000_000, 5_000_000, 6_000_000)
    assert p.senior_debt == 2_500_000  # 2,5x l'EBE, sous le plafond de 60 % du prix
    assert p.vendor_loan == 500_000 and p.equity == 2_000_000 and p.equity_share == 0.4
    r, n = 0.055, 7
    assert p.annual_debt_service == pytest.approx(2_500_000 * r / (1 - (1 + r) ** -n))
    assert p.coverage == pytest.approx(600_000 / p.annual_debt_service)


def test_debt_capped_by_price_share(thesis):
    t = copy.deepcopy(thesis)
    t["financing"]["senior_debt_multiple"] = 5.0
    c = normalize(raw_company(), AS_OF)
    c.ebe = 1_000_000
    assert financing_plan(c, t).senior_debt == pytest.approx(3_000_000)  # 60 % de 5 M€


def test_no_plan_without_positive_ebe(thesis):
    c = normalize(raw_company(), AS_OF)
    assert financing_plan(c, thesis) is None
    c.ebe = -10_000
    assert financing_plan(c, thesis) is None


def _rec(c, cfg, thesis):
    sig = assess(c, cfg, AS_OF)
    return recommend(c, sig, financing_plan(c, thesis), cfg, thesis)


def test_recommendation_rules(scoring_cfg, thesis):
    good = scored(scoring_cfg, thesis)
    good.ebe, good.ebe_margin, good.ebe_year = 900_000, 0.12, 2024
    r = _rec(good, scoring_cfg, thesis)
    assert r.label == "À approcher" and r.tone == "go" and r.next_steps
    assert any("fonds propres" in x for x in r.reasons)

    risky = scored(scoring_cfg, thesis)
    risky.debt_ratio = 400
    assert _rec(risky, scoring_cfg, thesis).label == "À creuser"

    big = scored(scoring_cfg, thesis)
    big.ebe = 4_000_000  # fonds propres ≈ 8 M€ > plafond de 6 M€
    r = _rec(big, scoring_cfg, thesis)
    assert r.label == "À creuser" and "ticket" in r.reasons[0]

    doc = scored(scoring_cfg, thesis, finances={},
                 dirigeants=[{"type_dirigeant": "personne physique", "nom": "X", "qualite": "Gérant"}])  # fmt: skip
    assert _rec(doc, scoring_cfg, thesis).label == "À documenter"

    excl = normalize(raw_company(), AS_OF)
    excl.has_collective_procedure = True
    excl = score_all([excl], scoring_cfg, thesis)[0]
    assert _rec(excl, scoring_cfg, thesis).label == "Écartée"

    low = scored(scoring_cfg, thesis, activite_principale="99.99Z", tranche_effectif_salarie="31",
                 date_creation="2020-01-01")  # fmt: skip
    low.director_age = 40
    low = score_all([low], scoring_cfg, thesis)[0]
    assert low.score.ceiling < scoring_cfg["qualified_threshold"]
    assert _rec(low, scoring_cfg, thesis).label == "Non prioritaire"


def test_low_confidence_qualified_is_to_document(scoring_cfg, thesis):
    c = scored(scoring_cfg, thesis)
    c.score.confidence = 0.5
    assert _rec(c, scoring_cfg, thesis).label == "À documenter"


def test_dd_questions_put_triggered_first():
    sig = [Signal("moyen", "Commercial", "CA en baisse", "-10 %", "Pourquoi la baisse ?")]
    qs = dd_questions(sig)
    assert qs["Commercial"][0] == "Pourquoi la baisse ?"
    assert len(qs["Commercial"]) == 4 and len(qs["Juridique"]) == 3
    assert len(set(qs["Financier"])) == len(qs["Financier"])


def test_data_gaps(scoring_cfg, thesis):
    full = scored(scoring_cfg, thesis)
    assert data_gaps(full) == ["EBE (valorisation et capacité d'endettement)"]
    thin = scored(scoring_cfg, thesis, finances={})
    assert "Chiffre d'affaires du dernier exercice" in data_gaps(thin)


# ---------------------------------------------------------------- rapport
def _companies(scoring_cfg, thesis):
    cs = [
        normalize(raw_company(siren=f"99900000{i}", nom_complet=f"CIBLE {i}"), AS_OF)
        for i in range(4)
    ]
    cs[0].ebe, cs[0].ebe_margin, cs[0].ebe_year = 900_000, 0.12, 2024
    cs[1].debt_ratio = 400
    cs[2].name = "<script>alert(1)</script> & Fils"
    cs[3].has_collective_procedure = True
    cs = score_all(cs, scoring_cfg, thesis)
    analyze_top(cs, MockLLM(), top_n=4)
    return cs


def test_report_contains_every_section(scoring_cfg, thesis):
    cs = _companies(scoring_cfg, thesis)
    html, chosen = build_report(cs, scoring_cfg, thesis, footer="Mention RGPD.", as_of=AS_OF)
    assert len(chosen) == 3  # l'exclue n'a pas de dossier
    assert chosen[0].rec.tone == "go"  # à approcher d'abord
    for section in ("Synthèse du pipeline", "Dossiers détaillés", "Identité et gouvernance",
                    "Données financières", "Score détaillé", "Valorisation et montage indicatifs",
                    "Signaux factuels", "Données et documents à obtenir", "Questions de due diligence",
                    "Brouillon d'approche", "Méthodologie et limites", "Mention RGPD."):  # fmt: skip
        assert section in html
    assert "échantillon synthétique" in html and "données personnelles" in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html  # échappé
    assert "Non calculable" in html  # cibles sans EBE


def test_report_selection_by_siren(scoring_cfg, thesis):
    cs = _companies(scoring_cfg, thesis)
    _, chosen = build_report(cs, scoring_cfg, thesis, sirens=["999000001"], as_of=AS_OF)
    assert [d.company.siren for d in chosen] == ["999000001"]
    assert evaluate(cs, scoring_cfg, thesis, AS_OF)[3].rec.label == "Écartée"


def test_report_campaign_line(scoring_cfg, thesis):
    cs = _companies(scoring_cfg, thesis)
    camp = pd.DataFrame({"siren": ["999000000", "999000001"], "status": ["meeting", "contacted"]})
    html, _ = build_report(cs, scoring_cfg, thesis, campaign=camp, as_of=AS_OF)
    assert "2 contact(s) envoyé(s), 1 réponse(s), 1 rendez-vous" in html


def test_cli_report(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    data = str(tmp_path / "data")
    r = CliRunner().invoke(app, ["run", "--offline", "--data-dir", data])
    assert r.exit_code == 0, r.output
    out = tmp_path / "data" / "out" / "rapport_deal_flow.html"
    assert out.exists() and "Rapport de deal flow" in out.read_text(encoding="utf-8")
    one = tmp_path / "un.html"
    r = CliRunner().invoke(
        app, ["report", "--data-dir", data, "--siren", "999000197", "--output", str(one)]
    )
    assert r.exit_code == 0 and "1 dossier" in r.output and one.exists()
    r = CliRunner().invoke(app, ["report", "--data-dir", data, "--siren", "123"])
    assert r.exit_code == 1


def test_as_of_used_for_stale_accounts(scoring_cfg):
    c = normalize(raw_company(), AS_OF)
    c.ebe, c.ebe_margin, c.ebe_year = 500_000, 0.1, 2024
    assert "Comptes anciens" not in [s.title for s in assess(c, scoring_cfg, date(2026, 6, 1))]
    assert "Comptes anciens" in [s.title for s in assess(c, scoring_cfg, date(2028, 6, 1))]
