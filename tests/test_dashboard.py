import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from .conftest import ROOT  # noqa: E402


def test_dashboard_runs_on_sample_without_keys():
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert any(m.label == "Emails envoyés" for m in at.metric)


def test_dashboard_filters_and_empty_selection():
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    total = int(at.metric[0].value)
    at.slider[0].set_value(80).run()
    assert not at.exception and int(at.metric[0].value) < total
    at.slider[0].set_value(100).run()
    assert not at.exception and "Aucune entreprise" in at.warning[0].value


def test_dashboard_tabs_and_draft_preview():
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Vue d'ensemble", "Cibles", "Campagne"]
    html_blocks = " ".join(m.value for m in at.markdown)
    assert "AUCUN ENVOI AUTOMATIQUE" in html_blocks  # brouillon affiché, jamais envoyé
    assert "sources publiques" in html_blocks  # mention de conformité visible dans l'aperçu
    assert "Échantillon synthétique" in html_blocks
