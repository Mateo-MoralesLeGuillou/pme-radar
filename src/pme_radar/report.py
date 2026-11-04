"""Rapport de deal flow : synthèse du pipeline et dossier de pré-due diligence par cible.

Sortie : un fichier HTML autonome (aucune ressource externe), lisible à l'écran et imprimable en PDF
A4 (« Imprimer > Enregistrer en PDF »). Chaque dossier rassemble ce qu'il faut pour décider d'un
premier appel : recommandation argumentée, identité et gouvernance, historique financier, score
détaillé avec sa fourchette, valorisation et montage LBO indicatifs, signaux factuels, données à
obtenir, questions de due diligence par thème et brouillon d'approche (ADR-020).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from statistics import median
from typing import Any

import pandas as pd

from . import labels
from .deal import (
    DD_THEMES,
    DOCUMENTS,
    Financing,
    Recommendation,
    data_gaps,
    dd_questions,
    financing_plan,
    recommend,
)
from .enrich import director_age
from .fmt import NNBSP, eur, mult, pct
from .models import Company, Stage
from .outreach import with_footer
from .risks import Signal, assess

ORDER = {"go": 0, "dig": 1, "doc": 2, "low": 3, "out": 4}
LOGO = (
    '<svg viewBox="0 0 128 128" width="44" height="44" aria-hidden="true"><defs>'
    '<linearGradient id="rs" x1="64" y1="64" x2="108" y2="18" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#25c2f5" stop-opacity="0"/><stop offset="1" stop-color="#25c2f5" '
    'stop-opacity=".9"/></linearGradient></defs><circle cx="64" cy="64" r="60" fill="#1d1d3a"/>'
    '<g fill="none" stroke="#25c2f5"><circle cx="64" cy="64" r="58" stroke-opacity=".45" '
    'stroke-width="3"/><circle cx="64" cy="64" r="40" stroke-opacity=".28" stroke-width="2.5"/>'
    '<circle cx="64" cy="64" r="22" stroke-opacity=".22" stroke-width="2"/></g>'
    '<path d="M64 64 L64 6 A58 58 0 0 1 114.23 35 Z" fill="url(#rs)"/>'
    '<circle cx="92" cy="40" r="6" fill="#fff"/><circle cx="64" cy="64" r="4.5" fill="#25c2f5"/></svg>'
)


@dataclass
class Dossier:
    company: Company
    signals: list[Signal]
    plan: Financing | None
    rec: Recommendation


def evaluate(
    companies: list[Company],
    scoring_cfg: dict[str, Any],
    thesis: dict[str, Any],
    as_of: date | None = None,
) -> list[Dossier]:
    """Signaux, montage et recommandation pour chaque société notée."""
    out = []
    for c in companies:
        if c.score is None:
            continue
        signals = assess(c, scoring_cfg, as_of)
        plan = financing_plan(c, thesis)
        out.append(Dossier(c, signals, plan, recommend(c, signals, plan, scoring_cfg, thesis)))
    return out


def select(dossiers: list[Dossier], top_n: int, sirens: list[str] | None = None) -> list[Dossier]:
    """Dossiers détaillés : les SIREN demandés ; sinon les `top_n` meilleures cibles à approcher,
    plus les cibles à creuser et à documenter (jusqu'à max(2, top_n // 4) de chaque), qui
    appellent une action avant toute approche."""
    if sirens:
        wanted = set(sirens)
        return [d for d in dossiers if d.company.siren in wanted]

    def best(tone: str, n: int) -> list[Dossier]:
        pool = [d for d in dossiers if d.rec.tone == tone]
        pool.sort(key=lambda d: -(d.company.score.total if d.company.score else 0))
        return pool[:n]

    extra = max(2, top_n // 4)
    return best("go", top_n) + best("dig", extra) + best("doc", extra)


# ---------------------------------------------------------------- rendu
def _e(v: object) -> str:
    return "n.d." if v is None or v == "" else escape(str(v))


def _badge(rec: Recommendation) -> str:
    return f'<span class="reco reco-{rec.tone}">{escape(rec.label)}</span>'


def _range(c: Company) -> str:
    s = c.score
    if s is None:
        return "n.d."
    if s.ceiling > s.total + 0.5:
        return f"{s.total:.0f} <small>→ {s.ceiling:.0f}</small>"
    return f"{s.total:.0f}"


def _summary_section(
    dossiers: list[Dossier], scoring_cfg: dict[str, Any], campaign: pd.DataFrame | None
) -> str:
    total = len(dossiers)
    by_tone = {t: [d for d in dossiers if d.rec.tone == t] for t in ORDER}
    qualified = [d for d in dossiers if d.company.stage == Stage.QUALIFIED]
    threshold = scoring_cfg.get("qualified_threshold", 70)
    cards = [
        ("Sociétés notées", total, ""),
        ("Qualifiées", len(qualified), f"score ≥ {threshold}"),
        ("À approcher", len(by_tone["go"]), "recommandation"),
        ("À creuser · à documenter", len(by_tone["dig"]) + len(by_tone["doc"]), "un point à lever"),
        ("Écartées", len(by_tone["out"]), "procédure collective"),
    ]
    kpis = "".join(
        f'<div class="kpi"><b>{n}</b><span>{escape(lbl)}</span><small>{escape(sub)}</small></div>'
        for lbl, n, sub in cards
    )
    points = []
    if total:
        points.append(f"{len(qualified)} cible(s) qualifiée(s) sur {total} sociétés notées "
                      f"({pct(len(qualified) / total, 0)}).")  # fmt: skip
    if qualified:
        med = median(d.company.score.total for d in qualified if d.company.score)
        conf = sum(d.company.score.confidence for d in qualified if d.company.score) / len(
            qualified
        )
        points.append(f"Score médian des qualifiées : {med:.0f}/100 ; fiabilité moyenne des données : "
                      f"{pct(conf, 0)} du barème.")  # fmt: skip
    plans = [d.plan for d in by_tone["go"] if d.plan]
    if plans:
        points.append(f"Valeur d'entreprise indicative médiane des cibles à approcher : "
                      f"{eur(median(p.ev_mid for p in plans))} ; fonds propres médians à réunir : "
                      f"{eur(median(p.equity for p in plans))}.")  # fmt: skip
    if by_tone["doc"]:
        points.append(f"{len(by_tone['doc'])} cible(s) à documenter : des données manquantes "
                      "pourraient les faire passer le seuil, un appel peut trancher.")  # fmt: skip
    if campaign is not None and len(campaign):
        status = campaign["status"]
        sent = int(status.isin(["contacted", "replied", "meeting", "declined", "bounced"]).sum())
        if sent == 0:
            points.append(
                f"Campagne : {len(campaign)} brouillon(s) prêt(s) à relire, aucun envoi à ce jour."
            )
        else:
            points.append(f"Campagne : {sent} contact(s) envoyé(s), "
                          f"{int(status.isin(['replied', 'meeting', 'declined']).sum())} réponse(s), "
                          f"{int((status == 'meeting').sum())} rendez-vous.")  # fmt: skip
    bar = "".join(
        f'<i class="bar-{t}" style="flex:{len(v)}" title="{len(v)}"></i>'
        for t, v in by_tone.items()
        if v
    )
    legend = "".join(
        f'<span class="lg lg-{t}">{escape(lbl)} · {len(by_tone[t])}</span>'
        for t, lbl in [
            ("go", "À approcher"),
            ("dig", "À creuser"),
            ("doc", "À documenter"),
            ("low", "Non prioritaire"),
            ("out", "Écartée"),
        ]  # fmt: skip
        if by_tone[t]
    )
    items = "".join(f"<li>{escape(p)}</li>" for p in points)
    return (f'<section><h2>Synthèse du pipeline</h2><div class="kpis">{kpis}</div>'
            f'<div class="stack">{bar}</div><div class="legend">{legend}</div>'
            f'<ul class="points">{items}</ul></section>')  # fmt: skip


def _ranking_section(chosen: list[Dossier]) -> str:
    rows = []
    for i, d in enumerate(chosen, 1):
        c, p = d.company, d.plan
        ev = f"{eur(p.ev_low)} – {eur(p.ev_high)}" if p else "n.d."
        rows.append(
            f'<tr><td>{i}</td><td><a href="#d-{c.siren}">{_e(c.name)}</a><br><small>{_e(c.city)}'
            f"</small></td><td class=num>{_range(c)}</td>"
            f"<td class=num>{pct(c.score.confidence if c.score else None, 0)}</td>"
            f"<td class=num>{eur(c.revenue_last)}</td><td class=num>{pct(c.ebe_margin)}</td>"
            f"<td class=num>{ev}</td><td>{_badge(d.rec)}</td></tr>"
        )
    return ('<section><h2>Dossiers détaillés</h2><table class="rank"><thead><tr><th>#</th>'
            '<th>Entreprise</th><th>Score <small>→ plafond</small></th><th>Fiabilité</th><th>CA</th>'
            "<th>Marge EBE</th><th>Valeur indicative</th><th>Recommandation</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></section>")  # fmt: skip


def _kv(rows: list[tuple[str, str]]) -> str:
    return (
        '<table class="kv">'
        + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
        + "</table>"
    )


def _identity(c: Company, as_of: date) -> str:
    directors = []
    for d in c.directors:
        if d.is_natural_person:
            age = director_age(d, as_of)
            directors.append(f"{_e(d.name)} — {_e(d.role)}" + (f", {age} ans" if age else ""))
        else:
            directors.append(f"{_e(d.name)} — {_e(d.role)} (personne morale)")
    if c.holding_owner is not None:
        o = c.holding_owner
        directors.append(f"via {_e(c.holding_name)} : {_e(o.name)}"
                         + (f", {c.director_age} ans" if c.director_age else ""))  # fmt: skip
    bodacc = {True: '<span class="txt-red">procédure collective publiée</span>',
              False: "aucune procédure collective", None: "non interrogé"}[c.has_collective_procedure]  # fmt: skip
    created = (f"{c.creation_date:%d/%m/%Y} ({c.company_age_years} ans)" if c.creation_date
               else "n.d.")  # fmt: skip
    return _kv([
        ("Forme juridique", escape(labels.legal_form(c.legal_form))),
        ("Création", created),
        ("Effectif", escape(labels.headcount(c.headcount_band))),
        ("Siège", f"{_e(c.postal_code)} {_e(c.city)} · {escape(labels.department(c.department))}"),
        ("Activité", f"{_e(c.naf_code)} — {_e(c.naf_label)}"),
        ("Dirigeants", "<br>".join(directors) or "n.d."),
        ("BODACC", bodacc),
    ])  # fmt: skip


def _financials(c: Company) -> str:
    years = [f for f in c.financials if f.revenue is not None or f.net_income is not None][-5:]
    if not years:
        table = '<p class="muted">Aucun compte publié dans les sources ouvertes.</p>'
    else:
        head = "".join(f"<th class=num>{f.year}</th>" for f in years)

        def row(label: str, cells: list[str]) -> str:
            return (
                f"<tr><th>{label}</th>"
                + "".join(f"<td class=num>{x}</td>" for x in cells)
                + "</tr>"
            )

        growth: list[str] = []
        prev = None
        for f in years:
            if prev is not None and prev.revenue and f.revenue is not None:
                growth.append(pct(f.revenue / prev.revenue - 1, signed=True))
            else:
                growth.append("—")
            prev = f
        margins = [pct(f.net_income / f.revenue) if f.revenue and f.net_income is not None else "n.d."
                   for f in years]  # fmt: skip
        table = (f'<table class="fin"><thead><tr><th>Exercice</th>{head}</tr></thead><tbody>'
                 + row("Chiffre d'affaires", [eur(f.revenue) for f in years])
                 + row("Variation", growth)
                 + row("Résultat net", [eur(f.net_income) for f in years])
                 + row("Marge nette", margins) + "</tbody></table>")  # fmt: skip
    ebe = (f"{eur(c.ebe)} (exercice {c.ebe_year}) · marge {pct(c.ebe_margin)}" if c.ebe is not None
           else "n.d.")  # fmt: skip
    debt = "n.d." if c.debt_ratio is None else f"{c.debt_ratio:.0f}{NNBSP}% des capitaux propres"
    return table + _kv([
        ("EBE (ratios BCE/INPI)", ebe),
        ("Croissance annuelle moyenne du CA", pct(c.revenue_cagr, signed=True)),
        ("Endettement", debt),
    ])  # fmt: skip


def _score(c: Company) -> str:
    s = c.score
    if s is None:
        return ""
    rows = []
    for r in s.criteria:
        width = 0 if not r.max_points else 100 * r.points / r.max_points
        rows.append(
            f'<tr class="{"missing" if r.missing else ""}"><td>{escape(r.label)}</td>'
            f'<td class=num>{r.points:g}/{r.max_points:g}</td><td><span class="meter">'
            f'<i style="width:{width:.0f}%"></i></span></td><td>{escape(r.detail)}'
            f"{' <b class=nd>à obtenir</b>' if r.missing else ''}</td></tr>"
        )
    for p in s.penalties:
        rows.append(f'<tr class="pen"><td>{escape(p.label)}</td><td class=num>{p.points:g}</td>'
                    f"<td></td><td>{escape(p.detail)}</td></tr>")  # fmt: skip
    foot = (f"Score <b>{s.total:.0f}/100</b> · plafond {s.ceiling:.0f}/100 si les données manquantes "
            f"sont favorables · fiabilité {pct(s.confidence, 0)} du barème")  # fmt: skip
    return (f'<table class="score"><tbody>{"".join(rows)}</tbody></table>'
            f'<p class="foot">{foot}</p>')  # fmt: skip


def _valuation(plan: Financing | None, thesis: dict[str, Any]) -> str:
    if plan is None:
        return ('<p class="muted">Non calculable : EBE indisponible ou négatif. À obtenir lors du '
                "premier échange (liasses fiscales).</p>")  # fmt: skip
    val, fin = thesis.get("valuation") or {}, thesis.get("financing") or {}
    lo, hi = val.get("ebe_multiple_low", 4), val.get("ebe_multiple_high", 6)
    min_cov = fin.get("min_coverage", 1.3)
    cov_state = "confortable" if plan.coverage >= min_cov else "tendue"
    stack = (f'<div class="stack fin-stack"><i class="bar-debt" style="flex:{plan.senior_debt:.0f}">'
             f'</i><i class="bar-vendor" style="flex:{plan.vendor_loan:.0f}"></i>'
             f'<i class="bar-equity" style="flex:{max(plan.equity, 0):.0f}"></i></div>'
             f'<div class="legend"><span class="lg lg-debt">Dette senior</span><span class="lg '
             f'lg-vendor">Crédit vendeur</span><span class="lg lg-equity">Fonds propres</span></div>')  # fmt: skip
    table = _kv([
        ("EBE de référence", f"{eur(plan.ebe)} (exercice {plan.ebe_year or 'n.d.'})"),
        (f"Valeur d'entreprise ({lo:g}x à {hi:g}x l'EBE)",
         f"<b>{eur(plan.ev_low)} à {eur(plan.ev_high)}</b> · milieu {eur(plan.ev_mid)}"),
        ("Dette senior", f"{eur(plan.senior_debt)} ({mult(plan.senior_debt / plan.ebe)} l'EBE)"),
        ("Crédit vendeur", eur(plan.vendor_loan)),
        ("Fonds propres à réunir", f"<b>{eur(plan.equity)}</b> ({pct(plan.equity_share, 0)} du prix)"),
        ("Service annuel de la dette", eur(plan.annual_debt_service)),
        ("Couverture du service de la dette", f"{mult(plan.coverage)} ({cov_state}, seuil "
                                                f"{mult(min_cov)})"),
    ])  # fmt: skip
    debt_x = f"{fin.get('senior_debt_multiple', 2.5):g}".replace(".", ",")
    assumptions = (f"Hypothèses (config/thesis.yaml) : dette senior {debt_x}x "
                   f"l'EBE plafonnée à {pct(fin.get('max_debt_share', 0.6), 0)} du prix, amortie sur "
                   f"{fin.get('amortization_years', 7)} ans à {pct(fin.get('interest_rate', 0.055))}, "
                   f"{pct(fin.get('cash_conversion', 0.6), 0)} de l'EBE disponible pour la dette.")  # fmt: skip
    return (stack + table + f'<p class="muted small">{escape(assumptions)} Ordre de grandeur : ni dette '
            "nette, ni BFR, ni EBE normalisé. Ce n'est ni une évaluation ni un avis.</p>")  # fmt: skip


def _signals(d: Dossier) -> str:
    rows = (
        "".join(
            f'<tr><td><span class="lvl lvl-{"high" if s.level == "élevé" else "mid" if s.level == "moyen" else "info"}">'
            f"{escape(s.level)}</span></td><td><b>{escape(s.title)}</b><br><small>{escape(s.detail)}</small></td>"
            f"<td><small>{escape(s.theme)}</small></td></tr>"
            for s in d.signals
        )
        or '<tr><td colspan="3" class="muted">Aucun signal factuel.</td></tr>'
    )
    ai = ""
    a = d.company.analysis
    if a and a.red_flags:
        ai = ("<h4>Hypothèses de l'IA, à vérifier</h4><ul>"
              + "".join(f"<li>{escape(x)}</li>" for x in a.red_flags) + "</ul>")  # fmt: skip
    return f'<table class="signals"><tbody>{rows}</tbody></table>{ai}'


def _gaps(c: Company) -> str:
    gaps = data_gaps(c)
    g = (
        "".join(f"<li>{escape(x)}</li>" for x in gaps)
        or "<li>Aucune donnée manquante au score.</li>"
    )
    docs = "".join(f"<li>{escape(x)}</li>" for x in DOCUMENTS)
    return (f'<div class="grid2"><div><h4>Données manquantes au score</h4><ul>{g}</ul></div>'
            f"<div><h4>Documents à demander</h4><ul class=check>{docs}</ul></div></div>")  # fmt: skip


def _questions(d: Dossier) -> str:
    triggered = {s.question for s in d.signals}
    qs = dd_questions(d.signals)
    blocks = []
    for theme in DD_THEMES:
        items = "".join(
            f'<li class="{"trig" if q in triggered else ""}">{escape(q)}</li>' for q in qs[theme]
        )
        blocks.append(f'<div class="qblock"><h4>{escape(theme)}</h4><ul>{items}</ul></div>')
    return ('<p class="muted small">● question déclenchée par un signal factuel de ce dossier.</p>'
            f'<div class="qgrid">{"".join(blocks)}</div>')  # fmt: skip


def _draft(c: Company, footer: str | None) -> str:
    a = c.analysis
    if a is None:
        return '<p class="muted">Brouillon non généré : lancer `pme-radar draft`.</p>'
    body = escape(with_footer(a.email_body, footer)).replace("\n", "<br>")
    return (f'<div class="mail"><span class="stampx">À relire · jamais envoyé automatiquement</span>'
            f"<p><b>Objet : {escape(a.email_subject)}</b></p><p>{body}</p></div>")  # fmt: skip


def _dossier(d: Dossier, thesis: dict[str, Any], as_of: date, footer: str | None) -> str:
    c, s = d.company, d.company.score
    assert s is not None
    why = c.analysis.mini_thesis if c.analysis else [s.summary]
    reasons = "".join(f"<li>{escape(r)}</li>" for r in d.rec.reasons)
    steps = "".join(f"<li>{escape(r)}</li>" for r in d.rec.next_steps)
    why_items = "".join(f"<li>{escape(w)}</li>" for w in why)
    return f"""<section class="dossier" id="d-{c.siren}">
<div class="d-head"><div><h2>{_e(c.name)}</h2><p class="muted">{_e(c.naf_label)} · {_e(c.city)}
({_e(c.department)}) · SIREN {_e(c.siren)}</p></div>
<div class="gauge" style="--v:{s.total:.0f}"><b>{s.total:.0f}</b><small>/100</small></div>{_badge(d.rec)}</div>
<div class="grid2"><div class="box box-{d.rec.tone}"><h3>Recommandation : {escape(d.rec.label)}</h3>
<ul>{reasons}</ul><h4>Prochaines étapes</h4><ol>{steps}</ol></div>
<div class="box"><h3>Pourquoi cette cible</h3><ul>{why_items}</ul></div></div>
<h3>Identité et gouvernance</h3>{_identity(c, as_of)}
<h3>Données financières</h3>{_financials(c)}
<h3>Score détaillé</h3>{_score(c)}
<h3>Valorisation et montage indicatifs</h3>{_valuation(d.plan, thesis)}
<h3>Signaux factuels</h3>{_signals(d)}
<h3>Données et documents à obtenir</h3>{_gaps(c)}
<h3>Questions de due diligence</h3>{_questions(d)}
<h3>Brouillon d'approche</h3>{_draft(c, footer)}
</section>"""


def _annex(scoring_cfg: dict[str, Any], thesis: dict[str, Any]) -> str:
    crit = scoring_cfg.get("criteria", {})
    names = {"director_age": "Âge du dirigeant", "owner_operator": "Dirigeant-exploitant",
             "no_obvious_successor": "Pas de successeur évident", "revenue": "Chiffre d'affaires",
             "headcount": "Effectif", "profitability": "Rentabilité (EBE, sinon marge nette)",
             "revenue_cagr": "Régularité du CA", "company_age": "Ancienneté",
             "thesis_fit": "Adéquation à la thèse"}  # fmt: skip
    rows = "".join(f"<tr><td>{escape(names.get(k, k))}</td><td class=num>{v.get('max_points', 0)}</td></tr>"
                   for k, v in crit.items())  # fmt: skip
    pens = ", ".join(f"{escape(k)} {v}" for k, v in (scoring_cfg.get("penalties") or {}).items())
    return f"""<section class="annex"><h2>Méthodologie et limites</h2>
<div class="grid2"><div><h4>Barème (100 points)</h4><table class="kv">{rows}</table>
<p class="small muted">Pénalités : {pens}. Seuil de qualification : {scoring_cfg.get("qualified_threshold", 70)}.
Donnée manquante = 0 point et mention « à obtenir » ; le plafond indique le score atteignable si elle
est favorable.</p></div>
<div><h4>Sources</h4><ul><li>API Recherche d'entreprises (data.gouv.fr) : identité, dirigeants, chiffre
d'affaires.</li><li>BODACC : procédures collectives.</li><li>Ratios BCE/INPI : EBE, endettement, historique.</li></ul>
<h4>Limites</h4><ul><li>Données publiques, parfois anciennes ou confidentielles.</li><li>Valorisation et
montage : ordres de grandeur pour décider d'un appel, pas une évaluation.</li><li>Les hypothèses de l'IA
et les brouillons sont relus par un humain ; rien n'est envoyé automatiquement.</li></ul></div></div>
</section>"""


CSS = """
:root{--ink:#1d1f33;--muted:#5d6185;--line:#e3e5f0;--soft:#f4f5fa;--cyan:#1594c2;--cyan-l:#e6f6fc;
--go:#14855f;--go-l:#e4f6ef;--dig:#b26a00;--dig-l:#fff3df;--doc:#4c5bd4;--doc-l:#eceffd;--low:#6b6f8e;
--low-l:#eff0f5;--out:#c23a52;--out-l:#fdecef}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#eef0f6;color:var(--ink);font:14.5px/1.5 Inter,"Segoe UI",Helvetica,Arial,sans-serif}
.cover{background:linear-gradient(135deg,#14142a 0%,#24244c 100%);color:#fff;padding:40px 56px 34px}
.cover .brand{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:700}
.cover .brand span{color:#25c2f5}.cover h1{font-size:34px;margin:22px 0 6px;letter-spacing:-.02em}
.cover p{margin:4px 0;color:#c9cdf0}.cover .conf{margin-top:14px;font-size:12.5px;color:#ffb547}
main{max-width:1000px;margin:0 auto;background:#fff;padding:12px 56px 40px}
section{margin-top:26px}h2{font-size:22px;margin:0 0 12px;letter-spacing:-.01em}
h3{font-size:16px;margin:22px 0 8px;padding-bottom:4px;border-bottom:2px solid var(--line)}
h4{font-size:13.5px;margin:10px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse;margin:6px 0}th,td{padding:7px 9px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}thead th{background:var(--soft);font-size:12.5px;color:var(--muted)}
.num{text-align:right;white-space:nowrap}.kv th{width:34%;color:var(--muted);font-weight:500}
.muted{color:var(--muted)}.small{font-size:12.5px}small{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpi{background:var(--soft);border-radius:12px;
padding:12px 14px;border-top:3px solid var(--cyan)}.kpi b{display:block;font-size:26px}.kpi span{font-weight:600}
.kpi small{display:block}.stack{display:flex;height:14px;border-radius:7px;overflow:hidden;margin:16px 0 6px;gap:2px}
.stack i{display:block}.bar-go{background:var(--go)}.bar-dig{background:var(--dig)}.bar-doc{background:var(--doc)}
.bar-low{background:#c5c8da}.bar-out{background:var(--out)}.bar-debt{background:#1594c2}.bar-vendor{background:#7fd0ec}
.bar-equity{background:#14142a}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
.lg:before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.lg-go:before{background:var(--go)}.lg-dig:before{background:var(--dig)}.lg-doc:before{background:var(--doc)}
.lg-low:before{background:#c5c8da}.lg-out:before{background:var(--out)}.lg-debt:before{background:#1594c2}
.lg-vendor:before{background:#7fd0ec}.lg-equity:before{background:#14142a}.points li{margin:4px 0}
.reco{display:inline-block;padding:4px 11px;border-radius:999px;font-size:12.5px;font-weight:700;white-space:nowrap}
.reco-go{background:var(--go-l);color:var(--go)}.reco-dig{background:var(--dig-l);color:var(--dig)}
.reco-doc{background:var(--doc-l);color:var(--doc)}.reco-low{background:var(--low-l);color:var(--low)}
.reco-out{background:var(--out-l);color:var(--out)}.rank a{color:var(--ink);font-weight:600;text-decoration:none}
.dossier{border-top:6px solid #14142a;padding-top:18px;margin-top:40px}
.d-head{display:flex;align-items:center;gap:18px}.d-head>div:first-child{flex:1}.d-head h2{margin:0}
.gauge{--v:0;width:84px;height:84px;border-radius:50%;display:grid;place-content:center;text-align:center;
background:radial-gradient(closest-side,#fff 76%,transparent 77% 100%),conic-gradient(var(--cyan) calc(var(--v)*1%),#e6e8f2 0)}
.gauge b{font-size:24px;line-height:1}.gauge small{font-size:11px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.box{background:var(--soft);border-radius:12px;padding:12px 16px}
.box h3{border:0;margin:4px 0 6px}.box-go{background:var(--go-l)}.box-dig{background:var(--dig-l)}
.box-doc{background:var(--doc-l)}.box-out{background:var(--out-l)}.box ul,.box ol{margin:4px 0;padding-left:20px}
.meter{display:block;height:8px;background:#e6e8f2;border-radius:4px;overflow:hidden;width:120px}
.meter i{display:block;height:100%;background:var(--cyan)}.score tr.missing td{color:var(--muted)}
.score tr.pen td{color:var(--out)}.nd{font-size:11px;color:var(--doc);background:var(--doc-l);padding:1px 6px;border-radius:5px}
.foot{font-size:13px;margin:6px 0}.lvl{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700}
.lvl-high{background:var(--out-l);color:var(--out)}.lvl-mid{background:var(--dig-l);color:var(--dig)}
.lvl-info{background:var(--soft);color:var(--muted)}.txt-red{color:var(--out);font-weight:600}
.qgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.qblock{background:var(--soft);border-radius:10px;padding:8px 12px}
.qblock ul{padding-left:16px;margin:4px 0}.qblock li{margin:3px 0;font-size:13px}.qblock li.trig{font-weight:600}
.qblock li.trig::marker{content:"● ";color:var(--dig)}ul.check{list-style:"☐  "}
.mail{border:1px solid var(--line);border-radius:12px;padding:14px 18px;font-size:13.5px;background:#fbfbfe}
.stampx{display:inline-block;color:var(--out);border:2px solid var(--out);border-radius:6px;padding:2px 8px;
font-size:11.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase}
.annex{border-top:1px solid var(--line);padding-top:12px}
@page{size:A4;margin:13mm}
@media print{body{background:#fff;font-size:12.5px}main{max-width:none;padding:0 4px}.cover{padding:26px 30px}
.dossier{break-before:page;margin-top:0}.box,.qblock,.mail,.kpi,.kv,.score,.fin,.signals{break-inside:avoid}
h2,h3,h4{break-after:avoid}tr{break-inside:avoid}}
"""


def build_report(
    companies: list[Company],
    scoring_cfg: dict[str, Any],
    thesis: dict[str, Any],
    campaign: pd.DataFrame | None = None,
    top_n: int = 10,
    sirens: list[str] | None = None,
    footer: str | None = None,
    as_of: date | None = None,
) -> tuple[str, list[Dossier]]:
    """(HTML, dossiers détaillés)."""
    as_of = as_of or date.today()
    dossiers = evaluate(companies, scoring_cfg, thesis, as_of)
    chosen = select(dossiers, top_n, sirens)
    synthetic = bool(companies) and all(c.siren.startswith("999") for c in companies)
    source = (
        "échantillon synthétique (démonstration)" if synthetic else "données publiques (open data)"
    )
    body = (_summary_section(dossiers, scoring_cfg, campaign) + _ranking_section(chosen)
            + "".join(_dossier(d, thesis, as_of, footer) for d in chosen)
            + _annex(scoring_cfg, thesis))  # fmt: skip
    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapport de deal flow · pme-radar</title><style>{CSS}</style></head><body>
<header class="cover"><div class="brand">{LOGO}<div>pme<span>-</span>radar</div></div>
<h1>Rapport de deal flow</h1><p>Thèse : {escape(str(thesis.get("name", "")))}</p>
<p>Édité le {as_of:%d/%m/%Y} · {len(dossiers)} sociétés notées · {len(chosen)} dossiers détaillés · source :
{source}</p><p class="conf">Document de travail confidentiel : il contient des données personnelles de
dirigeants (RGPD). Ne pas diffuser ; à conserver dans data/, jamais dans le dépôt.</p></header>
<main>{body}</main></body></html>"""
    return html, chosen
