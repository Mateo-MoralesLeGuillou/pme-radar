from pme_radar.enrich import normalize
from pme_radar.models import Stage
from pme_radar.scoring import score_all, score_company

from .conftest import AS_OF, raw_company


def tiers(thesis):
    return {n["code"]: n["tier"] for n in thesis["naf_codes"]}


def test_max_points_sum_to_100(scoring_cfg):
    assert sum(c["max_points"] for c in scoring_cfg["criteria"].values()) == 100


def test_ideal_target_scores_high(scoring_cfg, thesis):
    raw = raw_company(finances={"2022": {"ca": 9e6, "resultat_net": 7e5},
                                "2024": {"ca": 10e6, "resultat_net": 9e5}})
    s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
    assert s.total >= 90 and not s.excluded
    assert "dirigeant 66 ans" in s.summary and "10,0 M€" in s.summary


def test_breakdown_sums_to_total(scoring_cfg, thesis):
    s = score_company(normalize(raw_company(), AS_OF), scoring_cfg, tiers(thesis))
    assert round(sum(r.points for r in s.criteria) + sum(p.points for p in s.penalties), 1) == s.total
    assert all(r.points <= r.max_points for r in s.criteria)


def test_missing_age_gives_zero_points_not_exclusion(scoring_cfg, thesis):
    raw = raw_company(dirigeants=[{"type_dirigeant": "personne physique", "nom": "X",
                                   "qualite": "Gérant"}])
    s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
    age = next(r for r in s.criteria if r.key == "director_age")
    assert age.points == 0 and age.detail == "n.d." and not s.excluded


def test_confidential_accounts_light_penalty(scoring_cfg, thesis):
    s = score_company(normalize(raw_company(finances={}), AS_OF), scoring_cfg, tiers(thesis))
    assert [p.key for p in s.penalties] == ["missing_financials"]
    assert not s.excluded and s.total > 0
    assert "n.d." in s.summary


def test_corporate_director_penalty(scoring_cfg, thesis):
    raw = raw_company(dirigeants=[{"type_dirigeant": "personne morale", "denomination": "H",
                                   "qualite": "Président"}])
    s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
    assert "corporate_director" in [p.key for p in s.penalties]


def test_collective_procedure_excludes(scoring_cfg, thesis):
    c = normalize(raw_company(), AS_OF)
    c.has_collective_procedure = True
    s = score_company(c, scoring_cfg, tiers(thesis))
    assert s.excluded and s.total == 0 and "BODACC" in s.exclusion_reason


def test_score_never_negative(scoring_cfg, thesis):
    raw = raw_company(activite_principale="99.99Z", finances={}, tranche_effectif_salarie=None,
                      date_creation=None,
                      dirigeants=[{"type_dirigeant": "personne morale", "denomination": "H"}])
    s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
    assert s.total == 0


def test_band_boundaries(scoring_cfg, thesis):
    def pts(birth):
        raw = raw_company(dirigeants=[{"type_dirigeant": "personne physique", "nom": "X",
                                       "qualite": "Président", "date_de_naissance": birth}])
        s = score_company(normalize(raw, AS_OF), scoring_cfg, tiers(thesis))
        return next(r.points for r in s.criteria if r.key == "director_age")
    assert pts("1968-06") == 18   # 58 ans pile
    assert pts("1968-12") == 10   # 57 ans
    assert pts("1961-01") == 25   # 65 ans


def test_thresholds_editable_without_code(scoring_cfg, thesis):
    cs = [normalize(raw_company(), AS_OF)]
    assert score_all(cs, {**scoring_cfg, "qualified_threshold": 1}, thesis)[0].stage == Stage.QUALIFIED
    assert score_all(cs, {**scoring_cfg, "qualified_threshold": 101}, thesis)[0].stage == Stage.IDENTIFIED


def test_ranking_puts_excluded_last(scoring_cfg, thesis):
    a, b = normalize(raw_company(), AS_OF), normalize(raw_company(siren="999000008"), AS_OF)
    a.has_collective_procedure = True
    ranked = score_all([a, b], scoring_cfg, thesis)
    assert ranked[-1].siren == a.siren and ranked[-1].stage == Stage.EXCLUDED
