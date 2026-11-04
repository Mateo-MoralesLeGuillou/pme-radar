"""Tableau de bord pme-radar. Lancer : streamlit run dashboard/app.py (aucune clé requise).

Navigation en haut de page, recherche globale (nom, ville, SIREN, dirigeant) qui ouvre la fiche de
l'entreprise, lien direct vers une fiche : `/entreprise?siren=…`. Données : dernier run local
(`data/`) ou échantillon synthétique (`examples/`). Variables d'environnement facultatives :
PME_RADAR_DATA=sample (forcer la démo), PME_RADAR_DATA_DIR=<dossier> (autre dossier de run),
PME_RADAR_BROWSER=<chemin> (navigateur utilisé pour les PDF).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui  # noqa: E402

load_dotenv(ui.ROOT / ".env")  # variables facultatives (dossier du run, navigateur pour le PDF)

st.set_page_config(
    page_title="pme-radar · origination",
    page_icon=str(ui.ROOT / "docs/img/logo.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)
ui.inject_css()
pages = [
    st.Page(ui.P_HOME, title="Accueil", icon=":material/home:", default=True),
    st.Page(ui.P_COMPANY, title="Entreprise", icon=":material/apartment:"),
    st.Page(ui.P_TARGETS, title="Cibles", icon=":material/filter_alt:"),
    st.Page(ui.P_CAMPAIGN, title="Prises de contact", icon=":material/forward_to_inbox:"),
    st.Page(ui.P_REPORTS, title="Rapports", icon=":material/description:"),
    st.Page(ui.P_HELP, title="Aide", icon=":material/help:"),
]
nav = st.navigation(pages, position="top")
ui.header(data_mode_available=ui.live_paths() is not None)
ui.handle_goto()
nav.run()
ui.footer()
