import pandas as pd
from typer.testing import CliRunner

from pme_radar import export
from pme_radar.cli import app
from pme_radar.enrich import normalize

from .conftest import AS_OF, ROOT, raw_company


class FakeWS:
    def __init__(self):
        self.values = None

    def clear(self):
        self.cleared = True

    def update(self, values):
        self.values = values


class FakeSheet:
    def __init__(self, existing=()):
        self.ws = {n: FakeWS() for n in existing}

    def worksheet(self, name):
        if name not in self.ws:
            raise KeyError(name)
        return self.ws[name]

    def add_worksheet(self, title, rows, cols):
        self.ws[title] = FakeWS()
        return self.ws[title]


def test_company_row_and_tabs():
    t = export.targets_frame([normalize(raw_company(), AS_OF)])
    camp = pd.DataFrame(
        {
            "siren": ["999000001"],
            "campaign_id": ["c"],
            "status": ["meeting"],
            "sent_date": ["2026-11-01"],
        }
    )
    tabs = export.build_tabs(t, camp)
    assert list(tabs) == ["Identified", "Qualified", "Contacted", "Meeting", "Funnel"]
    assert len(tabs["Meeting"]) == 1 and len(tabs["Contacted"]) == 1


def test_sheets_export_with_fake_spreadsheet():
    t = export.targets_frame([normalize(raw_company(finances={}), AS_OF)])
    sheet = FakeSheet(existing=["Identified"])
    export.export_sheets(sheet, export.build_tabs(t, None))
    assert set(sheet.ws) == {"Identified", "Qualified", "Contacted", "Meeting", "Funnel"}
    header, row = sheet.ws["Identified"].values
    assert "siren" in header and "" in row  # NaN -> cellule vide, pas "nan"


def test_sheets_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    assert not export.sheets_configured()


def test_cli_run_offline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    data = str(tmp_path / "data")
    r = CliRunner().invoke(app, ["run", "--offline", "--data-dir", data])
    assert r.exit_code == 0, r.output
    out = tmp_path / "data" / "out"
    for f in ("identified.csv", "qualified.csv", "funnel.csv", "drafts.csv", "campaign.csv"):
        assert (out / f).exists(), f
    ident = pd.read_csv(out / "identified.csv")
    assert len(ident) == 45 and (ident["stage"] == "excluded").sum() == 3
    assert ident.loc[ident["stage"] == "excluded", "score"].eq(0).all()
    # suivi manuel puis métriques
    sir = pd.read_csv(out / "campaign.csv", dtype=str).loc[0, "siren"]
    assert CliRunner().invoke(app, ["track", sir, "contacted", "--data-dir", data]).exit_code == 0
    r = CliRunner().invoke(app, ["deliverability", "--data-dir", data])
    assert r.exit_code == 0 and "sent" in r.output


def test_sample_targets_consistent_with_pipeline():
    sample = pd.read_csv(ROOT / "examples" / "sample_targets.csv")
    assert 30 <= len(sample) <= 50 and {"siren", "stage", "score", "score_detail"} <= set(sample)
