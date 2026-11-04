import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from .conftest import ROOT  # noqa: E402


def test_dashboard_runs_on_sample_without_keys():
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert any(m.label == "Emails envoyés" for m in at.metric)
