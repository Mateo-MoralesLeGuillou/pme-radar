"""Tableau de bord pme-radar. Lancer : streamlit run dashboard/app.py (aucune clé requise)."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from pme_radar.funnel import campaign_metrics, funnel_counts

ROOT = Path(__file__).resolve().parent.parent
CYAN, CYAN_DIM, AMBER, RED = "#25c2f5", "#1a6f8f", "#ffb547", "#ff6b81"
TEXT, MUTED, GRID, CARD = "#e8eaf6", "#9aa0c8", "#2c2c4d", "#1a1a30"
FONT = "Inter, 'Source Sans Pro', sans-serif"
DEPARTMENTS = {
    "75": "Paris",
    "77": "Seine-et-Marne",
    "78": "Yvelines",
    "91": "Essonne",
    "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne",
    "95": "Val-d'Oise",
}
LOGO64 = base64.b64encode((ROOT / "docs/img/logo.svg").read_bytes()).decode()
STAGES = {"qualified": "Qualifiée", "identified": "Identifiée", "excluded": "Exclue"}
COLUMNS = [
    "siren", "name", "naf_code", "naf_label", "city", "department", "headcount_band",
    "company_age_years", "director_age", "revenue_last", "ebe_margin", "net_margin",
    "accounts_available", "score", "stage", "score_summary", "score_detail", "mini_thesis",
    "red_flags", "email_subject",
]  # fmt: skip

st.set_page_config(
    page_title="pme-radar · origination",
    page_icon=str(ROOT / "docs/img/logo.png"),
    layout="wide",
)
st.markdown(
    f"""<style>
    html, body, [class*="css"], .stMarkdown, .stDataFrame {{font-family:{FONT};}}
    [data-testid="stSidebar"] {{background:{CARD}; border-right:1px solid {GRID};}}
    [data-testid="stSidebar"] h2 {{font-size:.8rem; letter-spacing:.12em; text-transform:uppercase;
        color:{MUTED};}}
    h3 {{font-weight:650; letter-spacing:-.01em;}}
    [data-testid="stMetric"] {{background:linear-gradient(180deg,#20203d 0%,{CARD} 100%);
        border:1px solid {GRID}; border-top:3px solid {CYAN}; border-radius:16px; padding:.9rem 1rem;}}
    [data-testid="stMetricLabel"] p {{text-transform:uppercase; letter-spacing:.07em; font-size:.74rem;
        color:{MUTED}; font-weight:600;}}
    [data-testid="stMetricValue"] {{font-size:2rem; font-weight:700; letter-spacing:-.02em;}}
    [data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {{background:{CARD};
        border:1px solid {GRID}; border-radius:16px; padding:.6rem;}}
    button[data-baseweb="tab"] p {{font-size:1rem; font-weight:600;}}
    .pr-hero {{display:flex; align-items:center; gap:18px; margin:.2rem 0 1.2rem;}}
    .pr-hero img {{width:58px; height:58px; filter:drop-shadow(0 6px 18px rgba(37,194,245,.35));}}
    .pr-title {{font-size:2.1rem; line-height:1.1; font-weight:750; letter-spacing:-.03em;
        color:{TEXT};}}
    .pr-title span {{color:{CYAN};}}
    .pr-hero p {{margin:.15rem 0 0; color:{MUTED}; font-size:.98rem;}}
    .pr-badge {{margin-left:auto; padding:6px 14px; border-radius:999px; font-size:.78rem;
        font-weight:700; letter-spacing:.06em; text-transform:uppercase;}}
    .pr-badge.demo {{color:{AMBER}; border:1px solid rgba(255,181,71,.45);
        background:rgba(255,181,71,.08);}}
    .pr-badge.live {{color:{CYAN}; border:1px solid rgba(37,194,245,.45);
        background:rgba(37,194,245,.08);}}
    .pr-card {{background:{CARD}; border:1px solid {GRID}; border-radius:16px; padding:1.1rem 1.3rem;
        margin-bottom:.8rem;}}
    .pr-card h4 {{margin:0 0 .2rem; font-size:1.25rem; font-weight:700;}}
    .pr-card .sub {{color:{MUTED}; font-size:.9rem; margin-bottom:.6rem;}}
    .pr-kv {{display:grid; grid-template-columns:auto 1fr; gap:.35rem 1rem; font-size:.92rem;}}
    .pr-kv b {{color:{MUTED}; font-weight:500;}}
    .pr-chip {{display:inline-block; padding:5px 12px; margin:0 8px 8px 0; border-radius:999px;
        font-size:.85rem; color:{AMBER}; background:rgba(255,181,71,.10);
        border:1px solid rgba(255,181,71,.35);}}
    .pr-mail {{background:#14142a; border:1px solid {GRID}; border-radius:12px; padding:1rem 1.2rem;
        font-size:.92rem; line-height:1.55; color:{TEXT};}}
    .pr-review {{display:inline-block; font-size:.75rem; font-weight:700; letter-spacing:.06em;
        color:{RED}; border:1px solid rgba(255,107,129,.45); border-radius:6px; padding:3px 8px;
        margin-bottom:.6rem;}}
    .pr-foot {{color:{MUTED}; font-size:.8rem;}}
    </style>""",
    unsafe_allow_html=True,
)


def styled(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=TEXT, size=13),
        margin=dict(l=0, r=0, t=30, b=0),
        height=height,
        hoverlabel=dict(font_family=FONT),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID)
    return fig


def esc(v: object) -> str:
    """Texte inséré dans du HTML : échappé, et vide si la valeur manque."""
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else html.escape(str(v))


def fmt_pct(v: float) -> str:
    return "n.d." if pd.isna(v) else f"{v:.0%}"


def fmt_m(v: float) -> str:
    return "n.d." if pd.isna(v) else f"{v / 1e6:.1f} M€".replace(".", ",")


# --- Données -----------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<img src='data:image/svg+xml;base64,{LOGO64}' width='52' alt='pme-radar'>",
        unsafe_allow_html=True,
    )
    st.header("Données")
    live = (ROOT / "data" / "out" / "identified.csv").exists()
    use_live = st.checkbox("Utiliser le dernier run (data/out)", value=False, disabled=not live)
    base = ROOT / "data/out" if use_live else ROOT / "examples"
    targets_path = base / ("identified.csv" if use_live else "sample_targets.csv")
    campaign_path = base / ("campaign.csv" if use_live else "sample_campaign.csv")
    drafts_path = base / ("drafts.csv" if use_live else "sample_drafts.csv")
    if not use_live:
        st.caption("Échantillon **synthétique** (examples/) : aucune donnée réelle.")

targets = pd.read_csv(targets_path, dtype={"siren": str, "department": str, "naf_code": str})
targets = targets.reindex(columns=list(dict.fromkeys([*targets.columns, *COLUMNS])))  # anciens CSV
campaign = (
    pd.read_csv(campaign_path, dtype=str).fillna("")
    if campaign_path.exists()
    else pd.DataFrame(columns=["siren", "campaign_id", "status"])
)
drafts = (
    pd.read_csv(drafts_path, dtype={"siren": str})
    if drafts_path.exists()
    else pd.DataFrame(columns=["siren", "subject", "body"])
)
thresholds = yaml.safe_load((ROOT / "config/campaign.yaml").read_text(encoding="utf-8"))
threshold = yaml.safe_load((ROOT / "config/scoring.yaml").read_text(encoding="utf-8"))[
    "qualified_threshold"
]

with st.sidebar:
    st.header("Filtres")
    depts = sorted(targets["department"].dropna().unique())
    nafs = sorted(targets["naf_code"].dropna().unique())
    sel_depts = st.multiselect(
        "Départements", depts, format_func=lambda d: f"{d} · {DEPARTMENTS.get(d, d)}",
        placeholder="Tous",
    )  # fmt: skip
    sel_nafs = st.multiselect("Codes NAF", nafs, placeholder="Tous")
    min_score = st.slider("Score minimum", 0, 100, 0, step=5)
    only_accounts = st.checkbox("Comptes publiés uniquement", value=False)
    st.divider()
    st.markdown(
        "<div class='pr-foot'>Score déterministe et explicable · brouillons à relire, "
        "aucun envoi automatique · <a href='https://github.com/Mateo-MoralesLeGuillou/pme-radar'>"
        "code source</a></div>",
        unsafe_allow_html=True,
    )

mask = pd.Series(True, index=targets.index)
if sel_depts:
    mask &= targets["department"].isin(sel_depts)
if sel_nafs:
    mask &= targets["naf_code"].isin(sel_nafs)
if min_score:
    mask &= targets["score"].fillna(0) >= min_score
if only_accounts:
    mask &= targets["accounts_available"].astype(str).str.lower().eq("true")
targets = targets[mask]
campaign = campaign[campaign["siren"].isin(targets["siren"])]  # entonnoir sur la population filtrée

# --- En-tête et KPI ----------------------------------------------------------
badge = (
    "<span class='pr-badge live'>Dernier run</span>"
    if use_live
    else "<span class='pr-badge demo'>Échantillon synthétique</span>"
)
st.markdown(
    f"""<div class="pr-hero"><img src="data:image/svg+xml;base64,{LOGO64}" alt="">
    <div><div class="pr-title">pme<span>-</span>radar</div>
    <p>Origination search fund · PME transmissibles repérées dans l'open data</p></div>
    {badge}</div>""",
    unsafe_allow_html=True,
)

f = funnel_counts(targets, campaign)
n_total, n_q = len(targets), int((targets["stage"] == "qualified").sum())
med = targets.loc[targets["stage"] != "excluded", "score"].median()
k = st.columns(5)
k[0].metric("Entreprises analysées", n_total)
k[1].metric("Qualifiées", n_q, help=f"Score ≥ {threshold}/100 (config/scoring.yaml)")
k[2].metric("Score médian", "n.d." if pd.isna(med) else f"{med:.0f}/100")
k[3].metric("Contactées", int(f.loc[f["étape"] == "Contactées", "nombre"].iloc[0]))
k[4].metric("RDV obtenus", int(f.loc[f["étape"] == "RDV", "nombre"].iloc[0]))
if targets.empty:
    st.warning("Aucune entreprise ne correspond aux filtres.")
    st.stop()

tab_overview, tab_targets, tab_campaign = st.tabs(["Vue d'ensemble", "Cibles", "Campagne"])

# --- Vue d'ensemble ----------------------------------------------------------
with tab_overview:
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.subheader("Entonnoir d'origination")
        fig = go.Funnel(
            y=f["étape"],
            x=f["nombre"],
            textinfo="value+percent previous",
            marker={"color": [CYAN, "#1fa3d1", "#1a85ad", "#146889", "#0f4a64"]},
            connector={"line": {"color": GRID, "width": 1}},
        )
        st.plotly_chart(styled(go.Figure(fig), 340), width="stretch")
        excluded = int((targets["stage"] == "excluded").sum())
        st.caption(
            f"{excluded} entreprise(s) exclue(s) automatiquement (procédure collective BODACC)."
        )
    with right:
        st.subheader("Qualifiées par département")
        q = targets[targets["stage"] == "qualified"]
        by_dept = (
            q["department"].map(lambda d: DEPARTMENTS.get(d, d)).value_counts().sort_values()
            if len(q)
            else pd.Series(dtype=int)
        )
        bar = go.Bar(
            x=by_dept.values,
            y=by_dept.index,
            orientation="h",
            marker={"color": CYAN},
            text=by_dept.values,
            textposition="outside",
            cliponaxis=False,
        )
        fig_dept = styled(go.Figure(bar), 340)
        fig_dept.update_xaxes(
            visible=False, range=[0, max(by_dept.max() if len(by_dept) else 1, 1) * 1.2]
        )
        st.plotly_chart(fig_dept, width="stretch")

    st.subheader("Distribution des scores")
    scored = targets[targets["stage"] != "excluded"]
    hist = go.Figure()
    for stage, color in (("identified", "#4b4f7a"), ("qualified", CYAN)):
        sub = scored[scored["stage"] == stage]
        hist.add_trace(
            go.Histogram(x=sub["score"], name=STAGES[stage], marker_color=color, xbins=dict(size=5))
        )
    hist.add_vline(
        x=threshold,
        line_dash="dash",
        line_color=AMBER,
        annotation_text=f"Seuil de qualification : {threshold}",
        annotation_font_color=AMBER,
        annotation_position="top left",
    )
    hist.update_layout(
        barmode="stack",
        bargap=0.08,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, title_text=""),
        xaxis_title="Score /100",
        yaxis_title="Entreprises",
    )
    st.plotly_chart(styled(hist, 300), width="stretch")

    if len(q):
        st.subheader("Profil type d'une cible qualifiée")
        p = st.columns(4)
        p[0].metric("Âge médian du dirigeant", f"{q['director_age'].median():.0f} ans")
        p[1].metric("CA médian", fmt_m(q["revenue_last"].median()))
        p[2].metric("Marge d'EBE médiane", fmt_pct(q["ebe_margin"].median()))
        p[3].metric("Ancienneté médiane", f"{q['company_age_years'].median():.0f} ans")

# --- Cibles ------------------------------------------------------------------
with tab_targets:
    st.subheader("Meilleures cibles")
    top = scored.sort_values("score", ascending=False).head(20).reset_index(drop=True)
    st.dataframe(
        top.assign(revenue_m=top["revenue_last"] / 1e6)[
            [
                "siren",
                "name",
                "naf_code",
                "city",
                "director_age",
                "revenue_m",
                "ebe_margin",
                "net_margin",
                "score",
                "stage",
            ]
        ],  # fmt: skip
        hide_index=True,
        width="stretch",
        column_config={
            "siren": "SIREN",
            "name": "Entreprise",
            "naf_code": "NAF",
            "city": "Ville",
            "director_age": st.column_config.NumberColumn("Âge dirigeant", format="%d ans"),
            "revenue_m": st.column_config.NumberColumn("CA", format="%.1f M€"),
            "ebe_margin": st.column_config.NumberColumn("Marge EBE", format="percent"),
            "net_margin": st.column_config.NumberColumn("Marge nette", format="percent"),
            "score": st.column_config.NumberColumn("Score", format="%d/100"),
            "stage": "Statut",
        },
    )
    st.download_button(
        "Télécharger la sélection (CSV)",
        targets.to_csv(index=False).encode("utf-8"),
        file_name="pme-radar_selection.csv",
        mime="text/csv",
    )

    labels = {f"{r['name']} · {r['siren']}": r["siren"] for _, r in top.iterrows()}
    choice = st.selectbox("Fiche cible", list(labels))
    if choice:
        row = top[top["siren"] == labels[choice]].iloc[0]
        c1, c2 = st.columns([2, 3], gap="medium")
        with c1:
            age = "n.d." if pd.isna(row["director_age"]) else f"{row['director_age']:.0f} ans"
            seniority = (
                "n.d."
                if pd.isna(row["company_age_years"])
                else f"{row['company_age_years']:.0f} ans"
            )
            st.markdown(
                f"""<div class="pr-card"><h4>{esc(row["name"])}</h4>
                <div class="sub">{esc(row["naf_label"])} · {esc(row["city"])} ({esc(row["department"])})</div>
                <div class="pr-kv"><b>SIREN</b><span>{row["siren"]}</span>
                <b>Dirigeant</b><span>{age}</span><b>Ancienneté</b><span>{seniority}</span>
                <b>CA</b><span>{fmt_m(row["revenue_last"])}</span>
                <b>Marge d'EBE</b><span>{fmt_pct(row["ebe_margin"])}</span>
                <b>Marge nette</b><span>{fmt_pct(row["net_margin"])}</span></div></div>""",
                unsafe_allow_html=True,
            )
            gauge = go.Indicator(
                mode="gauge+number",
                value=float(row["score"]),
                number={"suffix": "/100", "font": {"size": 40}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": MUTED},
                    "bar": {"color": CYAN, "thickness": 0.28},
                    "bgcolor": "rgba(0,0,0,0)",
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, threshold], "color": GRID},
                        {"range": [threshold, 100], "color": "rgba(37,194,245,.16)"},
                    ],
                    "threshold": {"line": {"color": AMBER, "width": 3}, "value": threshold},
                },
            )
            fig_gauge = styled(go.Figure(gauge), 250)
            fig_gauge.update_layout(margin=dict(l=45, r=45, t=20, b=10))
            st.plotly_chart(fig_gauge, width="stretch")
        with c2:
            st.markdown(f"**{row['score_summary']}**")
            if isinstance(row["score_detail"], str):
                detail = pd.DataFrame(json.loads(row["score_detail"]))
                crit = detail[detail["max"] > 0].iloc[::-1]
                pens = detail[detail["max"] == 0]
                bars = go.Figure()
                bars.add_trace(
                    go.Bar(
                        y=crit["critère"],
                        x=crit["max"],
                        orientation="h",
                        marker_color=GRID,
                        hoverinfo="skip",
                        showlegend=False,
                    )  # fmt: skip
                )
                bars.add_trace(
                    go.Bar(
                        y=crit["critère"],
                        x=crit["points"],
                        orientation="h",
                        marker_color=CYAN,
                        text=[
                            f"{p:g}/{m:g} · {d}"
                            for p, m, d in zip(
                                crit["points"], crit["max"], crit["détail"], strict=True
                            )
                        ],
                        textposition="outside",
                        cliponaxis=False,
                        showlegend=False,
                    )
                )
                bars.update_layout(barmode="overlay", bargap=0.35)
                bars.update_xaxes(visible=False, range=[0, 50])
                st.plotly_chart(styled(bars, 360), width="stretch")
                for _, pen in pens.iterrows():
                    st.markdown(
                        f"<span class='pr-chip' style='color:{RED};border-color:rgba(255,107,129,.4);"
                        f"background:rgba(255,107,129,.08)'>{esc(pen['critère'])} {pen['points']:g} · "
                        f"{esc(pen['détail'])}</span>",
                        unsafe_allow_html=True,
                    )

        a1, a2 = st.columns(2, gap="medium")
        with a1:
            st.markdown("##### Mini-thèse")
            if isinstance(row.get("mini_thesis"), str):
                st.markdown("\n".join(f"- {t}" for t in row["mini_thesis"].split(" | ")))
            else:
                st.caption("Non générée : lancer `pme-radar draft`.")
            st.markdown("##### Signaux d'alerte")
            if isinstance(row.get("red_flags"), str):
                chips = "".join(
                    f"<span class='pr-chip'>{esc(t)}</span>" for t in row["red_flags"].split(" | ")
                )
                st.markdown(chips, unsafe_allow_html=True)
        with a2:
            st.markdown("##### Brouillon d'approche")
            mail = drafts[drafts["siren"] == row["siren"]]
            if len(mail):
                st.markdown(
                    f"<span class='pr-review'>À RELIRE · AUCUN ENVOI AUTOMATIQUE</span>"
                    f"<div class='pr-mail'><b>Objet : {esc(mail.iloc[0]['subject'])}</b><br><br>"
                    f"{esc(mail.iloc[0]['body']).replace(chr(10), '<br>')}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Brouillon produit pour le top N uniquement (`pme-radar draft`).")

# --- Campagne ----------------------------------------------------------------
with tab_campaign:
    st.subheader("KPI de campagne et délivrabilité")
    m = campaign_metrics(campaign, thresholds)
    if m.empty:
        st.info("Aucun suivi de campagne. Voir `pme-radar track`.")
    for _, r in m.iterrows():
        st.markdown(f"**Campagne {r['campaign_id']}**")
        c = st.columns(4)
        pct = lambda v: "n.d." if pd.isna(v) else f"{v:.1%}".replace(".", ",")  # noqa: E731
        c[0].metric("Emails envoyés", int(r["sent"]))
        c[1].metric("Taux de rebond", pct(r["bounce_rate"]))
        c[2].metric("Taux de réponse", pct(r["reply_rate"]))
        c[3].metric("Taux de RDV", pct(r["meeting_rate"]))
        if r["alerts"]:
            st.warning(r["alerts"])
    if len(campaign):
        st.subheader("Suivi des contacts")
        order = {
            "draft": "Brouillon", "contacted": "Contacté", "replied": "A répondu",
            "meeting": "RDV", "declined": "Décliné", "bounced": "Rebond",
        }  # fmt: skip
        counts = campaign["status"].value_counts().reindex(list(order), fill_value=0)
        counts.index = [order[s] for s in counts.index]
        colors = [GRID, "#1a85ad", CYAN, "#2ee6a6", AMBER, RED]
        status_bar = go.Bar(
            x=counts.index, y=counts.values, marker_color=colors, text=counts.values,
            textposition="outside", cliponaxis=False,
        )  # fmt: skip
        fig_status = styled(go.Figure(status_bar), 280)
        fig_status.update_layout(margin=dict(l=0, r=0, t=30, b=40))
        st.plotly_chart(fig_status, width="stretch")
        names = targets.set_index("siren")["name"]
        st.dataframe(
            campaign.assign(name=campaign["siren"].map(names))[
                ["name", "status", "sent_date", "replied_date", "meeting_date", "note"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "name": "Entreprise",
                "status": "Statut",
                "sent_date": "Envoi",
                "replied_date": "Réponse",
                "meeting_date": "RDV",
                "note": "Note",
            },
        )
    st.caption("Audit DNS du domaine d'envoi : `pme-radar deliverability --domain exemple.fr`.")
