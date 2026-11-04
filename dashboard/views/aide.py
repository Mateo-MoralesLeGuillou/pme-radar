"""Aide : où trouver chaque information, et ce que veut dire chaque terme."""

from __future__ import annotations

import streamlit as st
import ui

data = ui.load()
ui.page_title("Aide", "Trouver une information en quelques secondes, et comprendre chaque terme.")

st.subheader("Je cherche…")
WHERE = [
    ("Une entreprise précise", ui.P_COMPANY, "Barre de recherche en haut de chaque page : nom, ville, SIREN ou dirigeant."),
    ("Les cibles à contacter en priorité", ui.P_HOME, "Accueil › À faire maintenant (ou Cibles › « À approcher »)."),
    ("Pourquoi une cible a ce score", ui.P_COMPANY, "Fiche entreprise › onglet Score : points par critère, plafond."),
    ("Combien vaut une cible", ui.P_COMPANY, "Fiche entreprise › onglet Valorisation : fourchette, sensibilité, montage."),
    ("Quoi demander au cédant", ui.P_COMPANY, "Fiche entreprise › onglet Due diligence : questions et documents."),
    ("Le brouillon d'email", ui.P_COMPANY, "Fiche entreprise › onglet Contact : à copier, relire, adapter."),
    ("Qui relancer", ui.P_CAMPAIGN, f"Prises de contact › À traiter (sans réponse depuis {ui.FOLLOW_UP_DAYS} jours)."),
    ("Comparer ou exporter des cibles", ui.P_TARGETS, "Cibles : filtres, tri, export Excel, rapport d'une sélection."),
    ("Un document à partager", ui.P_REPORTS, "Rapports : rapport complet, dossier d'une entreprise, exports."),
]  # fmt: skip
grid = st.columns(3, gap="small")
for i, (need, page, how) in enumerate(WHERE):
    with grid[i % 3], st.container(border=True, height="stretch"):
        st.page_link(page, label=need, icon=":material/arrow_forward:")
        st.caption(how)

st.subheader("Les recommandations")
cols = st.columns(5)
for col, (tone, (_label, _, _, text)) in zip(cols, ui.RECO.items(), strict=True):
    with col, st.container(border=True, height="stretch"):
        st.html(ui.reco_badge(tone))
        st.caption(text)

st.subheader("Glossaire")
GLOSSARY = [
    ("Score", "Note sur 100 : transmission (âge du dirigeant, dirigeant-exploitant, successeur) 40, taille 25, "
     f"qualité 20, adéquation à la thèse 15, moins des pénalités. Qualifiée à partir de {data.threshold}."),
    ("Plafond", "Score atteignable si chaque donnée manquante s'avérait favorable."),
    ("Fiabilité", "Part du barème évaluée sur des données réelles (et non manquantes)."),
    ("Signal factuel", "Constat établi par une règle sur les données (endettement, baisse du CA, dépendance au "
     "dirigeant…), avec la question de due diligence associée."),
    ("Chiffre d'affaires (CA)", "Ventes de l'exercice."),
    ("EBE", "Excédent brut d'exploitation : rentabilité de l'activité avant amortissements, intérêts et impôts."),
    ("Marge d'EBE", "EBE divisé par le chiffre d'affaires."),
    ("Valeur d'entreprise (VE)", "Prix indicatif de l'activité : EBE × un multiple (4 à 6 par défaut). Ordre de "
     "grandeur, pas une évaluation."),
    ("Multiple d'EBE", "Nombre d'années d'EBE payées pour acquérir l'entreprise."),
    ("Dette senior", "Emprunt bancaire de l'acquisition, remboursé par les flux de la cible."),
    ("Crédit vendeur", "Part du prix payée plus tard au cédant : un signe de confiance."),
    ("Fonds propres", "Apport du repreneur et de ses investisseurs (prix + frais − dettes)."),
    ("Couverture", "Flux disponible pour la dette divisé par son remboursement annuel (confortable au-delà de 1,3x)."),
    ("Due diligence (DD)", "Vérifications avant l'achat : commerciale, financière, juridique, sociale, opérationnelle."),
    ("Holding personnelle", "Société détenue par le dirigeant pour porter ses titres : il reste l'interlocuteur."),
    ("BODACC", "Bulletin officiel des annonces civiles et commerciales : procédures collectives (exclusion)."),
    ("NAF", "Code d'activité de l'INSEE (ex. 33.20A, installation de structures métalliques)."),
    ("SIREN", "Identifiant à 9 chiffres de l'entreprise."),
]  # fmt: skip
term = st.text_input(
    "Rechercher un terme", key="term", placeholder="ex. EBE, plafond, crédit vendeur…"
)
shown = [(k, v) for k, v in GLOSSARY if not term or term.lower() in (k + " " + v).lower()]
if not shown:
    st.caption("Aucun terme ne correspond.")
for k, v in shown:
    st.markdown(f"**{k}** — {v}")

st.subheader("Questions fréquentes")
FAQ = [
    ("Le programme envoie-t-il des emails ?", "Non, jamais. Il prépare des brouillons marqués « à relire » ; "
     "l'envoi est un acte humain, suivi ensuite dans Prises de contact."),
    ("D'où viennent les données ?", "De sources publiques gratuites : annuaire des entreprises (data.gouv.fr), "
     "BODACC, ratios BCE/INPI. Aucune donnée achetée."),
    ("Pourquoi une cible n'a pas de valorisation ?", "Son EBE n'est pas publié (comptes confidentiels ou absents) : "
     "il faut l'obtenir au premier échange."),
    ("Pourquoi « à documenter » plutôt que « non prioritaire » ?", "Parce que des données manquent : son plafond "
     "dépasse le seuil, un échange peut la qualifier."),
    ("Comment changer les critères ?", "Dans config/scoring.yaml (barème, seuil) et config/thesis.yaml (secteurs, "
     "zone, multiples, financement), sans toucher au code."),
    ("Et le RGPD ?", "Données professionnelles publiques, minimisées ; chaque brouillon rappelle le droit "
     "d'opposition ; le dossier data/ reste local. Voir docs/rgpd.md."),
]  # fmt: skip
for q, a in FAQ:
    with st.expander(q):
        st.write(a)
