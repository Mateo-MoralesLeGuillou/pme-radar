"""Tableau de bord pme-radar. Lancer : streamlit run dashboard/app.py (aucune clé requise)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

from pme_radar.funnel import campaign_metrics, funnel_counts

ROOT = Path(__file__).resolve().parent.parent

st.set_page_config(page_title="pme-radar", page_icon="📡", layout="wide")
st.markdown(
    """<style>
    [data-testid="stSidebar"] {background:#1a1a30; border-right:1px solid #2c2c4d;}
    [data-testid="stSidebar"] h2 {font-size:1.1rem; letter-spacing:.08em; text-transform:uppercase;}
    h1 {font-weight:600;} h3 {border-bottom:1px solid #2c2c4d; padding-bottom:.4rem;}
    [data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stMetric"] {
        background:#1a1a30; border:1px solid #2c2c4d; border-radius:14px; padding:.6rem;}
    [data-testid="stSelectbox"] > div > div {border:1px solid #25c2f5; border-radius:6px;}
    </style>""",
    unsafe_allow_html=True,
)
st.title("📡 pme-radar : tableau de bord d'origination")

with st.sidebar:
    st.header("Données")
    live = (ROOT / "data" / "out" / "identified.csv").exists()
    use_live = st.checkbox("Utiliser le dernier run (data/out)", value=False, disabled=not live)
    if use_live:
        targets_path, campaign_path = ROOT / "data/out/identified.csv", ROOT / "data/out/campaign.csv"
    else:
        targets_path = ROOT / "examples/sample_targets.csv"
        campaign_path = ROOT / "examples/sample_campaign.csv"
        st.caption("Échantillon **synthétique** (examples/) : aucune donnée réelle.")

targets = pd.read_csv(targets_path, dtype={"siren": str})
campaign = (pd.read_csv(campaign_path, dtype=str).fillna("") if campaign_path.exists()
            else pd.DataFrame(columns=["siren", "campaign_id", "status"]))
thresholds = yaml.safe_load((ROOT / "config/campaign.yaml").read_text(encoding="utf-8"))

# --- Entonnoir -------------------------------------------------------------
st.subheader("Entonnoir")
f = funnel_counts(targets, campaign)
left, right = st.columns([3, 2])
fig = go.Figure(go.Funnel(y=f["étape"], x=f["nombre"], textinfo="value+percent previous",
                          marker={"color": ["#25c2f5", "#1fa3d1", "#1a85ad", "#146889", "#0f4a64"]}))
fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=340)
left.plotly_chart(fig, width="stretch")
view = f.assign(**{"conv. vs étape précédente": f["conversion_vs_précédente"].map(
    lambda v: "" if pd.isna(v) else f"{v:.0%}")})[["étape", "nombre", "conv. vs étape précédente"]]
right.dataframe(view, hide_index=True, width="stretch")
excluded = int((targets["stage"] == "excluded").sum())
right.caption(f"{excluded} entreprise(s) exclue(s) automatiquement (procédure collective BODACC).")

# --- Distribution des scores ----------------------------------------------
st.subheader("Distribution des scores")
scored = targets[targets["stage"] != "excluded"]
hist = px.histogram(scored, x="score", nbins=20, color="stage",
                    color_discrete_map={"qualified": "#25c2f5", "identified": "#4b4f7a"})
hist.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
hist.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=280, bargap=0.05)
st.plotly_chart(hist, width="stretch")

# --- Top 20 ---------------------------------------------------------------
st.subheader("Top 20 cibles")
top = scored.sort_values("score", ascending=False).head(20).reset_index(drop=True)
st.dataframe(top[["siren", "name", "naf_code", "city", "director_age", "revenue_last", "ebe_margin",
                  "net_margin",
                  "score", "stage"]], hide_index=True, width="stretch")
choice = st.selectbox("Détail du score", top["name"] if len(top) else [])
if choice:
    row = top[top["name"] == choice].iloc[0]
    st.markdown(f"**{row['score_summary']}**")
    detail = pd.DataFrame(json.loads(row["score_detail"]))
    st.dataframe(detail, hide_index=True, width="stretch")
    if isinstance(row.get("mini_thesis"), str):
        st.markdown("**Mini-thèse** : " + row["mini_thesis"].replace(" | ", " · "))
        st.markdown("**Signaux d'alerte** : " + str(row["red_flags"]).replace(" | ", " · "))

# --- Délivrabilité --------------------------------------------------------
st.subheader("KPI de campagne et délivrabilité")
m = campaign_metrics(campaign, thresholds)
if m.empty:
    st.info("Aucun suivi de campagne. Voir `pme-radar track`.")
for _, r in m.iterrows():
    st.markdown(f"**Campagne {r['campaign_id']}**")
    c1, c2, c3, c4 = st.columns(4)
    pct = lambda v: "n.d." if pd.isna(v) else f"{v:.1%}"  # noqa: E731
    c1.metric("Emails envoyés", int(r["sent"]))
    c2.metric("Taux de rebond", pct(r["bounce_rate"]))
    c3.metric("Taux de réponse", pct(r["reply_rate"]))
    c4.metric("Taux de RDV", pct(r["meeting_rate"]))
    if r["alerts"]:
        st.warning(r["alerts"])
st.caption("Audit DNS du domaine d'envoi : `pme-radar deliverability --domain exemple.fr`.")
