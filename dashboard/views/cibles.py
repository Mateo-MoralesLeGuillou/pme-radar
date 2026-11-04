"""Cibles : filtrer, trier, comparer, puis ouvrir une fiche ou exporter une sélection."""

from __future__ import annotations

import streamlit as st
import ui

from pme_radar import labels
from pme_radar.report import build_report

data = ui.load()
t = data.table
ui.require_data(data)
ui.page_title(
    "Cibles",
    "Toutes les entreprises notées. Filtrez, triez, puis « Ouvrir » pour la fiche complète.",
)

PRESETS = {
    "Toutes": lambda df: df,
    "À approcher": lambda df: df[df["tone"] == "go"],
    "À creuser": lambda df: df[df["tone"] == "dig"],
    "À documenter": lambda df: df[df["tone"] == "doc"],
    "Qualifiées": lambda df: df[df["stage"] == "qualified"],
    "Dirigeant 60 ans et +": lambda df: df[df["director_age"].fillna(0) >= 60],
    "Pas encore contactées": lambda df: df[
        df["status"].isin(["", "draft"]) & (df["stage"] != "excluded")
    ],
}
preset = st.pills("Sélections rapides", list(PRESETS), default="Toutes", key="preset", required=True,
                  help="Raccourcis vers les listes les plus utiles.")  # fmt: skip

f1, f2, f3 = st.columns([2.2, 1.6, 1.4], vertical_alignment="bottom")
query = f1.text_input("Rechercher", key="q", placeholder="Nom, ville, SIREN, dirigeant, activité…",
                      help="Recherche dans le nom, la ville, le SIREN, le dirigeant et l'activité.")  # fmt: skip
depts = sorted(t["department"].dropna().unique())
sel_depts = f2.multiselect("Départements", depts, key="depts", placeholder="Tous",
                           format_func=lambda x: f"{x} · {labels.DEPARTMENTS.get(x, x)}")  # fmt: skip
min_score = f3.slider("Score minimum", 0, 100, 0, step=5, key="min_score",
                      help=f"Une cible est qualifiée à partir de {data.threshold}/100.")  # fmt: skip
with st.expander("Plus de filtres", icon=":material/tune:"):
    g1, g2, g3 = st.columns(3)
    recos = g1.multiselect("Recommandations", ui.RECO_LABELS, key="recos", placeholder="Toutes")
    nafs = sorted(t["naf_label"].dropna().unique())
    sel_nafs = g2.multiselect("Activités", nafs, key="nafs", placeholder="Toutes")
    max_rev = float(round(max(t["revenue"].fillna(0).max() / 1e6, 1.0) + 0.5))
    rev = g3.slider("Chiffre d'affaires (M€)", 0.0, max_rev, (0.0, max_rev),
                    step=0.5, key="rev")  # fmt: skip
    h1, h2, h3 = st.columns(3)
    age_min = h1.slider("Âge minimal du dirigeant", 30, 80, 30, key="age_min")
    accounts = h2.toggle("Comptes publiés uniquement", key="accounts")
    hide_out = h3.toggle("Masquer les écartées", value=True, key="hide_out")

df = PRESETS[preset or "Toutes"](t)
if query:
    hay = (df["name"] + " " + df["city"] + " " + df["siren"] + " " + df["director"] + " "
           + df["naf_label"]).str.lower()  # fmt: skip
    df = df[hay.str.contains(query.strip().lower(), regex=False)]
if sel_depts:
    df = df[df["department"].isin(sel_depts)]
if min_score:
    df = df[df["score"] >= min_score]
if recos:
    df = df[df["reco"].isin(recos)]
if sel_nafs:
    df = df[df["naf_label"].isin(sel_nafs)]
lo, hi = rev
if lo > 0 or hi < max_rev:
    df = df[df["revenue"].fillna(-1).between(lo * 1e6, hi * 1e6)]
if age_min > 30:
    df = df[df["director_age"].fillna(0) >= age_min]
if accounts:
    df = df[df["accounts"]]
if hide_out:
    df = df[df["tone"] != "out"]

SORTS = {
    "Score (meilleures d'abord)": ("score", False),
    "Chiffre d'affaires": ("revenue", False),
    "Âge du dirigeant": ("director_age", False),
    "Valeur d'entreprise": ("ev_mid", False),
    "Nom (A → Z)": ("name", True),
}
r1, r2 = st.columns([3, 1.3], vertical_alignment="bottom")
r1.markdown(f"**{len(df)} entreprise{'s' if len(df) > 1 else ''}** sur {len(t)}")
sort = r2.selectbox("Trier par", list(SORTS), key="sort", label_visibility="collapsed")
col, asc = SORTS[sort]
df = df.sort_values(col, ascending=asc, na_position="last").reset_index(drop=True)

if df.empty:
    st.warning("Aucune entreprise ne correspond aux filtres : élargissez la recherche.")
    st.stop()

view = ui.targets_frame(df)
cols = ["open", "name", "city", "naf_label", "director_age", "revenue_m", "ebe_margin",
        "score", "reco_tag", "ev_mid_m", "equity_m", "status_label"]  # fmt: skip
config = ui.targets_columns(data.threshold) | {"open": ui.open_button_column(view, "targets_open")}
event = st.dataframe(view[cols], hide_index=True, width="stretch", placeholder="n.d.", height=min(38 + 35 * len(view), 620),
                     column_config=config, key="targets_table", on_select="rerun",
                     selection_mode="multi-row")  # fmt: skip
st.caption(
    "Cochez des lignes pour exporter ou produire le rapport d'une sélection ; « Ouvrir » affiche la fiche."
)

picked = view.iloc[list(event.selection.rows)] if event and event.selection.rows else view
scope = f"{len(picked)} sélectionnée(s)" if len(picked) < len(view) else f"les {len(view)} filtrées"
footer = data.campaign_cfg.get("compliance_footer")


def _report() -> str:
    html, _ = build_report(data.companies, data.scoring, data.thesis, campaign=data.campaign,
                           sirens=list(picked["siren"]), footer=footer)  # fmt: skip
    return html


export = df[df["siren"].isin(picked["siren"])].drop(columns=["_order"], errors="ignore")
ui.report_downloads(_report, "rapport_selection", f"Rapport de pré-DD ({scope})", disabled=len(picked) > 60,
                    help_="Un dossier de pré-due diligence par entreprise (60 au plus).")  # fmt: skip
e2, e3 = st.columns(2)
e2.download_button(f"Excel ({scope})", export.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                   file_name="cibles_pme-radar.csv", mime="text/csv", icon=":material/grid_on:",
                   width="stretch", on_click="ignore",
                   help="CSV au format Excel français (séparateur « ; », virgule décimale).")  # fmt: skip
e3.download_button(f"CSV ({scope})", export.to_csv(index=False).encode("utf-8"), file_name="cibles_pme-radar.csv",
                   mime="text/csv", icon=":material/table:", width="stretch", on_click="ignore")  # fmt: skip
