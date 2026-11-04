from datetime import date

from pme_radar.enrich import director_age, enrich, normalize, parse_director, revenue_cagr
from pme_radar.models import FinancialYear

from .conftest import AS_OF, raw_company


def test_full_company():
    c = normalize(raw_company(), AS_OF)
    assert c.director_age == 66  # né en mai 1960, au 4 nov. 2026
    assert c.company_age_years == 31
    assert c.is_owner_operator is True
    assert c.revenue_last == 6_000_000
    assert c.net_margin == 0.08
    assert round(c.revenue_cagr, 4) == round((6 / 5) ** 0.5 - 1, 4)
    assert c.accounts_available


def test_age_before_birthday_month():
    d = parse_director({"type_dirigeant": "personne physique", "date_de_naissance": "1960-12"})
    assert director_age(d, date(2026, 11, 4)) == 65


def test_age_year_only_is_estimate():
    d = parse_director({"type_dirigeant": "personne physique", "annee_de_naissance": 1960})
    assert d.birth_month is None
    assert director_age(d, AS_OF) == 66


def test_age_missing_and_corporate():
    assert director_age(None, AS_OF) is None
    corp = parse_director({"type_dirigeant": "personne morale", "denomination": "HOLDING X",
                           "date_de_naissance": "1960-01"})
    assert corp.birth_year is None and director_age(corp, AS_OF) is None


def test_corporate_director_not_owner_operator():
    raw = raw_company(dirigeants=[{"type_dirigeant": "personne morale", "denomination": "H SAS",
                                   "qualite": "Président"}])
    c = normalize(raw, AS_OF)
    assert c.is_owner_operator is False and c.has_corporate_director and c.director_age is None


def test_no_director_is_unknown_not_false():
    c = normalize(raw_company(dirigeants=[]), AS_OF)
    assert c.is_owner_operator is None and c.n_natural_directors == 0


def test_principal_director_prefers_president():
    raw = raw_company(dirigeants=[
        {"type_dirigeant": "personne physique", "nom": "A", "qualite": "Directeur général",
         "annee_de_naissance": 1985},
        {"type_dirigeant": "personne physique", "nom": "B", "qualite": "Président",
         "annee_de_naissance": 1958}])
    assert normalize(raw, AS_OF).director_age == 68


def test_confidential_accounts_are_missing_not_zero():
    for fin in ({}, None, {"2024": {"ca": None, "resultat_net": None}}):
        c = normalize(raw_company(finances=fin), AS_OF)
        assert not c.accounts_available
        assert c.revenue_last is None and c.net_margin is None and c.revenue_cagr is None


def test_revenue_without_net_income_has_no_margin():
    c = normalize(raw_company(finances={"2024": {"ca": 4_000_000}}), AS_OF)
    assert c.revenue_last == 4_000_000 and c.net_margin is None and c.revenue_cagr is None


def test_negative_margin_kept():
    c = normalize(raw_company(finances={"2024": {"ca": 1_000_000, "resultat_net": -50_000}}), AS_OF)
    assert c.net_margin == -0.05


def test_cagr_needs_two_years_and_positive_revenue():
    assert revenue_cagr([FinancialYear(year=2024, revenue=1.0)]) is None
    assert revenue_cagr([FinancialYear(year=2023, revenue=0), FinancialYear(year=2024, revenue=5)]) is None


def test_bad_creation_date():
    assert normalize(raw_company(date_creation="n/a"), AS_OF).company_age_years is None


def test_bodacc_flag_tri_state():
    raws = [raw_company(), raw_company(siren="999000008")]
    assert enrich(raws, AS_OF)[0].has_collective_procedure is None  # non interrogé
    out = enrich(raws, AS_OF, procedure_sirens={"999000008"})
    assert [c.has_collective_procedure for c in out] == [False, True]
