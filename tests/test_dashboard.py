import shutil

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from .conftest import ROOT  # noqa: E402

APP = str(ROOT / "dashboard" / "app.py")
TOP = "999000197"  # meilleure cible de l'échantillon synthétique


@pytest.fixture(autouse=True)
def demo_data(monkeypatch):
    """Échantillon synthétique, quel que soit le contenu local de data/."""
    monkeypatch.setenv("PME_RADAR_DATA", "sample")
    monkeypatch.delenv("PME_RADAR_DATA_DIR", raising=False)


def open_app(page: str | None = None, **query: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90).run()
    if page:
        at.switch_page(page)
        for k, v in query.items():
            at.query_params[k] = v
        at.run()
    assert not at.exception, at.exception
    return at


def html(at: AppTest) -> str:
    return " ".join(h.value for h in at.html) + " ".join(m.value for m in at.markdown)


def test_home_runs_on_sample_without_keys():
    at = open_app()
    labels = [m.label for m in at.metric]
    assert labels == [
        "Entreprises analysées",
        "Qualifiées",
        "À approcher",
        "Contactées",
        "Rendez-vous",
    ]
    assert int(at.metric[0].value) == 45
    page = html(at)
    assert "cibles prêtes à être approchées" in page and "Échantillon synthétique" in page
    assert "À faire maintenant" in [s.value for s in at.subheader]


def test_global_search_opens_the_company_sheet():
    at = open_app()
    search = at.selectbox(key="global_search")
    assert any(
        "PELLETIER TUYAUTERIE" in o and TOP in o for o in search.options
    )  # nom, ville, SIREN, dirigeant
    search.set_value(TOP).run()
    assert not at.exception
    assert "PELLETIER TUYAUTERIE" in html(at)
    metrics = {m.label: m.value for m in at.metric}
    assert {
        "Chiffre d'affaires",
        "Valeur d'entreprise",
        "Fonds propres à réunir",
        "Dirigeant",
    } <= set(metrics)
    assert [t.label.split(" ", 1)[1] for t in at.tabs] == [
        "Profil", "Finances", "Score", "Valorisation", "Due diligence", "Contact", "Documents",
    ]  # fmt: skip
    # brouillon : affiché à relire, jamais envoyé, avec la mention de conformité
    assert "AUCUN ENVOI AUTOMATIQUE" in html(at)
    assert any("sources publiques" in c.value for c in at.code)
    assert at.selectbox(key="global_search").value is None  # la recherche se vide après ouverture


def test_company_deep_link_and_browsing():
    at = open_app("views/entreprise.py", siren=TOP)
    assert at.selectbox(key="company").value == TOP
    assert "PELLETIER TUYAUTERIE" in html(at)
    next(b for b in at.button if b.label == "Suivante").click().run()
    assert not at.exception and at.selectbox(key="company").value != TOP
    # SIREN inconnu : page d'accueil de la fiche, avec suggestions
    at = open_app("views/entreprise.py", siren="123")
    assert "Suggestions : meilleures cibles" in [s.value for s in at.subheader]


def test_targets_screener_filters_and_presets():
    at = open_app("views/cibles.py")
    total = len(at.dataframe[0].value)
    assert total == 42  # écartées masquées par défaut
    at.slider(key="min_score").set_value(80).run()
    assert not at.exception and len(at.dataframe[0].value) < total
    at.slider(key="min_score").set_value(0).run()
    at.pills(key="preset").set_value("À approcher").run()
    shown = at.dataframe[0].value
    assert len(shown) > 0 and all(tag == ["À approcher"] for tag in shown["reco_tag"])
    at.text_input(key="q").set_value("introuvable-xyz").run()
    assert "Aucune entreprise" in at.warning[0].value


def test_campaign_reports_and_help_pages():
    at = open_app("views/campagne.py")
    assert "Emails envoyés" in [m.label for m in at.metric]
    assert any(s.value.startswith("À traiter") for s in at.subheader)
    at = open_app("views/rapports.py")
    labels = [b.label for b in at.get("download_button")]
    assert any("Télécharger le rapport" in x for x in labels) and any("Excel" in x for x in labels)
    at = open_app("views/aide.py")
    at.text_input(key="term").set_value("crédit vendeur").run()
    assert any("Crédit vendeur" in m.value for m in at.markdown)


def test_live_mode_status_update(tmp_path, monkeypatch):
    """Avec un run local, le statut de contact se met à jour depuis la fiche."""
    data = tmp_path / "data"
    (data / "processed").mkdir(parents=True)
    (data / "out").mkdir()
    shutil.copy(ROOT / "examples" / "sample_companies.jsonl", data / "processed" / "analyzed.jsonl")
    shutil.copy(ROOT / "examples" / "sample_campaign.csv", data / "out" / "campaign.csv")
    monkeypatch.delenv("PME_RADAR_DATA")
    monkeypatch.setenv("PME_RADAR_DATA_DIR", str(data))
    at = open_app("views/entreprise.py", siren=TOP)
    assert "Dernier run" in html(at)
    form_status = next(s for s in at.selectbox if s.label == "Nouveau statut")
    form_status.set_value("meeting")
    next(b for b in at.button if b.label == "Enregistrer").click().run()
    assert not at.exception
    camp = pd.read_csv(data / "out" / "campaign.csv", dtype=str).set_index("siren")
    assert camp.loc[TOP, "status"] == "meeting" and camp.loc[TOP, "campaign_id"] == "manuel"


def test_empty_run_shows_guidance(tmp_path, monkeypatch):
    """Run sans société notée : chaque page explique quoi faire, sans erreur."""
    data = tmp_path / "data"
    (data / "processed").mkdir(parents=True)
    (data / "processed" / "analyzed.jsonl").write_text("", encoding="utf-8")
    monkeypatch.delenv("PME_RADAR_DATA")
    monkeypatch.setenv("PME_RADAR_DATA_DIR", str(data))
    for page in (
        None,
        "views/entreprise.py",
        "views/cibles.py",
        "views/campagne.py",
        "views/rapports.py",
    ):
        at = open_app(page)
        assert "Aucune entreprise notée" in html(at), page
