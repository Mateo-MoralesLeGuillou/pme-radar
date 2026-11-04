"""Prises de contact : où en est chaque cible, quoi relancer, quels taux surveiller."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import ui

from pme_radar.funnel import campaign_metrics

data = ui.load()
ui.require_data(data)
ui.page_title(
    "Prises de contact", "Suivi des emails envoyés à la main : statuts, relances, taux de réponse."
)
camp = ui.campaign_view(data)
cc = ui.campaign_counts(data)
if camp.empty:
    ui.empty_state("Aucun suivi de campagne. Générez les brouillons (<code>pme-radar draft</code>) puis "
                   "suivez chaque envoi ici ou avec <code>pme-radar track</code>.", "✉️")  # fmt: skip
    st.stop()


def rate(num: int, den: int) -> str:
    return "n.d." if den <= 0 else ui.percent(num / den, 0)


delivered = cc["sent"] - cc["bounced"]
th = data.campaign_cfg
k = st.columns(5)
k[0].metric(
    "Brouillons prêts",
    cc["drafts"],
    border=True,
    icon=":material/edit_note:",
    help="À relire puis envoyer à la main : le programme n'envoie jamais rien.",
)
k[1].metric("Emails envoyés", cc["sent"], border=True, icon=":material/send:")
k[2].metric(
    "Taux de réponse",
    rate(cc["replied"], delivered),
    border=True,
    icon=":material/reply:",
    help=f"Réponses / emails délivrés. Alerte sous {th['reply_rate']['warning_below']:.0%}.",
)
k[3].metric(
    "Taux de RDV",
    rate(cc["meetings"], delivered),
    border=True,
    icon=":material/event_available:",
    help=f"Rendez-vous / emails délivrés. Alerte sous {th['meeting_rate']['warning_below']:.0%}.",
)
k[4].metric("Taux de rebond", rate(cc["bounced"], cc["sent"]), border=True, icon=":material/error:",
            help=f"Adresses invalides. Alerte à {th['bounce_rate']['warning']:.0%}, arrêt à "
                 f"{th['bounce_rate']['critical']:.0%}.")  # fmt: skip
for _, m in campaign_metrics(data.campaign, th).iterrows():
    if m["alerts"]:
        st.warning(f"Campagne {m['campaign_id']} : {m['alerts']}.", icon=":material/warning:")

# ---------------------------------------------------------------- relances
todo = ui.follow_ups(data)
if len(todo):
    st.subheader(f"À traiter ({len(todo)})")
    for r in todo.itertuples():
        a, b, c_ = st.columns([2.2, 2, 1.2], vertical_alignment="center")
        with a:
            ui.company_link(r.siren, r.name)
        b.html(
            ui.status_badge(r.status) + f" <span style='color:{ui.MUTED}'>{ui.esc(r.action)}</span>"
        )
        c_.caption(f"envoyé le {ui.fr_date(r.sent_date)}" if r.sent_date else "")

# ---------------------------------------------------------------- tableau de bord par statut
st.subheader("Pipeline par statut")
st.caption("Chaque colonne liste les entreprises à ce stade ; cliquez pour ouvrir la fiche.")
STAGES = [("draft", "à relire puis envoyer"), ("contacted", "en attente de réponse"),
          ("replied", "à traiter en priorité"), ("meeting", "rendez-vous obtenus"),
          ("declined", "ne plus solliciter"), ("bounced", "adresse à corriger")]  # fmt: skip
for line in (STAGES[:3], STAGES[3:]):
    board = st.columns(3, gap="medium")
    for col, (status, hint) in zip(board, line, strict=True):
        group = camp[camp["status"] == status].sort_values("score", ascending=False)
        with col, st.container(border=True, height="stretch"):
            st.html(f"{ui.status_badge(status)} <b style='margin-left:6px'>{len(group)}</b>"
                    f"<span style='color:{ui.MUTED}; margin-left:8px; font-size:.85rem'>{hint}</span>")  # fmt: skip
            if group.empty:
                st.caption("Aucune entreprise.")
            for r in group.head(8).itertuples():
                ui.company_link(r.siren, r.name)
            if len(group) > 8:
                st.caption(f"+ {len(group) - 8} autres (tableau ci-dessous)")

# ---------------------------------------------------------------- détail
st.subheader("Détail du suivi")
view = (
    camp.assign(
        status_label=camp["status"].map(lambda v: ui.STATUS.get(v, (v, ""))[0]),
        sent=pd.to_datetime(camp["sent_date"].replace("", None), errors="coerce"),
        replied=pd.to_datetime(camp["replied_date"].replace("", None), errors="coerce"),
        meeting=pd.to_datetime(camp["meeting_date"].replace("", None), errors="coerce"),
        open="Ouvrir",
    )
    .sort_values(["status", "score"], ascending=[True, False])
    .reset_index(drop=True)
)
cc_ = st.column_config
st.dataframe(
    view[["open", "name", "status_label", "score", "reco", "sent", "replied", "meeting", "note", "campaign_id"]],
    hide_index=True, width="stretch", placeholder="n.d.",
    column_config={
        "open": ui.open_button_column(view, "camp_open"),
        "name": cc_.TextColumn("Entreprise", pinned=True),
        "status_label": "Statut",
        "score": cc_.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        "reco": "Recommandation",
        "sent": cc_.DateColumn("Envoi", format="DD/MM/YYYY"),
        "replied": cc_.DateColumn("Réponse", format="DD/MM/YYYY"),
        "meeting": cc_.DateColumn("RDV", format="DD/MM/YYYY"),
        "note": "Note",
        "campaign_id": "Campagne",
    },
)  # fmt: skip
st.download_button("Exporter le suivi (CSV)", data.campaign.to_csv(index=False).encode("utf-8"),
                   file_name="suivi_campagne.csv", mime="text/csv", icon=":material/download:",
                   on_click="ignore")  # fmt: skip
with st.expander("Délivrabilité du domaine d'envoi", icon=":material/dns:"):
    st.markdown(
        "Avant tout envoi, vérifiez que le domaine est correctement configuré (MX, SPF, DKIM, DMARC) : "
        "sans cela, les emails finissent en spam et le taux de réponse s'effondre sans explication.\n\n"
        "`pme-radar deliverability --domain exemple.fr`"
    )
if data.campaign_path is None:
    st.caption("Démo : suivi fictif (`examples/sample_campaign.csv`). Avec vos données, mettez à jour un statut "
               "depuis la fiche entreprise, onglet Contact.")  # fmt: skip
