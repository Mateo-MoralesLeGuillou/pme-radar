from pme_radar.enrich import normalize
from pme_radar.scoring import score_company
from pme_radar.sources._http import FixtureFetcher
from pme_radar.sources.inpi_ratios import fetch_ratios

from .conftest import AS_OF, raw_company

PUBLIC = {"siren": "999000001", "confidentiality": "Public", "taux_d_endettement": 42.0}


def row(year, ca, ebe, **over):
    return {
        **PUBLIC,
        "date_cloture_exercice": f"{year}-12-31",
        "chiffre_d_affaires": ca,
        "ebe": ebe,
        "resultat_net": 1,
        **over,
    }


def test_fetch_ratios_offline_fixture():
    got = fetch_ratios(FixtureFetcher("tests/fixtures"), ["999000001", "999000008"])
    assert (
        got["999000001"][0]["date_cloture_exercice"] > got["999000001"][-1]["date_cloture_exercice"]
    )


def test_ebe_taken_from_latest_public_row_with_revenue():
    ratios = [row(2024, 0, 0, confidentiality="Partiellement confidentiel"), row(2023, 6e6, 6e5)]
    c = normalize(raw_company(finances={}), AS_OF, ratios=ratios)
    assert (c.ebe, c.ebe_year, c.ebe_margin, c.debt_ratio) == (6e5, 2023, 0.1, 42.0)
    assert c.revenue_last == 6e6  # le CA manquant de l'API est comblé par l'INPI


def test_masked_zero_is_never_an_ebe():
    ratios = [row(2024, 0, 0, confidentiality="Partiellement confidentiel")]
    c = normalize(raw_company(finances={}), AS_OF, ratios=ratios)
    assert c.ebe is None and c.ebe_margin is None and c.revenue_last is None


def test_api_revenue_wins_over_inpi_for_same_year():
    c = normalize(raw_company(), AS_OF, ratios=[row(2024, 9e6, 9e5)])
    assert c.revenue_last == 6_000_000


def test_score_uses_ebe_margin_then_falls_back_to_net_margin(scoring_cfg, thesis):
    tiers = {n["code"]: n["tier"] for n in thesis["naf_codes"]}

    def prof(c):
        return next(
            r for r in score_company(c, scoring_cfg, tiers).criteria if r.key == "profitability"
        )

    with_ebe = prof(normalize(raw_company(), AS_OF, ratios=[row(2024, 6e6, 8e5)]))
    assert "EBE" in with_ebe.label and with_ebe.points == 8  # 13 % >= 12 %
    fallback = prof(normalize(raw_company(), AS_OF))
    assert "marge nette" in fallback.label and fallback.points == 8  # 8 % >= 8 %


def test_stale_ratios_are_ignored():
    c = normalize(raw_company(finances={}), AS_OF, ratios=[row(2016, 6e6, 6e5)])
    assert c.ebe is None and c.revenue_last is None
