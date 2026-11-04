"""Génère des fixtures SYNTHÉTIQUES au format de l'API Recherche d'entreprises + BODACC.

Aucune donnée réelle : noms fictifs, SIREN dans la plage 999 000 001+ (réservée ici au synthétique).
Déterministe (seed fixe). Usage : python scripts/make_fixtures.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml

SEED = 20261104
N = 45
OUT = Path("tests/fixtures")
SURNAMES = [
    "Delorme",
    "Vasseur",
    "Marchetti",
    "Lefranc",
    "Bouvier",
    "Carpentier",
    "Desmoulins",
    "Garnier",
    "Hautecoeur",
    "Imbert",
    "Jolivet",
    "Kerbrat",
    "Lemaistre",
    "Maillard",
    "Noiret",
    "Ouvrard",
    "Perrault",
    "Quentin",
    "Rivoire",
    "Savary",
    "Tessier",
    "Urbain",
    "Valentin",
    "Wagner",
    "Yvon",
    "Zimmer",
    "Aubertin",
    "Blanchet",
    "Cordier",
    "Dupin",
    "Esnault",
    "Fabre",
    "Gilbert",
    "Hamon",
    "Ivanoff",
    "Jacquot",
    "Klein",
    "Lacombe",
    "Morvan",
    "Navarro",
    "Orsini",
    "Pelletier",
    "Roussel",
    "Sauvage",
    "Thibault",
]
FIRST = [
    "Alain",
    "Bernard",
    "Christian",
    "Daniel",
    "Eric",
    "François",
    "Gérard",
    "Hervé",
    "Jacques",
    "Laurent",
    "Michel",
    "Patrick",
    "Philippe",
    "Pierre",
    "Serge",
    "Thierry",
    "Brigitte",
    "Catherine",
    "Dominique",
    "Isabelle",
    "Martine",
    "Sophie",
]
NAF_NAMES = {
    "33.12Z": "Maintenance Industrielle",
    "33.14Z": "Électro-Maintenance",
    "33.20A": "Tuyauterie",
    "33.20B": "Montage Mécanique",
    "33.20D": "Installations Électriques",
    "43.21A": "Électricité",
    "43.22B": "Thermique & Climatisation",
    "80.20Z": "Sécurité Systèmes",
    "81.10Z": "Facility",
    "33.13Z": "Électronique Service",
    "43.22A": "Plomberie Fluides",
    "43.29B": "Aménagements",
    "71.20B": "Contrôle & Inspection",
}
DEPTS = {
    "75": ("Paris", "75011"),
    "92": ("Nanterre", "92000"),
    "93": ("Saint-Denis", "93200"),
    "94": ("Créteil", "94000"),
    "95": ("Cergy", "95000"),
    "78": ("Versailles", "78000"),
    "91": ("Évry", "91000"),
    "77": ("Meaux", "77100"),
}
BANDS = ["11", "12", "12", "21", "21", "22", "31"]


def _holding_record(i: int, surname: str, personal: set[int], groups: dict[int, str]):
    """Fiche de la société dirigeante (sans toucher au générateur principal : sorties stables)."""
    r = random.Random(1000 + i)
    siren = f"{998000001 + i:09d}"
    base = {"siren": siren, "etat_administratif": "A", "categorie_entreprise": "PME",
            "date_creation": "2005-06-01", "finances": {}}
    if i in personal:  # holding patrimoniale du fondateur
        year = r.randint(1955, 1966)
        return {**base, "nom_complet": f"{surname.upper()} PARTICIPATIONS", "activite_principale": "64.20Z",
                "dirigeants": [{"type_dirigeant": "personne physique", "nom": surname.upper(),
                                "prenoms": r.choice(FIRST), "qualite": "Président",
                                "date_de_naissance": f"{year}-{r.randint(1, 12):02d}",
                                "annee_de_naissance": year}]}
    kind = groups[i]
    if kind == "group_holding":  # holding animatrice d'un groupe : dirigée par une autre société
        return {**base, "nom_complet": "ALTAIR GROUPE HOLDING", "activite_principale": "64.20Z",
                "dirigeants": [{"type_dirigeant": "personne morale", "denomination": "ALTAIR CAPITAL SAS",
                                "siren": "997000001", "qualite": "Président"}]}
    if kind == "head_office":  # siège social d'un groupe industriel (NAF 70.10Z)
        return {**base, "nom_complet": "VEGA INDUSTRIES SIEGE", "activite_principale": "70.10Z",
                "dirigeants": [{"type_dirigeant": "personne physique", "nom": "MARCHAND",
                                "prenoms": "Claire", "qualite": "Directrice générale",
                                "annee_de_naissance": 1972}]}
    return None  # société introuvable dans l'API


def build() -> tuple[dict, dict]:
    rnd = random.Random(SEED)
    thesis = yaml.safe_load(Path("config/thesis.yaml").read_text(encoding="utf-8"))
    nafs = [n["code"] for n in thesis["naf_codes"]]
    core = [n["code"] for n in thesis["naf_codes"] if n["tier"] == "core"]
    results = []
    procedure = {5, 17, 33}  # procédures collectives (BODACC)
    # dirigeant personne morale : 3 holdings personnelles (64.20Z + personne physique) et 3 vrais groupes
    personal_holding = {3, 14, 28}
    group_parent = {9: "group_holding", 21: "head_office", 38: "unknown"}
    corporate = personal_holding | set(group_parent)
    holdings = []
    no_accounts = {2, 11, 19, 26, 35, 41}  # comptes confidentiels / absents
    year_only = {1, 6, 13, 24, 30, 40}  # date de naissance partielle
    no_director = {44}
    for i in range(N):
        siren = f"{999000001 + i * 7:09d}"
        naf = rnd.choice(core if rnd.random() < 0.7 else nafs)
        surname = rnd.choice(SURNAMES)
        name = f"{surname} {NAF_NAMES[naf]}".upper()
        dept = rnd.choice(list(DEPTS))
        city, cp = DEPTS[dept]
        senior = rnd.random() < 0.55
        birth_year = rnd.randint(1955, 1967) if senior else rnd.randint(1968, 1990)
        creation_year = rnd.randint(1985, 2012) if senior else rnd.randint(2000, 2020)
        base_rev = rnd.choice([1.2, 2.5, 3.5, 4.8, 6.2, 8.5, 11, 14, 19, 26, 34]) * 1e6
        trend = rnd.uniform(-0.06, 0.12)
        margin = rnd.uniform(0.0, 0.11) if rnd.random() > 0.15 else rnd.uniform(-0.04, 0)
        finances = {}
        n_years = rnd.choice([2, 3, 4])
        for k, y in enumerate(range(2024 - n_years + 1, 2025)):
            rev = base_rev * (1 + trend) ** (k - n_years + 1)
            finances[str(y)] = {
                "ca": int(rev),
                "resultat_net": int(rev * margin * rnd.uniform(0.8, 1.2)),
            }
        if i in no_accounts:
            finances = {} if i % 2 else {"2024": {"ca": None, "resultat_net": None}}
        dirigeants = []
        if i in corporate:
            holdings.append(_holding_record(i, surname, personal_holding, group_parent))
            dirigeants.append(
                {
                    "type_dirigeant": "personne morale",
                    "denomination": f"{rnd.choice(SURNAMES).upper()} HOLDING SAS",
                    "siren": f"{998000001 + i:09d}",
                    "qualite": "Président",
                }
            )
        elif i not in no_director:
            d = {
                "type_dirigeant": "personne physique",
                "nom": surname.upper(),
                "prenoms": rnd.choice(FIRST),
                "qualite": rnd.choice(["Président", "Gérant"]),
                "annee_de_naissance": birth_year,
            }
            if i not in year_only:
                d["date_de_naissance"] = f"{birth_year}-{rnd.randint(1, 12):02d}"
            dirigeants.append(d)
            if rnd.random() < 0.3:  # co-dirigeant
                dirigeants.append(
                    {
                        "type_dirigeant": "personne physique",
                        "nom": rnd.choice(SURNAMES).upper(),
                        "prenoms": rnd.choice(FIRST),
                        "qualite": "Directeur général",
                        "annee_de_naissance": rnd.randint(1975, 1990),
                        "date_de_naissance": f"{rnd.randint(1975, 1990)}-06",
                    }
                )
        results.append(
            {
                "siren": siren,
                "nom_complet": name,
                "nom_raison_sociale": name,
                "nature_juridique": rnd.choice(["5710", "5499", "5599"]),
                "activite_principale": naf,
                "categorie_entreprise": "PME",
                "tranche_effectif_salarie": rnd.choice(BANDS),
                "etat_administratif": "A",
                "date_creation": f"{creation_year}-{rnd.randint(1, 12):02d}-15",
                "siege": {
                    "siret": siren + "00011",
                    "code_postal": cp,
                    "libelle_commune": city,
                    "departement": dept,
                    "activite_principale": naf,
                },
                "dirigeants": dirigeants,
                "finances": finances,
            }
        )
    sirens = [r["siren"] for r in results]
    def registre(s: str) -> str:
        return f"{s[:3]} {s[3:6]} {s[6:]}"

    bodacc = {"total_count": len(procedure), "results": [
        {"registre": [registre(sirens[i])], "typeavis": "annonce",
         "dateparution": f"2026-09-{10 + k}"}
        for k, i in enumerate(sorted(procedure))]}
    holdings = [h for h in holdings if h is not None]
    return {"results": results}, bodacc, {"results": holdings}


def build_ratios(results: list[dict]) -> dict:
    """Lignes « ratios INPI » synthétiques (EBE, endettement), RNG séparé : autres sorties stables."""
    r = random.Random(3000)
    rows = []
    for i, c in enumerate(results):
        if i % 5 == 4:  # pas de ratios publiés pour 1 société sur 5
            continue
        ca0 = next((v["ca"] for v in c["finances"].values() if v.get("ca")), None)
        years = range(2020, 2025)
        base = ca0 or r.choice([2.5, 5, 9]) * 1e6
        ebe_m = r.uniform(0.0, 0.17)
        for k, y in enumerate(years):
            ca = int(base * (1.03 ** (k - 4)))
            partial = i % 7 == 3 and y == 2024  # dernier bilan partiellement confidentiel
            rows.append({
                "siren": c["siren"],
                "date_cloture_exercice": f"{y}-12-31",
                "chiffre_d_affaires": 0 if partial else ca,
                "ebe": 0 if partial else int(ca * ebe_m * r.uniform(0.85, 1.15)),
                "resultat_net": int(ca * ebe_m * 0.45),
                "taux_d_endettement": round(r.uniform(5, 140), 3),
                "confidentiality": "Partiellement confidentiel" if partial else "Public",
            })
    return {"total_count": len(rows), "results": rows}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    search, bodacc, holdings = build()
    (OUT / "recherche_entreprises_search.json").write_text(
        json.dumps(search, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "bodacc_records.json").write_text(
        json.dumps(bodacc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "recherche_entreprises_holdings.json").write_text(
        json.dumps(holdings, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "inpi_ratios.json").write_text(
        json.dumps(build_ratios(search["results"]), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"{len(search['results'])} entreprises synthétiques, {len(bodacc['results'])} procédures")
