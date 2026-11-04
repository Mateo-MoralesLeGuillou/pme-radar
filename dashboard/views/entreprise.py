"""Fiche entreprise : tout ce qu'il faut savoir sur une cible, sur une seule page.

Lien direct : /entreprise?siren=<SIREN>. En-tête (recommandation, score), chiffres clés, l'essentiel
en trois blocs, puis des onglets : profil, finances, score, valorisation, due diligence, contact,
documents.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

from pme_radar import labels
from pme_radar.deal import (
    DEFAULT_FINANCING,
    DEFAULT_VALUATION,
    data_gaps,
    dd_plan,
    highlights,
    information_requests,
    sensitivity,
)
from pme_radar.fmt import mult
from pme_radar.onepager import render as render_onepager
from pme_radar.outreach import STATUSES, update_status, with_footer
from pme_radar.report import build_report

data = ui.load()
t = data.table
ui.require_data(data)
order = list(t["siren"])  # classement par score

# --------------------------------------------------------------- sélection (URL <-> état)
# l'URL (?siren=) prime ; sinon la dernière fiche consultée pendant la session
wanted = st.query_params.get("siren") or st.session_state.get("last_company")
if wanted in data.by_siren and st.session_state.get("company") != wanted:
    st.session_state["company"] = wanted


def _sync_url() -> None:
    value = st.session_state.get("company")
    if value:
        st.query_params["siren"] = value
    else:
        st.session_state.pop("last_company", None)
        if "siren" in st.query_params:
            del st.query_params["siren"]


def _step(delta: int) -> None:
    current = st.session_state.get("company")
    i = order.index(current) if current in order else -1
    st.session_state["company"] = order[(i + delta) % len(order)]
    _sync_url()


pick, prev_col, next_col = st.columns([7, 1.1, 1.1], vertical_alignment="bottom")
with pick:
    siren = st.selectbox(
        "Entreprise", order, index=None, format_func=data.label, key="company",
        on_change=_sync_url,
        placeholder="Choisir une entreprise : nom, ville, SIREN ou dirigeant…",
    )  # fmt: skip
prev_col.button("Précédente", icon=":material/chevron_left:", on_click=_step, args=(-1,),
                width="stretch", help="Entreprise précédente dans le classement par score.")  # fmt: skip
next_col.button("Suivante", icon=":material/chevron_right:", on_click=_step, args=(1,),
                width="stretch", help="Entreprise suivante dans le classement par score.")  # fmt: skip

if not siren or siren not in data.by_siren:
    ui.page_title(
        "Fiche entreprise", "Choisissez une entreprise ci-dessus, ou partez d'une suggestion."
    )
    st.subheader("Suggestions : meilleures cibles")
    cols = st.columns(3, gap="medium")
    for i, r in enumerate(t[t["stage"] != "excluded"].head(6).itertuples()):
        with cols[i % 3], st.container(border=True):
            ui.company_link(r.siren, r.name)
            st.html(f"{ui.reco_badge(r.tone)} <span style='color:{ui.MUTED}'>· {r.score:.0f}/100 · "
                    f"CA {ui.m_eur(r.revenue)} · {ui.esc(r.city)}</span>")  # fmt: skip
    st.stop()

st.session_state["last_company"] = siren
if st.query_params.get("siren") != siren:
    st.query_params["siren"] = siren  # retour sur la page : l'URL désigne la fiche affichée

c = data.by_siren[siren]
d = data.dossiers[siren]
row = t.set_index("siren").loc[siren]
s, plan = c.score, d.plan
assert s is not None
person = c.main_person()
rank = order.index(siren) + 1

# --------------------------------------------------------------- en-tête
if row["status"]:
    contact_tag = ui.status_badge(row["status"])
else:
    contact_tag = ui.status_badge("draft" if c.analysis else "")
st.html(
    f"""<div class="pr-ts"><div>
    <h2>{ui.esc(c.name)}</h2>
    <div class="sub">{ui.esc(c.naf_label)} · {ui.esc(c.city)} ({ui.esc(c.department)}) · SIREN {ui.esc(c.siren)}
    · {ui.esc(labels.legal_form(c.legal_form))}</div>
    <div class="tags">{ui.reco_badge(d.rec.tone, big=True)} {contact_tag}</div></div>
    <div class="right"><div class="meta">Score · n° {rank} sur {len(order)}</div>
    <div class="score">{s.total:.0f}<small>/100</small></div>
    <div class="meta">plafond {s.ceiling:.0f} · fiabilité {ui.percent(s.confidence, 0)}</div></div></div>"""
)

# --------------------------------------------------------------- chiffres clés
OFF = {"delta_color": "off", "delta_arrow": "off", "border": True, "height": "stretch"}
growth = f"{ui.percent(c.revenue_cagr, signed=True)} par an" if c.revenue_cagr is not None else None
m = st.columns(6)
m[0].metric(
    "Chiffre d'affaires",
    ui.money(c.revenue_last),
    delta=growth,
    border=True,
    height="stretch",
    help="Dernier exercice publié ; variation : croissance annuelle moyenne du CA.",
)
m[1].metric(
    "Marge d'EBE",
    ui.percent(c.ebe_margin),
    delta=f"EBE {ui.money(c.ebe)}" if c.ebe else None,
    help="EBE / chiffre d'affaires. EBE : rentabilité opérationnelle avant amortissements.",
    **OFF,
)
m[2].metric(
    "Résultat net",
    ui.money(c.net_income_last),
    delta=f"marge {ui.percent(c.net_margin)}" if c.net_margin is not None else None,
    help="Résultat net du dernier exercice publié.",
    **OFF,
)
m[3].metric(
    "Valeur d'entreprise",
    ui.m_eur(plan.ev_mid) if plan else "n.d.",
    delta=f"{ui.m_eur(plan.ev_low)} – {ui.m_eur(plan.ev_high)}" if plan else "EBE non publié",
    help="Indicative : EBE × multiples de la thèse (milieu de fourchette).",
    **OFF,
)
m[4].metric(
    "Fonds propres à réunir",
    ui.money(plan.equity) if plan else "n.d.",
    delta=f"{ui.percent(plan.equity_share, 0)} des emplois" if plan else None,
    help="Montage indicatif : prix + frais − dette senior − crédit vendeur.",
    **OFF,
)
m[5].metric("Dirigeant", ui.years(c.director_age), delta=person.name if person and person.name else None,
            help="Âge du dirigeant principal (ou de la personne derrière sa holding personnelle).", **OFF)  # fmt: skip

# --------------------------------------------------------------- l'essentiel
tiers = {n["code"]: n["tier"] for n in data.thesis.get("naf_codes", [])}
strengths = highlights(c, tiers.get(c.naf_code or ""))
watch = [x for x in d.signals if x.level in ("élevé", "moyen")]
e1, e2, e3 = st.columns(3, gap="medium")
with e1, st.container(border=True, height="stretch"):
    st.markdown(f"**Pourquoi « {d.rec.label} » ?**")
    st.caption(ui.RECO[d.rec.tone][3])
    st.html(
        '<ul class="pr-list">' + "".join(f"<li>{ui.esc(r)}</li>" for r in d.rec.reasons) + "</ul>"
    )
with e2, st.container(border=True, height="stretch"):
    st.markdown("**Points forts**")
    items = strengths or ["Aucun point fort établi par les données publiques."]
    st.html(
        '<ul class="pr-list pr-pos">' + "".join(f"<li>{ui.esc(x)}</li>" for x in items) + "</ul>"
    )
with e3, st.container(border=True, height="stretch"):
    st.markdown("**Points de vigilance**")
    if watch:
        st.html('<ul class="pr-list pr-neg">' + "".join(
            f"<li><b>{ui.esc(x.title)}</b> — {ui.esc(x.detail)}</li>" for x in watch) + "</ul>")  # fmt: skip
    else:
        st.caption("Aucun point de vigilance majeur dans les données.")

tabs = st.tabs([":material/badge: Profil", ":material/bar_chart: Finances", ":material/speed: Score",
                ":material/account_balance: Valorisation", ":material/fact_check: Due diligence",
                ":material/mail: Contact", ":material/download: Documents"])  # fmt: skip


def kv(pairs: list[tuple[str, str]]) -> None:
    st.html('<dl class="pr-kv">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>")


# --------------------------------------------------------------- profil
with tabs[0]:
    p1, p2 = st.columns([1, 1.2], gap="large")
    with p1:
        st.markdown("##### Identité")
        bodacc = {True: "procédure collective publiée", False: "aucune procédure",
                  None: "non interrogé"}[c.has_collective_procedure]  # fmt: skip
        kv([
            ("Activité", f"{ui.esc(c.naf_code)} · {ui.esc(c.naf_label)}"),
            ("Forme juridique", ui.esc(labels.legal_form(c.legal_form))),
            ("Création", f"{c.creation_date:%d/%m/%Y} ({c.company_age_years} ans)" if c.creation_date else "n.d."),
            ("Effectif", ui.esc(labels.headcount(c.headcount_band))),
            ("Siège", f"{ui.esc(c.postal_code)} {ui.esc(c.city)}"),
            ("Département", ui.esc(labels.department(c.department))),
            ("Comptes publiés", "oui" if c.accounts_available else "non (confidentiels ou absents)"),
            ("BODACC", bodacc),
        ])  # fmt: skip
    with p2:
        st.markdown("##### Dirigeants")
        rows = [{"Nom": x.name or "n.d.", "Qualité": x.role or "", "Type": "personne physique"
                 if x.is_natural_person else "société", "Naissance": str(x.birth_year or "")}
                for x in c.directors]  # fmt: skip
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", placeholder="n.d.")
        else:
            st.caption("Aucun dirigeant publié.")
        if c.holding_name:
            owner = c.holding_owner
            who = f" ({ui.esc(owner.name)})" if owner and owner.name else ""
            st.info(f"Détention via la holding personnelle **{c.holding_name}**{who} : le dirigeant reste "
                    "l'interlocuteur de la transmission.", icon=":material/account_tree:")  # fmt: skip
        elif c.has_corporate_director:
            st.warning("Dirigée par une société (groupe) : décision de cession probablement hors de la "
                       "société.", icon=":material/corporate_fare:")  # fmt: skip

# --------------------------------------------------------------- finances
with tabs[1]:
    years_ = [f for f in c.financials if f.revenue is not None or f.net_income is not None][-6:]
    if not years_:
        ui.empty_state(
            "Aucun compte publié dans les sources ouvertes : liasses fiscales à obtenir en priorité.",
            "📄",
        )
    else:
        f1, f2 = st.columns([1.15, 1], gap="large")
        with f1:
            fin = pd.DataFrame(index=["Chiffre d'affaires", "Croissance", "Résultat net", "Marge nette",
                                      "EBE", "Marge d'EBE"])  # fmt: skip
            prev = None
            for f in years_:
                yoy = ui.percent(f.revenue / prev - 1, signed=True) if prev and f.revenue else "—"
                fin[str(f.year)] = [
                    ui.money(f.revenue), yoy, ui.money(f.net_income),
                    ui.percent(f.net_income / f.revenue) if f.revenue and f.net_income is not None else "n.d.",
                    ui.money(c.ebe) if c.ebe_year == f.year else "—",
                    ui.percent(c.ebe_margin) if c.ebe_year == f.year else "—",
                ]  # fmt: skip
                prev = f.revenue
            st.dataframe(fin, width="stretch")
            debt = "n.d." if c.debt_ratio is None else f"{c.debt_ratio:.0f} % des fonds propres"
            st.caption(f"Endettement : {debt}. Sources : API Recherche d'entreprises (data.gouv.fr), "
                       "ratios BCE/INPI. EBE publié pour le dernier exercice disponible.")  # fmt: skip
        with f2:
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=[str(f.year) for f in years_],
                    y=[(f.revenue or 0) / 1e6 for f in years_],
                    name="Chiffre d'affaires",
                    marker_color=ui.CYAN,
                    text=[ui.m_eur(f.revenue) for f in years_],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="CA %{x} : %{y:.2f} M€<extra></extra>",
                )
            )
            fig.add_trace(go.Scatter(x=[str(f.year) for f in years_],
                                     y=[(f.net_income or 0) / 1e3 for f in years_], name="Résultat net",
                                     mode="lines+markers+text", line={"color": ui.AMBER, "width": 3}, yaxis="y2",
                                     text=[ui.money(f.net_income) for f in years_], textposition="top center",
                                     textfont={"color": ui.AMBER},
                                     hovertemplate="Résultat net %{x} : %{y:.0f} k€<extra></extra>"))  # fmt: skip
            net = [(f.net_income or 0) / 1e3 for f in years_]
            span = max(abs(x) for x in net) or 1
            fig.update_layout(showlegend=True, legend={"orientation": "h", "y": 1.14, "x": 0},
                              yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "showticklabels": False,
                                      "range": [min(0, min(net)) - span * 0.2, span * 2.2]})  # fmt: skip
            fig.update_yaxes(title="CA (M€)", selector={"anchor": "x"})
            ui.chart(fig, 300, key="co_fin", legend=True)

# --------------------------------------------------------------- score
with tabs[2]:
    s1, s2 = st.columns([1.5, 1], gap="large")
    with s1:
        crit = s.criteria[::-1]
        bars = go.Figure()
        bars.add_trace(
            go.Bar(
                y=[x.label for x in crit],
                x=[x.max_points for x in crit],
                orientation="h",
                marker_color=ui.GRID,
                hoverinfo="skip",
            )
        )
        bars.add_trace(go.Bar(y=[x.label for x in crit], x=[x.points for x in crit], orientation="h",
                              marker_color=[ui.VIOLET if x.missing else ui.CYAN for x in crit],
                              text=[f"{x.points:g}/{x.max_points:g} · {x.detail}" for x in crit],
                              textposition="outside", cliponaxis=False,
                              hovertemplate="%{y} : %{x} pt<extra></extra>"))  # fmt: skip
        bars.update_layout(barmode="overlay", bargap=0.35)
        bars.update_xaxes(visible=False, range=[0, 52])
        ui.chart(bars, 380, key="co_score")
    with s2:
        st.markdown(
            f"#### {s.total:.0f}/100 · {'qualifiée' if s.total >= data.threshold else 'non qualifiée'}"
        )
        st.caption(f"Seuil de qualification : {data.threshold}/100.")
        kv([
            ("Plafond", f"{s.ceiling:.0f}/100 <small>(si les données manquantes sont favorables)</small>"),
            ("Fiabilité", f"{ui.percent(s.confidence, 0)} du barème évalué sur données réelles"),
        ])  # fmt: skip
        for pen in s.penalties:
            st.error(
                f"{pen.label} : {pen.points:g} pt · {pen.detail}", icon=":material/remove_circle:"
            )
        gaps = data_gaps(c)
        if gaps:
            st.markdown("**Données à obtenir**")
            st.html(
                '<ul class="pr-list">' + "".join(f"<li>{ui.esc(g)}</li>" for g in gaps) + "</ul>"
            )
        st.caption(s.summary)

# --------------------------------------------------------------- valorisation
with tabs[3]:
    val = {**DEFAULT_VALUATION, **(data.thesis.get("valuation") or {})}
    fin_cfg = {**DEFAULT_FINANCING, **(data.thesis.get("financing") or {})}
    if plan is None:
        ui.empty_state("Valorisation non calculable : EBE indisponible ou négatif. À obtenir au premier "
                       "échange (liasses fiscales, EBE retraité).", "🧮")  # fmt: skip
    else:
        v = st.columns(4)
        v[0].metric(
            "VE basse",
            ui.money(plan.ev_low),
            border=True,
            help=f"EBE × {val['ebe_multiple_low']:g}",
        )
        v[1].metric(
            "VE milieu", ui.money(plan.ev_mid), border=True, help="Base du montage indicatif."
        )
        v[2].metric(
            "VE haute",
            ui.money(plan.ev_high),
            border=True,
            help=f"EBE × {val['ebe_multiple_high']:g}",
        )
        v[3].metric(
            "EBE de référence", ui.money(plan.ebe), border=True, help=f"Exercice {plan.ebe_year}."
        )
        h1, h2 = st.columns([1.1, 1], gap="large")
        with h1:
            st.markdown("##### Sensibilité de la valeur (M€)")
            multiples, deltas, grid = sensitivity(plan, data.thesis)
            heat = go.Heatmap(
                z=[[x / 1e6 for x in r] for r in grid], x=[f"{m_:g}x".replace(".", ",") for m_ in multiples],
                y=[f"EBE {ui.percent(d_, 0, signed=True)}" if d_ else "EBE de référence" for d_ in deltas],
                text=[[f"{x / 1e6:.2f}".replace(".", ",") for x in r] for r in grid], texttemplate="%{text}",
                colorscale=[[0, "#14203a"], [1, "#1a8fc0"]], showscale=False,
                hovertemplate="%{y} × %{x} : %{text} M€<extra></extra>",
            )  # fmt: skip
            fig = go.Figure(heat)
            fig.update_yaxes(autorange="reversed")
            fig.add_shape(
                type="rect", x0=1.5, x1=2.5, y0=1.5, y1=2.5, line={"color": ui.AMBER, "width": 3}
            )
            ui.chart(fig, 260, key="co_sens")
            st.caption(
                "Lignes : variation de l'EBE ; colonnes : multiple retenu. Encadré : cas de base."
            )
        with h2:
            st.markdown("##### Emplois et ressources (milieu de fourchette)")
            su = pd.DataFrame(
                [("Emplois", "Valeur d'entreprise", plan.ev_mid), ("Emplois", "Frais de transaction", plan.fees),
                 ("Ressources", "Dette senior", plan.senior_debt), ("Ressources", "Crédit vendeur", plan.vendor_loan),
                 ("Ressources", "Fonds propres", plan.equity)],
                columns=["", "Poste", "Montant"],
            )  # fmt: skip
            su["Part"] = (su["Montant"] / plan.uses).map(lambda v: ui.percent(v, 0))
            su["Montant"] = su["Montant"].map(ui.money)
            st.dataframe(su, hide_index=True, width="stretch", placeholder="n.d.")
            ok = plan.coverage >= fin_cfg["min_coverage"]
            kv([
                ("Dette senior / EBE", f"{plan.senior_debt / plan.ebe:.1f}x".replace(".", ",")),
                ("Fonds propres / emplois", ui.percent(plan.equity_share, 0)),
                ("Service annuel de la dette", ui.money(plan.annual_debt_service)),
                ("Couverture", f"{mult(plan.coverage)} ({'confortable' if ok else 'tendue'})"),
            ])  # fmt: skip
        st.caption("Ordres de grandeur pour décider d'un premier contact, pas une évaluation : ni dette nette, "
                   "ni BFR, ni EBE normalisé. Hypothèses : config/thesis.yaml (voir Aide).")  # fmt: skip

# --------------------------------------------------------------- due diligence
with tabs[4]:
    level_icon = {"élevé": "🔴", "moyen": "🟠", "info": "⚪"}
    st.markdown("##### Signaux factuels")
    if d.signals:
        sig = pd.DataFrame([{"Niveau": f"{level_icon.get(x.level, '')} {x.level}", "Signal": x.title,
                             "Détail": x.detail, "Chantier": x.theme} for x in d.signals])  # fmt: skip
        st.dataframe(sig, hide_index=True, width="stretch", placeholder="n.d.")
    else:
        st.caption("Aucun signal factuel.")
    if c.analysis and c.analysis.red_flags:
        with st.expander("Hypothèses de l'IA, à vérifier"):
            st.html(
                '<ul class="pr-list">'
                + "".join(f"<li>{ui.esc(x)}</li>" for x in c.analysis.red_flags)
                + "</ul>"
            )
    with st.container():
        st.markdown("##### Plan de due diligence")
        plan_dd = pd.DataFrame(
            dd_plan(d.signals), columns=["Réf.", "Chantier", "Question", "Priorité"]
        )
        only_high = st.toggle("Priorité haute uniquement", key="dd_high",
                              help="Questions déclenchées par un signal factuel de la cible.")  # fmt: skip
        if only_high:
            plan_dd = plan_dd[plan_dd["Priorité"] == "Haute"]
        st.dataframe(plan_dd, hide_index=True, width="stretch", placeholder="n.d.",
                     column_config={"Réf.": st.column_config.TextColumn(width=60),
                                    "Chantier": st.column_config.TextColumn(width=150),
                                    "Question": st.column_config.TextColumn(width=760)})  # fmt: skip
    q2, q3 = st.columns([1.2, 1], gap="large")
    with q2:
        st.markdown("##### Documents à demander")
        irl = pd.DataFrame(information_requests(d.signals), columns=["Document", "Priorité"])
        st.dataframe(irl, hide_index=True, width="stretch", placeholder="n.d.")
    with q3:
        st.markdown("##### Prochaines étapes")
        st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(d.rec.next_steps, 1)))

# --------------------------------------------------------------- contact
with tabs[5]:
    k1, k2 = st.columns([1, 1.5], gap="large")
    camp = data.campaign.set_index("siren")
    with k1:
        st.markdown("##### Suivi de la prise de contact")
        st.html(ui.status_badge(row["status"]))
        if siren in camp.index:
            r = camp.loc[siren]
            kv([("Campagne", ui.esc(r["campaign_id"])), ("Envoi", ui.fr_date(r["sent_date"])),
                ("Réponse", ui.fr_date(r["replied_date"])), ("Rendez-vous", ui.fr_date(r["meeting_date"])),
                ("Note", ui.esc(r["note"]) or "—")])  # fmt: skip
        if data.campaign_path is not None:
            with st.form("status_form", border=True):
                st.markdown("**Mettre à jour**")
                labels_ = {k: ui.STATUS[k][0] for k in STATUSES}
                new = st.selectbox(
                    "Nouveau statut", list(labels_), format_func=labels_.get, index=1
                )
                when = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                note = st.text_input("Note (facultatif)")
                if st.form_submit_button("Enregistrer", icon=":material/save:", type="primary"):
                    update_status(
                        data.campaign_path, siren, new, on=when, note=note, campaign_id="manuel"
                    )
                    st.toast(f"{c.name} : {labels_[new]}", icon=":material/check_circle:")
                    st.rerun()
        else:
            st.caption("Démo : suivi en lecture seule. Avec vos données, le statut se met à jour ici "
                       "(ou `pme-radar track`).")  # fmt: skip
    with k2:
        st.markdown("##### Brouillon d'approche")
        if c.analysis is None:
            st.caption("Brouillon non généré pour cette cible : `pme-radar draft` (top N).")
        else:
            footer = data.campaign_cfg.get("compliance_footer")
            st.html('<span class="pr-warn">À RELIRE · AUCUN ENVOI AUTOMATIQUE</span>')
            to = f"{person.name}, {person.role}" if person and person.name else "dirigeant"
            st.caption(f"Destinataire : {to}. Copier, relire et adapter avant tout envoi.")
            st.code(c.analysis.email_subject, language=None, wrap_lines=True)
            st.code(with_footer(c.analysis.email_body, footer), language=None, wrap_lines=True)

# --------------------------------------------------------------- documents
with tabs[6]:
    footer = data.campaign_cfg.get("compliance_footer")

    def _dossier() -> str:
        html, _ = build_report(data.companies, data.scoring, data.thesis, campaign=data.campaign,
                               sirens=[siren], footer=footer)  # fmt: skip
        return html

    def _onepager() -> str:
        cfg = data.thesis.get("valuation") or {"ebe_multiple_low": 4.0, "ebe_multiple_high": 6.0}
        return render_onepager(c, cfg)

    st.markdown("##### Télécharger")
    ui.report_downloads(_dossier, f"dossier_{siren}", "Dossier de pré-due diligence")
    st.download_button("Fiche synthétique (Markdown)", _onepager, file_name=f"fiche_{siren}.md",
                       mime="text/markdown", icon=":material/article:", on_click="ignore")  # fmt: skip
    st.download_button("Données de la fiche (CSV)", row.to_frame().T.to_csv(index=False).encode("utf-8"),
                       file_name=f"{siren}.csv", mime="text/csv", icon=":material/table:", on_click="ignore")  # fmt: skip
    st.caption(
        f"Lien direct vers cette fiche : `?siren={siren}` (à ajouter à l'adresse du dashboard)."
    )
