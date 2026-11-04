from datetime import date
from pathlib import Path

import pytest

from pme_radar.config import load_yaml

ROOT = Path(__file__).resolve().parent.parent
AS_OF = date(2026, 11, 4)


@pytest.fixture(scope="session")
def thesis():
    return load_yaml(ROOT / "config" / "thesis.yaml")


@pytest.fixture(scope="session")
def scoring_cfg():
    return load_yaml(ROOT / "config" / "scoring.yaml")


def raw_company(**over):
    base = {
        "siren": "999000001",
        "nom_complet": "TEST MAINTENANCE",
        "activite_principale": "33.12Z",
        "categorie_entreprise": "PME",
        "tranche_effectif_salarie": "12",
        "date_creation": "1995-03-15",
        "siege": {"code_postal": "92000", "libelle_commune": "Nanterre", "departement": "92"},
        "dirigeants": [
            {
                "type_dirigeant": "personne physique",
                "nom": "DUPONT",
                "prenoms": "Alain",
                "qualite": "Président",
                "date_de_naissance": "1960-05",
            }
        ],
        "finances": {
            "2022": {"ca": 5_000_000, "resultat_net": 300_000},
            "2024": {"ca": 6_000_000, "resultat_net": 480_000},
        },
    }
    base.update(over)
    return base
