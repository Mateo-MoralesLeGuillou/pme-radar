from pme_radar.enrich import normalize
from pme_radar.onepager import DISCLAIMER, render, valuation_range
from pme_radar.scoring import score_company

from .conftest import AS_OF, raw_company

CFG = {"ebe_multiple_low": 4.0, "ebe_multiple_high": 6.0}


def company(scoring_cfg, thesis, ebe):
    ratios = [
        {
            "siren": "999000001",
            "date_cloture_exercice": "2024-12-31",
            "ebe": ebe,
            "chiffre_d_affaires": 6e6,
            "resultat_net": 1,
            "confidentiality": "Public",
        }
    ]
    c = normalize(raw_company(), AS_OF, ratios=ratios)
    c.score = score_company(c, scoring_cfg, {n["code"]: n["tier"] for n in thesis["naf_codes"]})
    return c


def test_valuation_is_ebe_times_configured_multiples(scoring_cfg, thesis):
    assert valuation_range(company(scoring_cfg, thesis, 1e6), CFG) == (4e6, 6e6)


def test_no_valuation_without_positive_ebe(scoring_cfg, thesis):
    assert valuation_range(company(scoring_cfg, thesis, -1e5), CFG) is None
    assert "Non calculable" in render(company(scoring_cfg, thesis, -1e5), CFG)


def test_onepager_has_disclaimer_and_sections(scoring_cfg, thesis):
    md = render(company(scoring_cfg, thesis, 1e6), CFG)
    assert DISCLAIMER in md and "4,00 M€ à 6,00 M€" in md
    for h in ("## Identité", "## Détail du score", "## Mini-thèse", "## Valorisation indicative"):
        assert h in md
