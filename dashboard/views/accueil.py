"""Accueil : l'essentiel en une page (chiffres clés, actions du jour, meilleures cibles)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import ui

data = ui.load()
ui.require_data(data)
t = data.table

n = len(t)
qualified = int((t["stage"] == "qualified").sum())
tones = t["tone"].value_counts()
go_n = int(tones.get("go", 0))
cc = ui.campaign_counts(data)

st.html(
    f"""<div class="pr-hero"><div class="k">Pipeline d'origination · {ui.esc(data.source)}</div>
    <h2><b>{go_n}</b> cible{"s" if go_n > 1 else ""} prête{"s" if go_n > 1 else ""} à être approchée{"s" if go_n > 1 else ""}</h2>
    <p>Sur {n} PME analysées, {qualified} sont qualifiées (score ≥ {data.threshold}/100).
    {cc["sent"]} prise(s) de contact, {cc["replied"]} réponse(s), {cc["meetings"]} rendez-vous.</p></div>"""
)

k = st.columns(5)
k[0].metric(
    "Entreprises analysées",
    n,
    border=True,
    icon=":material/radar:",
    help="Sociétés notées sur la zone et les secteurs de la thèse (config/thesis.yaml).",
)
k[1].metric(
    "Qualifiées",
    qualified,
    border=True,
    icon=":material/verified:",
    help=f"Score ≥ {data.threshold}/100 : profil transmissible, à examiner.",
)
k[2].metric(
    "À approcher",
    go_n,
    border=True,
    icon=":material/send:",
    help="Qualifiées et sans signal bloquant : le premier contact peut être préparé.",
)
k[3].metric(
    "Contactées",
    cc["sent"],
    border=True,
    icon=":material/forward_to_inbox:",
    help="Emails envoyés à la main (suivi : page Prises de contact).",
)
k[4].metric("Rendez-vous", cc["meetings"], border=True, icon=":material/event_available:",
            help="Rendez-vous obtenus avec un dirigeant.")  # fmt: skip

with st.container(horizontal=True, gap="small", key="pr-actions"):
    st.page_link(ui.P_COMPANY, label="Rechercher une entreprise", icon=":material/search:")
    st.page_link(ui.P_TARGETS, label="Filtrer les cibles", icon=":material/filter_alt:")
    st.page_link(ui.P_CAMPAIGN, label="Suivre les contacts", icon=":material/forward_to_inbox:")
    st.page_link(
        ui.P_REPORTS, label="Rapport de pré-due diligence", icon=":material/picture_as_pdf:"
    )
    st.page_link(ui.P_HELP, label="Comprendre un terme", icon=":material/help:")

# ---------------------------------------------------------------- à faire maintenant
st.subheader("À faire maintenant")
a1, a2, a3 = st.columns(3, gap="medium")
with a1, st.container(border=True, height="stretch"):
    st.markdown("**:green[:material/send:] Prêtes à approcher**")
    st.caption("Qualifiées, sans signal bloquant, pas encore contactées.")
    ready = t[(t["tone"] == "go") & t["status"].isin(["", "draft"])].head(5)
    if ready.empty:
        st.caption("Aucune pour l'instant.")
    for r in ready.itertuples():
        ui.company_link(r.siren, r.name)
        draft = "brouillon prêt" if r.has_draft else "brouillon à générer"
        st.html(f'<div class="pr-item"><span>{r.score:.0f}/100 · CA {ui.m_eur(r.revenue)} · {ui.esc(r.city)}</span>'
                f"<span>{draft}</span></div>")  # fmt: skip
with a2, st.container(border=True, height="stretch"):
    st.markdown("**:orange[:material/reply:] Réponses et relances**")
    st.caption(f"Réponses reçues, ou envois sans réponse depuis {ui.FOLLOW_UP_DAYS} jours ou plus.")
    todo = ui.follow_ups(data).head(5)
    if todo.empty:
        st.caption("Rien à traiter.")
    for r in todo.itertuples():
        ui.company_link(r.siren, r.name)
        when = f"envoyé il y a {r.days:.0f} j" if r.days == r.days else ""
        st.html(f'<div class="pr-item"><span>{ui.esc(r.action)}</span><span>{when}</span></div>')
with a3, st.container(border=True, height="stretch"):
    st.markdown("**:violet[:material/description:] À documenter**")
    st.caption("Sous le seuil faute de données : un échange peut les qualifier.")
    doc = t[t["tone"] == "doc"].sort_values("ceiling", ascending=False).head(5)
    if doc.empty:
        st.caption("Aucune.")
    for r in doc.itertuples():
        ui.company_link(r.siren, r.name)
        st.html(f'<div class="pr-item"><span>score {r.score:.0f} → jusqu\'à {r.ceiling:.0f}</span>'
                f"<span>fiabilité {r.confidence:.0%}</span></div>")  # fmt: skip

# ---------------------------------------------------------------- meilleures cibles
st.subheader("Meilleures cibles")
st.caption(
    "Cliquez sur « Ouvrir » pour la fiche complète : finances, valorisation, due diligence, brouillon."
)
top = ui.targets_frame(t[t["stage"] != "excluded"].head(10)).reset_index(drop=True)
cols = ["open", "name", "city", "director_age", "revenue_m", "ebe_margin", "score", "reco_tag",
        "ev_mid_m", "status_label"]  # fmt: skip
config = ui.targets_columns(data.threshold) | {"open": ui.open_button_column(top, "home_open")}
st.dataframe(
    top[cols],
    hide_index=True,
    width="stretch",
    placeholder="n.d.",
    column_config=config,
    key="home_top",
)

# ---------------------------------------------------------------- vues d'ensemble
st.subheader("Vue d'ensemble")
g1, g2 = st.columns(2, gap="medium")
with g1, st.container(border=True):
    st.markdown("**Entonnoir d'origination**")
    steps = [("Analysées", n), ("Qualifiées", qualified), ("À approcher", go_n),
             ("Contactées", cc["sent"]), ("Ont répondu", cc["replied"]), ("RDV", cc["meetings"])]  # fmt: skip
    funnel = go.Funnel(
        y=[s for s, _ in steps], x=[v for _, v in steps], textinfo="value+percent previous",
        marker={"color": [ui.CYAN, "#1fa3d1", ui.GREEN, "#1a85ad", "#146889", ui.AMBER]},
        connector={"line": {"color": ui.GRID, "width": 1}},
        hovertemplate="%{y} : %{x}<extra></extra>",
    )  # fmt: skip
    ui.chart(go.Figure(funnel), 300, key="home_funnel")
with g2, st.container(border=True):
    st.markdown("**Recommandations**")
    counts = t["reco"].value_counts().reindex(ui.RECO_LABELS).fillna(0).astype(int)
    ui.chart(ui.hbar(list(counts.index), list(counts.values), ui.RECO_HEX), 300, key="home_reco")
g3, g4 = st.columns(2, gap="medium")
with g3, st.container(border=True):
    st.markdown("**Distribution des scores**")
    scored = t[t["stage"] != "excluded"]
    hist = go.Figure()
    for stage, color, name in (
        ("identified", "#3b4a72", "Non qualifiées"),
        ("qualified", ui.CYAN, "Qualifiées"),
    ):
        sub = scored[scored["stage"] == stage]
        hist.add_trace(go.Histogram(x=sub["score"], name=name, marker_color=color, xbins={"size": 5},
                                    hovertemplate="score %{x} : %{y}<extra></extra>"))  # fmt: skip
    hist.add_vline(x=data.threshold, line_dash="dash", line_color=ui.AMBER,
                   annotation_text=f"seuil {data.threshold}", annotation_font_color=ui.AMBER)  # fmt: skip
    hist.update_layout(barmode="stack", bargap=0.08)
    hist.update_xaxes(title="Score /100")
    ui.chart(hist, 280, key="home_hist")
with g4, st.container(border=True):
    st.markdown("**Qualifiées par département**")
    q = t[t["stage"] == "qualified"]
    by_dept = q["dept_label"].value_counts()
    if by_dept.empty:
        st.caption("Aucune cible qualifiée.")
    else:
        ui.chart(ui.hbar(list(by_dept.index), list(by_dept.values)), 280, key="home_dept")
