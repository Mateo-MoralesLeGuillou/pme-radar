from datetime import date

import pandas as pd
import pytest

from pme_radar import funnel, outreach
from pme_radar.deliverability import (
    check_dkim,
    check_dmarc,
    check_mx,
    check_spf,
    render_report,
    run_checks,
)
from pme_radar.enrich import normalize
from pme_radar.llm.analysis import analyze_company
from pme_radar.llm.mock_provider import MockLLM

from .conftest import AS_OF, ROOT, raw_company

T = {"bounce_rate": {"warning": 0.02, "critical": 0.05}, "reply_rate": {"warning_below": 0.05},
     "meeting_rate": {"warning_below": 0.01}, "min_sample": 20}


class FakeResolver:
    def __init__(self, txt=None, mx=None):
        self._txt, self._mx = txt or {}, mx or {}

    def txt(self, name):
        return self._txt.get(name, [])

    def mx(self, name):
        return self._mx.get(name, [])


# ---- délivrabilité ----
def test_mx():
    assert check_mx(FakeResolver(mx={"a.fr": ["mx.a.fr"]}), "a.fr").status == "ok"
    assert check_mx(FakeResolver(), "a.fr").status == "fail"


@pytest.mark.parametrize("rec,status", [
    (["v=spf1 include:_spf.google.com -all"], "ok"), (["v=spf1 include:x ~all"], "warn"),
    (["v=spf1 +all"], "fail"), (["v=spf1 -all", "v=spf1 ~all"], "fail"), ([], "fail"),
    (["google-site-verification=abc"], "fail")])
def test_spf(rec, status):
    assert check_spf(FakeResolver(txt={"a.fr": rec}), "a.fr").status == status


@pytest.mark.parametrize("rec,status", [
    (["v=DMARC1; p=reject; rua=mailto:d@a.fr"], "ok"), (["v=DMARC1; p=quarantine"], "warn"),
    (["v=DMARC1; p=none; rua=mailto:d@a.fr"], "warn"), (["v=DMARC1"], "fail"), ([], "fail")])
def test_dmarc(rec, status):
    assert check_dmarc(FakeResolver(txt={"_dmarc.a.fr": rec}), "a.fr").status == status


def test_dkim():
    r = FakeResolver(txt={"google._domainkey.a.fr": ["v=DKIM1; k=rsa; p=MIGf"]})
    assert check_dkim(r, "a.fr", "google").status == "ok"
    assert check_dkim(r, "a.fr", "other").status == "fail"
    assert check_dkim(r, "a.fr", None).status == "skipped"


def test_report_verdict():
    good = FakeResolver(txt={"a.fr": ["v=spf1 -all"], "_dmarc.a.fr": ["v=DMARC1; p=reject; rua=m"],
                             "s._domainkey.a.fr": ["p=KEY"]}, mx={"a.fr": ["mx"]})
    assert "Verdict : Prêt." in render_report("a.fr", run_checks("a.fr", "s", good))
    assert "NON PRÊT" in render_report("a.fr", run_checks("a.fr", None, FakeResolver()))


# ---- campagne ----
def camp(statuses, cid="c1"):
    return pd.DataFrame({"siren": [str(i) for i in range(len(statuses))], "campaign_id": cid,
                         "status": statuses})


def test_funnel_counts():
    targets = pd.DataFrame({"siren": list("abcd"), "stage": ["qualified", "qualified", "identified", "excluded"]})
    f = funnel.funnel_counts(targets, camp(["contacted", "replied", "meeting", "draft"]))
    assert f["nombre"].tolist() == [4, 2, 3, 2, 1]
    assert f.loc[1, "conversion_vs_précédente"] == 0.5


def test_funnel_without_campaign():
    f = funnel.funnel_counts(pd.DataFrame({"siren": ["a"], "stage": ["qualified"]}), None)
    assert f["nombre"].tolist() == [1, 1, 0, 0, 0]


def test_metrics_and_alerts():
    statuses = ["bounced"] * 3 + ["meeting"] * 2 + ["replied"] * 3 + ["contacted"] * 22
    m = funnel.campaign_metrics(camp(statuses), T).iloc[0]
    assert m["sent"] == 30 and m["bounce_rate"] == 0.1
    assert m["reply_rate"] == pytest.approx(5 / 27)
    assert "CRITIQUE" in m["alerts"]


def test_small_sample_not_judged():
    m = funnel.campaign_metrics(camp(["bounced"] * 5), T).iloc[0]
    assert "échantillon insuffisant" in m["alerts"]


def test_low_reply_alert_and_empty():
    m = funnel.campaign_metrics(camp(["contacted"] * 40), T).iloc[0]
    assert "réponse" in m["alerts"] and "RDV" in m["alerts"]
    assert funnel.campaign_metrics(pd.DataFrame(), T).empty


def test_campaign_tracking(tmp_path, scoring_cfg, thesis):
    c = analyze_company(normalize(raw_company(), AS_OF), MockLLM())
    path = tmp_path / "campaign.csv"
    outreach.init_campaign([c], "c1", path)
    outreach.init_campaign([c], "c2", path)  # idempotent
    df = outreach.load_campaign(path)
    assert len(df) == 1 and df.loc[0, "status"] == "draft"
    outreach.update_status(path, c.siren, "contacted", date(2026, 11, 5))
    outreach.update_status(path, c.siren, "meeting", date(2026, 11, 20), note="visio")
    row = outreach.load_campaign(path).iloc[0]
    assert (row.status, row.sent_date, row.meeting_date, row.note) == (
        "meeting", "2026-11-05", "2026-11-20", "visio")
    with pytest.raises(ValueError):
        outreach.update_status(path, c.siren, "sent")
    with pytest.raises(KeyError):
        outreach.update_status(path, "000", "contacted")


def test_drafts_marked_for_human_review():
    c = analyze_company(normalize(raw_company(), AS_OF), MockLLM())
    df = outreach.drafts_frame([c, normalize(raw_company(siren="2"), AS_OF)])
    assert len(df) == 1 and "RELIRE" in df.loc[0, "review_status"]


def test_sample_campaign_file_is_valid():
    df = pd.read_csv(ROOT / "examples" / "sample_campaign.csv", dtype=str).fillna("")
    assert set(df["status"]) <= set(outreach.STATUSES)
