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
