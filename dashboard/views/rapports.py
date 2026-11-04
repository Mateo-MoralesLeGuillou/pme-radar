"""Rapports : le rapport de pré-due diligence complet, un dossier par entreprise, les exports."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
import ui

from pme_radar.report import build_report

data = ui.load()
t = data.table
ui.require_data(data)
footer = data.campaign_cfg.get("compliance_footer")
ui.page_title(
    "Rapports", "Documents prêts à partager : rapport de pré-due diligence, dossiers, exports."
)

left, right = st.columns([1, 1], gap="large")
with left, st.container(border=True):
    st.markdown("#### :material/picture_as_pdf: Rapport de pré-due diligence")
    st.caption("Mémo au format private equity : synthèse exécutive, tableau des cibles, football field, puis un "
               "dossier par cible (thèse, vigilance, finances, valorisation, financement, plan de DD).")  # fmt: skip
    top_n = st.slider("Cibles « à approcher » détaillées", 1, 20, 10, key="report_top_n",
                      help="S'y ajoutent les meilleures cibles à creuser et à documenter.")  # fmt: skip

    def _full() -> str:
        html, _ = build_report(data.companies, data.scoring, data.thesis, campaign=data.campaign,
                               top_n=top_n, footer=footer)  # fmt: skip
        return html

    st.download_button("Télécharger le rapport (HTML, imprimable en PDF)", _full, file_name="rapport_pre_dd.html",
                       mime="text/html", icon=":material/download:", type="primary", on_click="ignore")  # fmt: skip
    sample_pdf = ui.ROOT / "examples" / "rapport_deal_flow_sample.pdf"
    if not data.live and sample_pdf.exists():
        st.download_button("Exemple PDF (échantillon synthétique)", sample_pdf.read_bytes(),
                           file_name="rapport_pre_dd_exemple.pdf", mime="application/pdf",
                           icon=":material/picture_as_pdf:", on_click="ignore")  # fmt: skip
    st.caption(
        "Ouvrir le fichier HTML dans le navigateur puis « Imprimer > Enregistrer en PDF » (A4)."
    )
with right, st.container(border=True):
    st.markdown("#### :material/apartment: Dossier d'une entreprise")
    st.caption("Le même dossier, pour une seule entreprise : à joindre à une note ou à un comité.")
    siren = st.selectbox("Entreprise", list(t["siren"]), index=None, format_func=data.label, key="report_one",
                         placeholder="Choisir une entreprise…")  # fmt: skip
    if siren:

        def _one() -> str:
            html, _ = build_report(data.companies, data.scoring, data.thesis, campaign=data.campaign,
                                   sirens=[siren], footer=footer)  # fmt: skip
            return html

        st.download_button("Télécharger le dossier", _one, file_name=f"dossier_{siren}.html", mime="text/html",
                           icon=":material/download:", type="primary", on_click="ignore")  # fmt: skip
        ui.company_link(siren, "Voir la fiche dans le dashboard")

with st.container(border=True):
    st.markdown("#### :material/table: Exports de données")
    e1, e2, e3 = st.columns(3)
    table = t.drop(columns=["_order"], errors="ignore")
    e1.download_button("Toutes les cibles (Excel)", table.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="cibles_pme-radar.csv", mime="text/csv", icon=":material/grid_on:",
                       width="stretch", on_click="ignore",
                       help="CSV au format Excel français (séparateur « ; », virgule décimale).")  # fmt: skip
    e2.download_button("Toutes les cibles (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name="cibles_pme-radar.csv", mime="text/csv", icon=":material/table:",
                       width="stretch", on_click="ignore")  # fmt: skip
    e3.download_button("Suivi des contacts (CSV)", data.campaign.to_csv(index=False).encode("utf-8"),
                       file_name="suivi_campagne.csv", mime="text/csv", icon=":material/forward_to_inbox:",
                       width="stretch", on_click="ignore")  # fmt: skip

st.subheader("Aperçu du rapport")
preview = (
    data.report_path if data.report_path else ui.ROOT / "examples" / "rapport_deal_flow_sample.html"
)
if st.toggle("Afficher l'aperçu", key="report_preview",
             help="Dernier rapport généré par `pme-radar run` (ou l'exemple synthétique en démo)."):  # fmt: skip
    if preview.exists():
        components.html(preview.read_text(encoding="utf-8"), height=900, scrolling=True)
    else:
        st.caption("Aucun rapport généré : téléchargez-le ci-dessus ou lancez `pme-radar report`.")
