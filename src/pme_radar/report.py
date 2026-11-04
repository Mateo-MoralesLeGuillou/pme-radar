"""Rapport de deal flow, au format d'un mémo de pré-due diligence (private equity / M&A).

Structure : page de garde · 1. synthèse exécutive · 2. vue d'ensemble des cibles (tableau de
pipeline, football field des valorisations) · 3. un dossier par cible (profil, thèse
d'investissement, points de vigilance, financiers, score, valorisation et sensibilité, sources et
emplois, signaux, plan de due diligence, demandes d'informations, prochaines étapes) ·
4. méthodologie, hypothèses et avertissement. HTML autonome (aucune ressource externe), lisible à
l'écran et imprimable en PDF A4 (ADR-020, ADR-022).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from html import escape
from statistics import median
from typing import Any

import pandas as pd

from . import labels
from .deal import (
    DEFAULT_FINANCING,
    DEFAULT_VALUATION,
    Financing,
    Recommendation,
    data_gaps,
    dd_plan,
    financing_plan,
    highlights,
    information_requests,
    recommend,
    sensitivity,
)
from .fmt import NNBSP, eur, mult, pct
from .models import Company, Stage
from .outreach import with_footer
from .risks import Signal, assess

ORDER = {"go": 0, "dig": 1, "doc": 2, "low": 3, "out": 4}
ACTIONS = {
    "go": "Relire et envoyer le brouillon d'approche ; préparer l'appel découverte.",
    "dig": "Lever le point de vigilance (données, questions prioritaires) avant toute approche.",
    "doc": "Obtenir les données manquantes : un premier échange peut qualifier la cible.",
}
TONE_LABELS = [("go", "À approcher"), ("dig", "À creuser"), ("doc", "À documenter"),
               ("low", "Non prioritaire"), ("out", "Écartée")]  # fmt: skip
LOGO = (
    '<svg viewBox="0 0 128 128" width="40" height="40" aria-hidden="true"><defs>'
    '<linearGradient id="rs" x1="64" y1="64" x2="108" y2="18" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#25c2f5" stop-opacity="0"/><stop offset="1" stop-color="#25c2f5" '
    'stop-opacity=".9"/></linearGradient></defs><circle cx="64" cy="64" r="60" fill="#13294b"/>'
    '<g fill="none" stroke="#25c2f5"><circle cx="64" cy="64" r="58" stroke-opacity=".5" '
    'stroke-width="3"/><circle cx="64" cy="64" r="40" stroke-opacity=".3" stroke-width="2.5"/>'
    '<circle cx="64" cy="64" r="22" stroke-opacity=".25" stroke-width="2"/></g>'
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


# ---------------------------------------------------------------- formats
_ND = '<span class="nd">n.d.</span>'


def _e(v: object) -> str:
    return _ND if v is None or v == "" else escape(str(v))


def _code(text: str) -> str:
    """Échappe le texte et rend les `commandes` en police à chasse fixe."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(text))


def keur(v: float | None) -> str:
    """Milliers d'euros au format comptable : 7 300 ; négatifs entre parenthèses."""
    if v is None:
        return '<span class="nd">n.d.</span>'
    k = round(v / 1000)
    text = f"{abs(k):,}".replace(",", NNBSP)
    return f"({text})" if k < 0 else text


def meur(v: float) -> str:
    return f"{v / 1e6:.2f}".replace(".", ",")


def _x(v: float) -> str:
    return f"{v:g}".replace(".", ",") + "x"


def _badge(rec: Recommendation) -> str:
    return f'<span class="reco reco-{rec.tone}">{escape(rec.label)}</span>'


def _sector(c: Company) -> str:
    label = c.naf_label or ""
    return escape(label if len(label) <= 46 else label[:44].rstrip() + "…")


# ---------------------------------------------------------------- graphiques SVG
def _svg_funnel(steps: list[tuple[str, int]]) -> str:
    w, row, label_w = 380, 30, 112
    top = max([n for _, n in steps] + [1])
    parts = []
    for i, (label, n) in enumerate(steps):
        y = i * row
        bw = (w - label_w - 60) * n / top
        parts.append(
            f'<text x="{label_w - 10}" y="{y + 19}" text-anchor="end" class="sv-l">{escape(label)}</text>'
            f'<rect x="{label_w}" y="{y + 5}" width="{max(bw, 2):.1f}" height="20" rx="2" '
            f'class="sv-b{min(i, 4)}"/><text x="{label_w + bw + 7:.1f}" y="{y + 19}" class="sv-v">{n}</text>'
        )
    return f'<svg viewBox="0 0 {w} {row * len(steps)}" class="chart">{"".join(parts)}</svg>'


def _nice_step(max_v: float) -> float:
    for step in (0.25e6, 0.5e6, 1e6, 2e6, 2.5e6, 5e6, 10e6, 20e6):
        if max_v / step <= 6:
            return step
    return 50e6


def _svg_football(rows: list[tuple[str, float, float, float]]) -> str:
    """Football field : une barre par cible de la valeur basse à la valeur haute, milieu marqué."""
    w, row, label_w, right, pad = 720, 30, 235, 70, 36
    max_v = max(h for *_, h in rows) * 1.08
    plot = w - label_w - right - pad

    def x(v: float) -> float:  # marge à gauche de l'axe : place pour la valeur basse
        return label_w + pad + plot * v / max_v

    h = row * len(rows) + 34
    parts = []
    step = _nice_step(max_v)
    tick = 0.0
    while tick <= max_v:
        label = f"{tick / 1e6:g}".replace(".", ",")
        parts.append(f'<line x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="0" y2="{h - 26}" class="sv-grid"/>'
                     f'<text x="{x(tick):.1f}" y="{h - 10}" text-anchor="middle" class="sv-t">{label}</text>')  # fmt: skip
        tick += step
    parts.append(f'<text x="{w - right + 10}" y="{h - 10}" class="sv-t">M€</text>')
    for i, (label, lo, mid, hi) in enumerate(rows):
        y = i * row + 4
        name = label if len(label) <= 32 else label[:30].rstrip() + "…"
        parts.append(
            f'<text x="{label_w - 12}" y="{y + 16}" text-anchor="end" class="sv-l">{escape(name)}</text>'
            f'<rect x="{x(lo):.1f}" y="{y + 4}" width="{x(hi) - x(lo):.1f}" height="16" rx="2" class="sv-range"/>'
            f'<line x1="{x(mid):.1f}" x2="{x(mid):.1f}" y1="{y}" y2="{y + 24}" class="sv-mid"/>'
            f'<text x="{x(lo) - 5:.1f}" y="{y + 16}" text-anchor="end" class="sv-n">{meur(lo)}</text>'
            f'<text x="{x(hi) + 5:.1f}" y="{y + 16}" class="sv-n">{meur(hi)}</text>'
        )
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(parts)}</svg>'


def _svg_revenue(c: Company) -> str:
    years = [f for f in c.financials if f.revenue is not None][-5:]
    if not years:
        return ""
    w, h, base, bw = 300, 150, 120, 34
    top = max(f.revenue or 0 for f in years) or 1
    gap = (w - 20 - bw * len(years)) / max(len(years), 1)
    parts = []
    for i, f in enumerate(years):
        x = 10 + gap / 2 + i * (bw + gap)
        bh = 88 * (f.revenue or 0) / top
        parts.append(
            f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="2" class="sv-b0"/>'
            f'<text x="{x + bw / 2:.1f}" y="{base - bh - 5:.1f}" text-anchor="middle" class="sv-n">'
            f"{meur(f.revenue or 0)}</text>"
            f'<text x="{x + bw / 2:.1f}" y="{base + 16}" text-anchor="middle" class="sv-t">{f.year}</text>'
        )
    parts.append(f'<line x1="6" x2="{w - 6}" y1="{base}" y2="{base}" class="sv-axis"/>')
    return (f'<svg viewBox="0 0 {w} {h}" class="chart small-chart">{"".join(parts)}</svg>'
            '<p class="note">Chiffre d\'affaires, M€.</p>')  # fmt: skip


# ---------------------------------------------------------------- sections
def _cover(thesis: dict[str, Any], dossiers: list[Dossier], chosen: list[Dossier], source: str,
           as_of: date) -> str:  # fmt: skip
    qualified = sum(d.company.stage == Stage.QUALIFIED for d in dossiers)
    return f"""<section class="cover">
<div class="cover-top"><div class="brand">{LOGO}<span>pme<i>-</i>radar</span></div>
<span class="conf-pill">Strictement confidentiel</span></div>
<div class="cover-mid"><p class="kicker">Deal flow · Origination search fund</p>
<h1>Rapport de pré-due diligence</h1><p class="thesis">{escape(str(thesis.get("name", "")))}</p>
<table class="cover-meta"><tr><th>Date</th><td>{as_of:%d/%m/%Y}</td></tr>
<tr><th>Périmètre</th><td>{len(dossiers)} sociétés notées · {qualified} qualifiées</td></tr>
<tr><th>Dossiers détaillés</th><td>{len(chosen)}</td></tr><tr><th>Source</th><td>{escape(source)}</td></tr>
<tr><th>Préparé par</th><td>pme-radar · moteur d'origination open source</td></tr></table></div>
<div class="cover-bottom">Document de travail confidentiel. Il contient des données personnelles de
dirigeants (RGPD) : diffusion interne uniquement, conservation dans <code>data/</code>, jamais dans
le dépôt. Valeurs et montages sont des ordres de grandeur, pas une évaluation.</div></section>"""


def _summary(dossiers: list[Dossier], chosen: list[Dossier], scoring_cfg: dict[str, Any],
             campaign: pd.DataFrame | None) -> str:  # fmt: skip
    total = len(dossiers)
    tones = Counter(d.rec.tone for d in dossiers)
    qualified = [d for d in dossiers if d.company.stage == Stage.QUALIFIED]
    threshold = scoring_cfg.get("qualified_threshold", 70)
    sent = replies = meetings = 0
    if campaign is not None and len(campaign):
        status = campaign["status"]
        sent = int(status.isin(["contacted", "replied", "meeting", "declined", "bounced"]).sum())
        replies = int(status.isin(["replied", "meeting", "declined"]).sum())
        meetings = int((status == "meeting").sum())
    kpis = [("Sociétés notées", str(total), "périmètre du run"),
            ("Qualifiées", str(len(qualified)), f"score ≥ {threshold}/100"),
            ("À approcher", str(tones["go"]), "recommandation"),
            ("À creuser · à documenter", str(tones["dig"] + tones["doc"]), "un point à lever"),
            ("Rendez-vous", str(meetings), f"{sent} contact(s) envoyé(s)")]  # fmt: skip
    kpi_html = "".join(f'<div class="kpi"><b>{v}</b><span>{escape(k)}</span><small>{escape(s)}</small></div>'
                       for k, v, s in kpis)  # fmt: skip
    msgs = []
    if total:
        msgs.append(f"<b>{len(qualified)} cibles qualifiées</b> sur {total} sociétés notées "
                    f"({pct(len(qualified) / total, 0)}) ; <b>{tones['go']} recommandées à l'approche</b>.")  # fmt: skip
    if qualified:
        med = median(d.company.score.total for d in qualified if d.company.score)
        conf = sum(d.company.score.confidence for d in qualified if d.company.score) / len(
            qualified
        )
        msgs.append(f"Score médian des qualifiées : <b>{med:.0f}/100</b>, établi sur "
                    f"{pct(conf, 0)} du barème en moyenne.")  # fmt: skip
    plans = [d.plan for d in dossiers if d.rec.tone == "go" and d.plan]
    if plans:
        msgs.append(f"Valeur d'entreprise indicative des cibles à approcher : de "
                    f"<b>{eur(min(p.ev_low for p in plans))} à {eur(max(p.ev_high for p in plans))}</b> "
                    f"(médiane {eur(median(p.ev_mid for p in plans))}) ; fonds propres médians à réunir : "
                    f"<b>{eur(median(p.equity for p in plans))}</b>.")  # fmt: skip
    if tones["doc"]:
        msgs.append(f"<b>{tones['doc']} cibles à documenter</b> : sous le seuil, mais des données "
                    "manquantes pourraient les qualifier ; un appel peut trancher.")  # fmt: skip
    if campaign is not None and len(campaign):
        msgs.append(
            f"Campagne : {sent} contact(s) envoyé(s), {replies} réponse(s), {meetings} rendez-vous."
            if sent
            else f"Campagne : {len(campaign)} brouillon(s) prêt(s) à relire, aucun envoi à ce jour."
        )
    vigilance = Counter(s.title for d in chosen for s in d.signals if s.level in ("élevé", "moyen"))
    if vigilance:
        title, n = vigilance.most_common(1)[0]
        msgs.append(f"Point de vigilance le plus fréquent dans les dossiers : « {escape(title)} » "
                    f"({n} sur {len(chosen)}).")  # fmt: skip
    funnel = [
        ("Sociétés notées", total),
        ("Qualifiées", len(qualified)),
        ("À approcher", tones["go"]),
    ]
    if sent:
        funnel += [("Contactées", sent), ("Rendez-vous", meetings)]
    bar = "".join(
        f'<i class="bar-{t}" style="flex:{tones[t]}"></i>' for t, _ in TONE_LABELS if tones[t]
    )
    legend = "".join(f'<span class="lg lg-{t}">{escape(lbl)} · {tones[t]}</span>'
                     for t, lbl in TONE_LABELS if tones[t])  # fmt: skip
    first = f"#d-{chosen[0].company.siren}" if chosen else "#pipeline"
    split = ", ".join(
        f"{n} {lbl.lower()}"
        for t, lbl in TONE_LABELS
        if (n := sum(d.rec.tone == t for d in chosen))
    )
    toc = "".join(
        f'<a href="{href}"><b>{n}</b><span>{title}</span><small>{sub}</small></a>'
        for n, href, title, sub in [
            (1, "#synthese", "Synthèse exécutive", "chiffres clés, plan d'action"),
            (2, "#pipeline", "Vue d'ensemble des cibles", "tableau comparatif, valorisations"),
            (
                3,
                first,
                "Dossiers de pré-due diligence",
                f"{len(chosen)} dossier(s) : {split}" if chosen else "aucun",
            ),
            (4, "#methode", "Méthodologie et avertissement", "barème, hypothèses, sources"),
        ]
    )
    actions = ""
    for tone, label in TONE_LABELS[:3]:
        group = [d for d in chosen if d.rec.tone == tone]
        if group:
            names = ", ".join(f'<a href="#d-{d.company.siren}"><b>{escape(d.company.name)}</b></a>'
                              for d in group)  # fmt: skip
            actions += (f'<tr><td><span class="reco reco-{tone}">{escape(label)}</span></td>'
                        f"<td>{names}</td><td>{ACTIONS[tone]}</td></tr>")  # fmt: skip
    if actions:
        actions = (f'<h3>Plan d\'action</h3><table class="tbl actions"><thead><tr><th>Décision</th>'
                   f"<th>Cibles (dossiers détaillés)</th><th>Prochaine étape</th></tr></thead>"
                   f"<tbody>{actions}</tbody></table>")  # fmt: skip
    return f"""<section class="sheet" id="synthese">
<header class="sec"><span class="num">1</span><h2>Synthèse exécutive</h2></header>
<div class="kpis">{kpi_html}</div>
<div class="grid2"><div><h3>Messages clés</h3><ul class="key">{"".join(f"<li>{m}</li>" for m in msgs)}</ul></div>
<div><h3>Entonnoir d'origination</h3>{_svg_funnel(funnel)}
<h3>Recommandations</h3><div class="stack">{bar}</div><div class="legend">{legend}</div></div></div>
{actions}<h3>Sommaire</h3><nav class="toc">{toc}</nav></section>"""


def _svg_hbars(items: list[tuple[str, int]], cls: str = "sv-b1") -> str:
    """Barres horizontales libellées (répartitions)."""
    w, row, label_w = 380, 24, 170
    top = max([n for _, n in items] + [1])
    parts = []
    for i, (label, n) in enumerate(items):
        y = i * row
        bw = (w - label_w - 34) * n / top
        name = label if len(label) <= 26 else label[:24].rstrip() + "…"
        parts.append(
            f'<text x="{label_w - 8}" y="{y + 16}" text-anchor="end" class="sv-l">{escape(name)}</text>'
            f'<rect x="{label_w}" y="{y + 4}" width="{max(bw, 2):.1f}" height="16" rx="2" class="{cls}"/>'
            f'<text x="{label_w + bw + 6:.1f}" y="{y + 16}" class="sv-v">{n}</text>'
        )
    return f'<svg viewBox="0 0 {w} {row * len(items) + 4}" class="chart">{"".join(parts)}</svg>'


def _pipeline(dossiers: list[Dossier], chosen: list[Dossier], thesis: dict[str, Any]) -> str:
    rows = []
    for i, d in enumerate(chosen, 1):
        c, p, s = d.company, d.plan, d.company.score
        assert s is not None
        ceiling = f" <small>→ {s.ceiling:.0f}</small>" if s.ceiling > s.total + 0.5 else ""
        rows.append(
            f'<tr><td class="c">{i}</td><td><a href="#d-{c.siren}"><b>{_e(c.name)}</b></a>'
            f"<br><small>{_sector(c)} · {_e(c.city)} ({_e(c.department)})</small></td>"
            f"<td class=num>{keur(c.revenue_last)}</td><td class=num>{pct(c.ebe_margin)}</td>"
            f"<td class=num>{f'{meur(p.ev_low)} – {meur(p.ev_high)}' if p else _ND}</td>"
            f"<td class=num>{meur(p.equity) if p else _ND}</td>"
            f"<td class=num><b>{s.total:.0f}</b>{ceiling}<br><small>fiab. {pct(s.confidence, 0)}</small></td>"
            f"<td>{_badge(d.rec)}</td></tr>"
        )
    field = [
        (d.company.name, d.plan.ev_low, d.plan.ev_mid, d.plan.ev_high) for d in chosen if d.plan
    ]
    val = {**DEFAULT_VALUATION, **(thesis.get("valuation") or {})}
    chart = (f"<h3>Valorisation indicative des cibles (football field)</h3>{_svg_football(field)}"
             f'<p class="note">Valeur d\'entreprise = EBE × {_x(val["ebe_multiple_low"])} à '
             f'{_x(val["ebe_multiple_high"])}, en M€ ; trait vertical : milieu de fourchette. Cibles sans '
             "EBE publié non représentées.</p>") if field else ""  # fmt: skip
    qualified = [d.company for d in dossiers if d.company.stage == Stage.QUALIFIED]
    by_dept = Counter(labels.department(c.department) for c in qualified).most_common(8)
    by_naf = Counter(c.naf_label or "n.d." for c in qualified).most_common(8)
    dist = (f"<h3>Répartition des {len(qualified)} cibles qualifiées du périmètre</h3><div class=\"grid2\">"
            f"<div><h4>Par département</h4>{_svg_hbars(by_dept)}</div>"
            f"<div><h4>Par activité</h4>{_svg_hbars(by_naf, 'sv-b3')}</div></div>") if qualified else ""  # fmt: skip
    return f"""<section class="sheet" id="pipeline">
<header class="sec"><span class="num">2</span><h2>Vue d'ensemble des cibles</h2></header>
<table class="tbl pipe"><thead><tr><th>#</th><th>Entreprise · activité · localisation</th>
<th class=num>CA<br>(k€)</th><th class=num>Marge<br>d'EBE</th><th class=num>VE indicative<br>(M€)</th>
<th class=num>Fonds propres<br>(M€)</th><th class=num>Score</th><th>Recommandation</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
<p class="note">Score : plancher officiel (→ plafond si les données manquantes sont favorables) ; fiab. : part
du barème évaluée sur des données réelles. VE : fourchette de valeur d'entreprise ; fonds propres : à réunir
au milieu de fourchette (montage détaillé dans chaque dossier).</p>{chart}{dist}</section>"""


def _profile_table(c: Company, as_of: date) -> str:
    person = c.main_person()
    age = f", {c.director_age} ans" if c.director_age is not None else ""
    owner = (f"via {escape(c.holding_name)}" if c.holding_name
             else "personne physique" if c.is_owner_operator else "société (groupe)" if c.is_owner_operator is False
             else "n.d.")  # fmt: skip
    bodacc = {True: '<span class="neg-txt">procédure publiée</span>', False: "aucune procédure",
              None: "non interrogé"}[c.has_collective_procedure]  # fmt: skip
    rows = [
        ("Chiffre d'affaires", f"{eur(c.revenue_last)}" + (f" ({_last_year(c)})" if _last_year(c) else "")),
        ("Croissance annuelle", pct(c.revenue_cagr, signed=True)),
        ("EBE", f"{eur(c.ebe)}" + (f" ({c.ebe_year})" if c.ebe_year else "")),
        ("Marge d'EBE", pct(c.ebe_margin)),
        ("Résultat net", eur(c.net_income_last)),
        ("Effectif", escape(labels.headcount(c.headcount_band))),
        ("Création", f"{c.creation_date:%Y} ({c.company_age_years} ans)" if c.creation_date else "n.d."),
        ("Dirigeant", f"{_e(person.name if person else None)}{age}"),
        ("Détention", owner),
        ("Endettement", "n.d." if c.debt_ratio is None else f"{c.debt_ratio:.0f}{NNBSP}% des fonds propres"),
        ("BODACC", bodacc),
    ]  # fmt: skip
    return "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)


def _last_year(c: Company) -> int | None:
    years = [f.year for f in c.financials if f.revenue is not None]
    return years[-1] if years else None


def _financials(c: Company) -> str:
    years = [f for f in c.financials if f.revenue is not None or f.net_income is not None][-5:]
    if not years:
        return ('<p class="muted">Aucun compte publié dans les sources ouvertes : liasses fiscales à '
                "obtenir en priorité (voir les demandes d'informations).</p>")  # fmt: skip
    head = "".join(f"<th class=num>{f.year}</th>" for f in years)

    def row(label: str, cells: list[str], cls: str = "") -> str:
        return (
            f'<tr class="{cls}"><th>{label}</th>'
            + "".join(f"<td class=num>{x}</td>" for x in cells)
            + "</tr>"
        )

    growth: list[str] = []
    prev_revenue: float | None = None
    for f in years:
        if prev_revenue and f.revenue is not None:
            growth.append(pct(f.revenue / prev_revenue - 1, signed=True))
        else:
            growth.append("—")
        prev_revenue = f.revenue
    margins = [pct(f.net_income / f.revenue) if f.revenue and f.net_income is not None else "n.d."
               for f in years]  # fmt: skip
    ebe_cells = [keur(c.ebe) if c.ebe_year == f.year else "—" for f in years]
    ebe_m = [pct(c.ebe_margin) if c.ebe_year == f.year else "—" for f in years]
    table = (f'<table class="tbl fin"><thead><tr><th>En k€</th>{head}</tr></thead><tbody>'
             + row("Chiffre d'affaires", [keur(f.revenue) for f in years], "strong")
             + row("Croissance", growth, "sub")
             + row("EBE", ebe_cells)
             + row("Marge d'EBE", ebe_m, "sub")
             + row("Résultat net", [keur(f.net_income) for f in years])
             + row("Marge nette", margins, "sub") + "</tbody></table>")  # fmt: skip
    note = ('<p class="note">Sources : API Recherche d\'entreprises (data.gouv.fr), ratios BCE/INPI. '
            "EBE publié pour le seul dernier exercice disponible. Analyse pme-radar.</p>")  # fmt: skip
    return f'<div class="grid-fin"><div>{table}{note}</div><div>{_svg_revenue(c)}</div></div>'


def _scorecard(c: Company) -> str:
    s = c.score
    assert s is not None
    rows = []
    for r in s.criteria:
        width = 0 if not r.max_points else 100 * r.points / r.max_points
        nd = ' <span class="tag-doc">à obtenir</span>' if r.missing else ""
        rows.append(f'<tr class="{"missing" if r.missing else ""}"><td>{escape(r.label)}</td>'
                    f'<td class=num>{r.points:g}</td><td class=num>{r.max_points:g}</td>'
                    f'<td><span class="meter"><i style="width:{width:.0f}%"></i></span></td>'
                    f"<td>{escape(r.detail)}{nd}</td></tr>")  # fmt: skip
    for p in s.penalties:
        rows.append(f'<tr class="pen"><td>{escape(p.label)}</td><td class=num>{p.points:g}</td><td></td>'
                    f"<td></td><td>{escape(p.detail)}</td></tr>")  # fmt: skip
    return (f'<table class="tbl score"><thead><tr><th>Critère</th><th class=num>Points</th><th class=num>Max</th>'
            f'<th></th><th>Donnée</th></tr></thead><tbody>{"".join(rows)}</tbody><tfoot><tr><td>Score</td>'
            f'<td class=num>{s.total:.0f}</td><td class=num>100</td><td colspan="2">plafond {s.ceiling:.0f} si les '
            f"données manquantes sont favorables · fiabilité {pct(s.confidence, 0)} du barème</td></tr></tfoot></table>")  # fmt: skip


def _valuation(plan: Financing | None, thesis: dict[str, Any]) -> str:
    if plan is None:
        return ('<p class="muted">Non calculable : EBE indisponible ou négatif. À obtenir au premier '
                "échange (liasses fiscales, EBE retraité).</p>")  # fmt: skip
    multiples, deltas, grid = sensitivity(plan, thesis)
    val = {**DEFAULT_VALUATION, **(thesis.get("valuation") or {})}
    head = "".join(f"<th class=num>{_x(m)}</th>" for m in multiples)
    body = ""
    for d, row in zip(deltas, grid, strict=True):
        cells = "".join(
            f'<td class="num{" base" if d == 0 and m == multiples[2] else ""}{" band" if val["ebe_multiple_low"] <= m <= val["ebe_multiple_high"] else ""}">{meur(v)}</td>'
            for m, v in zip(multiples, row, strict=True)
        )
        label = f"EBE {pct(d, 0, signed=True)}" if d else "EBE de référence"
        body += f"<tr><th>{label} · {meur(plan.ebe * (1 + d))} M€</th>{cells}</tr>"
    summary = (f'<div class="valbox"><div><span>Valeur d\'entreprise indicative</span><b>{eur(plan.ev_low)} '
               f"– {eur(plan.ev_high)}</b><small>EBE {eur(plan.ebe)} ({plan.ebe_year}) × "
               f'{_x(val["ebe_multiple_low"])} à {_x(val["ebe_multiple_high"])}</small></div><div><span>Milieu de '
               f"fourchette</span><b>{eur(plan.ev_mid)}</b><small>base du montage indicatif</small></div></div>")  # fmt: skip
    return (summary + f'<h4>Sensibilité de la valeur d\'entreprise (M€)</h4><table class="tbl sens"><thead><tr>'
            f"<th>EBE ↓ · multiple →</th>{head}</tr></thead><tbody>{body}</tbody></table>"
            '<p class="note">Zone ombrée : fourchette de multiples de la thèse ; case encadrée : cas de base.</p>')  # fmt: skip


def _financing(plan: Financing | None, thesis: dict[str, Any]) -> str:
    if plan is None:
        return '<p class="muted">Non calculable sans EBE.</p>'
    fin = {**DEFAULT_FINANCING, **(thesis.get("financing") or {})}
    ok = plan.coverage >= fin["min_coverage"]
    uses = [("Valeur d'entreprise (milieu de fourchette)", plan.ev_mid),
            (f"Frais de transaction ({pct(fin['transaction_fees'], 0)})", plan.fees)]  # fmt: skip
    sources = [(f"Dette senior ({_x(round(plan.senior_debt / plan.ebe, 2))} l'EBE)", plan.senior_debt),
               (f"Crédit vendeur ({pct(fin['vendor_loan_share'], 0)} du prix)", plan.vendor_loan),
               ("Fonds propres (searcher et investisseurs)", plan.equity)]  # fmt: skip

    def block(title: str, items: list[tuple[str, float]], total: float) -> str:
        lines = "".join(f"<tr><td>{escape(k)}</td><td class=num>{keur(v)}</td>"
                        f"<td class=num>{pct(v / total, 0)}</td></tr>" for k, v in items)  # fmt: skip
        return (f'<table class="tbl su"><thead><tr><th>{title}</th><th class=num>k€</th><th class=num>%</th>'
                f"</tr></thead><tbody>{lines}</tbody><tfoot><tr><td>Total</td><td class=num>{keur(total)}</td>"
                "<td class=num>100 %</td></tr></tfoot></table>")  # fmt: skip

    stats = [("Dette senior / EBE", _x(round(plan.senior_debt / plan.ebe, 2))),
             ("Fonds propres / emplois", pct(plan.equity_share, 0)),
             ("Service annuel de la dette", eur(plan.annual_debt_service)),
             ("Couverture du service de la dette",
              f'{mult(plan.coverage)} <span class="{"pos-txt" if ok else "neg-txt"}">'
              f'{"confortable" if ok else "tendue"} (seuil {mult(fin["min_coverage"])})</span>')]  # fmt: skip
    stat_html = "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in stats)
    return (f'<div class="grid2">{block("Emplois", uses, plan.uses)}{block("Ressources", sources, plan.uses)}</div>'
            f'<div class="credit">{stat_html}</div><p class="note">Hypothèses (config/thesis.yaml) : dette senior '
            f"{_x(fin['senior_debt_multiple'])} l'EBE plafonnée à {pct(fin['max_debt_share'], 0)} du prix, amortie sur "
            f"{fin['amortization_years']:g} ans à {pct(fin['interest_rate'])} ; {pct(fin['cash_conversion'], 0)} de "
            "l'EBE disponible pour la dette. La couverture dépend de ces hypothèses, pas de la cible : elle "
            "n'entre pas dans la recommandation (ADR-020). Ni dette nette, ni BFR, ni EBE normalisé.</p>")  # fmt: skip


def _signals(d: Dossier) -> str:
    level_cls = {"élevé": "high", "moyen": "mid", "info": "info"}
    rows = (
        "".join(
            f'<tr><td><span class="lvl lvl-{level_cls[s.level]}">{escape(s.level)}</span></td>'
            f"<td><b>{escape(s.title)}</b><br><small>{escape(s.detail)}</small></td><td>{escape(s.theme)}</td></tr>"
            for s in d.signals
        )
        or '<tr><td colspan="3" class="muted">Aucun signal factuel.</td></tr>'
    )
    ai = ""
    a = d.company.analysis
    if a and a.red_flags:
        ai = ("<h4>Hypothèses de l'IA, à vérifier</h4><ul>"
              + "".join(f"<li>{escape(x)}</li>" for x in a.red_flags) + "</ul>")  # fmt: skip
    return (f'<table class="tbl sig"><thead><tr><th>Niveau</th><th>Signal factuel</th><th>Chantier</th></tr>'
            f"</thead><tbody>{rows}</tbody></table>{ai}")  # fmt: skip


def _dd(d: Dossier) -> str:
    rows = "".join(
        f'<tr class="{"hi" if prio == "Haute" else ""}"><td class="c">{code}</td><td>{escape(theme)}</td>'
        f'<td>{escape(q)}</td><td><span class="prio prio-{"h" if prio == "Haute" else "n"}">{prio}</span></td></tr>'
        for code, theme, q, prio in dd_plan(d.signals)
    )
    return (f'<table class="tbl dd"><thead><tr><th>Réf.</th><th>Chantier</th><th>Question</th><th>Priorité</th>'
            f'</tr></thead><tbody>{rows}</tbody></table><p class="note">Priorité haute : question déclenchée '
            "par un signal factuel de la cible.</p>")  # fmt: skip


def _irl(d: Dossier) -> str:
    gaps = data_gaps(d.company)
    rows = "".join(
        f'<tr><td class="c">{i}</td><td>{escape(doc)}</td><td><span class="prio prio-{"h" if prio == "Haute" else "n"}">'
        f"{prio}</span></td><td>À demander</td></tr>"
        for i, (doc, prio) in enumerate(information_requests(d.signals), 1)
    )
    gap_html = (
        ("<p><b>Données manquantes au score :</b> " + escape(" ; ".join(gaps)) + ".</p>")
        if gaps
        else ""
    )
    return (gap_html + f'<table class="tbl irl"><thead><tr><th>#</th><th>Document</th><th>Priorité</th><th>Statut</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>")  # fmt: skip


def _draft(c: Company, footer: str | None) -> str:
    a = c.analysis
    if a is None:
        return '<p class="muted">Brouillon non généré : lancer <code>pme-radar draft</code>.</p>'
    body = escape(with_footer(a.email_body, footer)).replace("\n", "<br>")
    return (f'<div class="mail"><span class="stampx">À relire · jamais envoyé automatiquement</span>'
            f"<p><b>Objet : {escape(a.email_subject)}</b></p><p>{body}</p></div>")  # fmt: skip


def _dossier(i: int, d: Dossier, thesis: dict[str, Any], as_of: date, footer: str | None) -> str:
    c, s = d.company, d.company.score
    assert s is not None
    tiers = {n["code"]: n["tier"] for n in thesis.get("naf_codes", [])}
    pos = highlights(c, tiers.get(c.naf_code or ""))
    if c.analysis:
        pos.append(f"Analyse IA : {c.analysis.mini_thesis[0]}")
    neg = [s_ for s_ in d.signals if s_.level in ("élevé", "moyen")][:5]
    pos_html = (
        "".join(f"<li>{escape(x)}</li>" for x in pos)
        or "<li>Aucun point fort établi par les données.</li>"
    )
    neg_html = (
        "".join(f"<li><b>{escape(x.title)}</b> — {escape(x.detail)}</li>" for x in neg)
        or "<li>Aucun point de vigilance majeur dans les données.</li>"
    )
    legal = escape(labels.legal_form(c.legal_form))
    reasons = "".join(f"<li>{_code(r)}</li>" for r in d.rec.reasons)
    steps = "".join(f"<li>{_code(r)}</li>" for r in d.rec.next_steps)
    return f"""<section class="dossier" id="d-{c.siren}">
<div class="dhead"><div class="dtitle"><p class="kicker">Dossier 3.{i} · NAF {_e(c.naf_code)}</p><h2>{_e(c.name)}</h2>
<p class="sub">{_e(c.naf_label)}<br>{_e(c.city)} ({_e(c.department)}) · SIREN {_e(c.siren)} · {legal}</p></div>
<div class="rating rating-{d.rec.tone}"><span>Recommandation</span><b>{escape(d.rec.label)}</b>
<small>Score {s.total:.0f}/100 · plafond {s.ceiling:.0f} · fiabilité {pct(s.confidence, 0)}</small></div></div>
<div class="grid-profile"><aside class="facts"><h4>Profil</h4><table>{_profile_table(c, as_of)}</table></aside>
<div><h3 class="first">Thèse d'investissement</h3><ul class="pos">{pos_html}</ul>
<h3>Points de vigilance</h3><ul class="neg">{neg_html}</ul>
<h3>Motifs de la recommandation</h3><ul class="plain">{reasons}</ul></div></div>
<h3><span class="sn">1</span>Données financières</h3>{_financials(c)}
<h3><span class="sn">2</span>Analyse du score</h3>{_scorecard(c)}
<h3><span class="sn">3</span>Valorisation indicative</h3>{_valuation(d.plan, thesis)}
<h3><span class="sn">4</span>Structure de financement indicative</h3>{_financing(d.plan, thesis)}
<h3><span class="sn">5</span>Signaux factuels et hypothèses</h3>{_signals(d)}
<h3><span class="sn">6</span>Plan de due diligence</h3>{_dd(d)}
<h3><span class="sn">7</span>Demandes d'informations</h3>{_irl(d)}
<h3><span class="sn">8</span>Prochaines étapes</h3><ol class="steps">{steps}</ol>
<h3>Annexe · brouillon d'approche</h3>{_draft(c, footer)}
</section>"""


def _method(scoring_cfg: dict[str, Any], thesis: dict[str, Any]) -> str:
    names = {"director_age": "Âge du dirigeant", "owner_operator": "Dirigeant-exploitant",
             "no_obvious_successor": "Pas de successeur évident", "revenue": "Chiffre d'affaires",
             "headcount": "Effectif", "profitability": "Rentabilité (EBE, sinon marge nette)",
             "revenue_cagr": "Régularité du CA", "company_age": "Ancienneté",
             "thesis_fit": "Adéquation à la thèse"}  # fmt: skip
    crit = "".join(f"<tr><td>{escape(names.get(k, k))}</td><td class=num>{v.get('max_points', 0)}</td></tr>"
                   for k, v in (scoring_cfg.get("criteria") or {}).items())  # fmt: skip
    pen_names = {"corporate_director": "Dirigeant personne morale (groupe)",
                 "missing_financials": "Comptes non disponibles", "high_debt": "Endettement élevé"}  # fmt: skip
    pens = "".join(f"<tr><td>{escape(pen_names.get(k, k))}</td><td class=num>{v}</td></tr>"
                   for k, v in (scoring_cfg.get("penalties") or {}).items())  # fmt: skip
    val = {**DEFAULT_VALUATION, **(thesis.get("valuation") or {})}
    fin = {**DEFAULT_FINANCING, **(thesis.get("financing") or {})}
    hyp = [("Multiples d'EBE", f"{_x(val['ebe_multiple_low'])} à {_x(val['ebe_multiple_high'])}"),
           ("Dette senior", f"{_x(fin['senior_debt_multiple'])} l'EBE, ≤ {pct(fin['max_debt_share'], 0)} du prix"),
           ("Crédit vendeur", f"{pct(fin['vendor_loan_share'], 0)} du prix"),
           ("Frais de transaction", f"{pct(fin['transaction_fees'], 0)} du prix"),
           ("Taux et durée de la dette", f"{pct(fin['interest_rate'])} sur {fin['amortization_years']:g} ans"),
           ("EBE disponible pour la dette", pct(fin["cash_conversion"], 0)),
           ("Couverture jugée confortable", mult(fin["min_coverage"])),
           ("Ticket de fonds propres maximal", eur(fin["max_equity_ticket"]))]  # fmt: skip
    hyp_html = "".join(f"<tr><td>{k}</td><td class=num>{v}</td></tr>" for k, v in hyp)
    glossary = [("Score (plancher)", "Points obtenus sur les seules données disponibles ; base de la qualification."),
                ("Plafond", "Score atteignable si chaque donnée manquante s'avérait favorable."),
                ("Fiabilité", "Part du barème évaluée sur des données réelles."),
                ("Signal factuel", "Constat établi par une règle sur les données, avec sa question de DD."),
                ("EBE", "Excédent brut d'exploitation : rentabilité opérationnelle, avant amortissements."),
                ("Couverture", "Flux disponible pour la dette divisé par son service annuel.")]  # fmt: skip
    gl = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in glossary)
    return f"""<section class="sheet" id="methode">
<header class="sec"><span class="num">4</span><h2>Méthodologie, hypothèses et avertissement</h2></header>
<div class="grid2"><div><h3 class="first">Barème du score (100 points)</h3><table class="tbl compact"><tbody>{crit}</tbody></table>
<h4>Pénalités</h4><table class="tbl compact"><tbody>{pens}</tbody></table>
<p class="note">Seuil de qualification : {scoring_cfg.get("qualified_threshold", 70)}/100. Procédure collective :
exclusion. Donnée manquante : 0 point, signalée « à obtenir ».</p>
<h4>Sources</h4><ul class="src"><li>API Recherche d'entreprises (data.gouv.fr) : identité, dirigeants, chiffre
d'affaires.</li><li>BODACC : procédures collectives.</li><li>Ratios BCE/INPI (data.economie.gouv.fr) : EBE,
endettement, historique.</li></ul></div>
<div><h3 class="first">Hypothèses de valorisation et de financement</h3><table class="tbl compact"><tbody>{hyp_html}</tbody></table>
<h4>Glossaire</h4><dl class="gloss">{gl}</dl></div></div>
<h3>Avertissement</h3><p class="disclaimer">Ce document a été préparé automatiquement à partir de données
publiques, possiblement incomplètes ou anciennes, à des fins de travail interne d'origination. Les
valorisations et montages présentés sont des ordres de grandeur destinés à décider d'un premier
contact : ils ne constituent ni une évaluation, ni une offre, ni un conseil en investissement. Les
hypothèses de l'intelligence artificielle sont signalées comme telles et doivent être vérifiées. Aucun
contact n'est pris sans relecture humaine. Les informations relatives aux dirigeants sont des données
personnelles : leur usage est limité à la prospection B2B, dans le respect du droit d'opposition.</p></section>"""


CSS = """
:root{--navy:#0b1f3a;--navy2:#13294b;--ink:#1c2333;--muted:#5f6b85;--line:#d9dee8;--soft:#f4f6fa;
--accent:#1588b8;--accent-l:#e7f4fa;--go:#137a55;--go-l:#e3f4ec;--dig:#a8620a;--dig-l:#fdf1df;--doc:#4250c6;
--doc-l:#eceefc;--low:#6a7088;--low-l:#eff1f5;--out:#b8324a;--out-l:#fbe9ec}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#e9ecf2;color:var(--ink);font:13.5px/1.5 Inter,"Helvetica Neue",Helvetica,Arial,sans-serif}
a{color:inherit;text-decoration:none}main{max-width:1020px;margin:0 auto}
.cover{background:linear-gradient(150deg,#0b1f3a 0%,#13294b 60%,#173a63 100%);color:#fff;padding:46px 60px;
min-height:1120px;display:flex;flex-direction:column;justify-content:space-between}
.cover-top{display:flex;justify-content:space-between;align-items:center}
.brand{display:flex;align-items:center;gap:12px;font-size:21px;font-weight:700}.brand i{font-style:normal;color:#25c2f5}
.conf-pill{border:1.5px solid #e2b04a;color:#e2b04a;border-radius:4px;padding:5px 12px;font-size:11.5px;font-weight:700;
letter-spacing:.12em;text-transform:uppercase}
.kicker{font-size:11.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
.cover .kicker{color:#7fd3f2}.cover h1{font-size:44px;line-height:1.1;margin:0 0 14px;letter-spacing:-.02em;font-weight:700}
.thesis{font-size:19px;color:#c9d6ec;margin:0 0 34px}.cover-meta{border-collapse:collapse;font-size:14px}
.cover-meta th{color:#8fa3c4;font-weight:500;text-align:left;padding:7px 28px 7px 0}.cover-meta td{padding:7px 0;color:#fff}
.cover-meta tr{border-top:1px solid rgba(255,255,255,.14)}.cover-bottom{font-size:12px;color:#9fb0cc;max-width:640px;line-height:1.6}
.cover code{color:#cfe3ff;background:rgba(255,255,255,.1)}
.sheet,.dossier{background:#fff;padding:40px 54px;margin:16px 0;box-shadow:0 2px 14px rgba(11,31,58,.08)}
.sec{display:flex;align-items:center;gap:14px;border-bottom:2px solid var(--navy);padding-bottom:10px;margin-bottom:18px}
.sec .num{background:var(--navy);color:#fff;width:32px;height:32px;border-radius:4px;display:grid;place-content:center;font-weight:700}
.sec h2{margin:0;font-size:24px;color:var(--navy);letter-spacing:-.01em}
h3{font-size:15.5px;color:var(--navy);margin:24px 0 9px;padding-bottom:5px;border-bottom:1px solid var(--line)}
h3.first{margin-top:0}h3 .sn{display:inline-grid;place-content:center;width:22px;height:22px;border-radius:3px;
background:var(--accent);color:#fff;font-size:12px;margin-right:9px;vertical-align:1px}
h4{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:8px}
.kpi{border:1px solid var(--line);border-top:3px solid var(--navy);padding:11px 13px;border-radius:3px}
.kpi b{display:block;font-size:26px;color:var(--navy);line-height:1.15}.kpi span{display:block;font-weight:600;font-size:12.5px}
.kpi small{color:var(--muted);font-size:11.5px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:26px}.key li{margin:7px 0}.key{padding-left:18px}
.toc{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.toc a{display:block;border-left:3px solid var(--accent);background:var(--soft);padding:9px 12px;break-inside:avoid}
.toc b{display:block;font-size:18px;color:var(--accent);line-height:1.1}.toc span{display:block;font-weight:700;font-size:12.5px;color:var(--navy)}.toc small{display:block;color:var(--muted);font-size:11px}
.chart{width:100%;height:auto;display:block}.small-chart{max-width:300px;margin-left:auto}
.sv-l{font-size:12px;fill:#1c2333}.sv-v,.sv-n{font-size:11px;fill:#1c2333;font-weight:600}.sv-t{font-size:10.5px;fill:#5f6b85}
.sv-b0{fill:#0b1f3a}.sv-b1{fill:#1588b8}.sv-b2{fill:#137a55}.sv-b3{fill:#6f9ec0}.sv-b4{fill:#a8620a}
.sv-grid{stroke:#e4e8ef;stroke-width:1}.sv-axis{stroke:#9aa4b8}.sv-range{fill:#1588b8;opacity:.88}
.sv-mid{stroke:#0b1f3a;stroke-width:2.5}
.stack{display:flex;height:12px;border-radius:2px;overflow:hidden;gap:2px;margin:6px 0}
.stack i{display:block}.bar-go{background:var(--go)}.bar-dig{background:var(--dig)}.bar-doc{background:var(--doc)}
.bar-low{background:#c3c8d6}.bar-out{background:var(--out)}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
.lg:before{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
.lg-go:before{background:var(--go)}.lg-dig:before{background:var(--dig)}.lg-doc:before{background:var(--doc)}
.lg-low:before{background:#c3c8d6}.lg-out:before{background:var(--out)}
.tbl{width:100%;border-collapse:collapse;margin:4px 0 6px;font-size:12.5px}
.tbl thead th{background:var(--navy);color:#fff;font-weight:600;font-size:11px;letter-spacing:.04em;text-transform:uppercase;
padding:7px 8px;text-align:left}.tbl td,.tbl tbody th{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
.tbl tbody th{font-weight:600;color:var(--ink)}.tbl tbody tr:nth-child(even) td{background:#fafbfd}
.tbl tfoot td{border-top:2px solid var(--navy);font-weight:700;padding:7px 8px}.num{text-align:right!important;white-space:nowrap}
.tbl thead th.num{white-space:normal}.pipe td{font-size:12px}.c{text-align:center!important;color:var(--muted)}.tbl small{color:var(--muted)}.nd{color:#9aa4b8;font-style:italic}
.fin tr.strong td,.fin tr.strong th{font-weight:700}.fin tr.sub td,.fin tr.sub th{color:var(--muted);font-weight:400;font-size:11.5px}
.grid-fin{display:grid;grid-template-columns:1fr 300px;gap:22px;align-items:start}
.note{font-size:11px;color:var(--muted);margin:4px 0 0}.muted{color:var(--muted)}
.reco{display:inline-block;padding:3px 9px;border-radius:3px;font-size:11.5px;font-weight:700;white-space:nowrap}
.reco-go{background:var(--go-l);color:var(--go)}.reco-dig{background:var(--dig-l);color:var(--dig)}
.reco-doc{background:var(--doc-l);color:var(--doc)}.reco-low{background:var(--low-l);color:var(--low)}
.reco-out{background:var(--out-l);color:var(--out)}
.dhead{display:flex;gap:20px;align-items:stretch;border-bottom:2px solid var(--navy);padding-bottom:14px;margin-bottom:16px}
.dtitle{flex:1}.dtitle h2{margin:0;font-size:27px;color:var(--navy);letter-spacing:-.01em}.sub{margin:4px 0 0;color:var(--muted)}
.rating{min-width:250px;border-radius:4px;padding:11px 16px;display:flex;flex-direction:column;justify-content:center}
.rating span{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;opacity:.85}.rating b{font-size:21px;line-height:1.25}
.rating small{font-size:11.5px;opacity:.9}.rating-go{background:var(--go);color:#fff}.rating-dig{background:var(--dig);color:#fff}
.rating-doc{background:var(--doc);color:#fff}.rating-low{background:#7a8098;color:#fff}.rating-out{background:var(--out);color:#fff}
.grid-profile{display:grid;grid-template-columns:300px 1fr;gap:24px}
.facts{background:var(--soft);border:1px solid var(--line);border-radius:3px;padding:12px 14px}.facts h4{margin-top:0}
.facts table{width:100%;border-collapse:collapse;font-size:12px}.facts th{color:var(--muted);font-weight:500;text-align:left;
padding:4px 6px 4px 0;vertical-align:top;width:44%}.facts td{padding:4px 0;font-weight:600}.facts tr{border-bottom:1px solid #e6e9f0}
ul.pos,ul.neg,ul.plain{padding-left:0;list-style:none;margin:6px 0}ul.pos li,ul.neg li,ul.plain li{padding:3px 0 3px 20px;position:relative}
ul.pos li:before{content:"+";position:absolute;left:3px;color:var(--go);font-weight:800}
ul.neg li:before{content:"!";position:absolute;left:6px;color:var(--dig);font-weight:800}
ul.plain li:before{content:"›";position:absolute;left:5px;color:var(--accent);font-weight:800}
.meter{display:block;height:7px;background:#e6e9f0;border-radius:4px;overflow:hidden;width:100px}
.meter i{display:block;height:100%;background:var(--accent)}.score tr.missing td{color:var(--muted)}
.score tr.pen td{color:var(--out)}.tag-doc{font-size:10px;color:var(--doc);background:var(--doc-l);padding:1px 6px;border-radius:3px;font-weight:700}
.valbox{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:6px}.valbox>div{border:1px solid var(--line);
border-left:4px solid var(--accent);padding:10px 14px}.valbox span{display:block;font-size:11px;letter-spacing:.06em;
text-transform:uppercase;color:var(--muted)}.valbox b{display:block;font-size:20px;color:var(--navy)}.valbox small{color:var(--muted)}
.sens thead th{text-transform:none;letter-spacing:0;font-size:11.5px}.sens td.band{background:var(--accent-l)!important}.sens td.base{outline:2px solid var(--navy);outline-offset:-2px;font-weight:700}
.su td:first-child{width:62%}.credit{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0 4px}
.credit div{background:var(--soft);padding:9px 12px;border-radius:3px}.credit>div>span{display:block;font-size:10.5px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}.credit b span{font-size:11px;margin-left:4px}.credit b{font-size:14.5px}.pos-txt{color:var(--go);font-weight:600}.neg-txt{color:var(--out);font-weight:600}
.lvl{display:inline-block;padding:2px 7px;border-radius:3px;font-size:11px;font-weight:700}.lvl-high{background:var(--out-l);color:var(--out)}
.lvl-mid{background:var(--dig-l);color:var(--dig)}.lvl-info{background:var(--soft);color:var(--muted)}
.prio{font-size:11px;font-weight:700;padding:1px 7px;border-radius:3px}.prio-h{background:var(--dig-l);color:var(--dig)}
.prio-n{background:var(--soft);color:var(--muted)}.dd tr.hi td{background:#fffaf1!important}
.steps li{margin:4px 0}.mail{border:1px solid var(--line);padding:12px 16px;font-size:12.5px;background:#fbfcfe}
.stampx{display:inline-block;color:var(--out);border:1.5px solid var(--out);border-radius:3px;padding:2px 8px;font-size:10.5px;
font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.compact td{padding:4px 8px}.gloss dt{font-weight:700;font-size:12.5px;margin-top:5px}.gloss dd{margin:0 0 3px;color:var(--muted);font-size:12px}
.disclaimer{font-size:11.5px;color:var(--muted);text-align:justify}ul.src{padding-left:16px;margin:4px 0;font-size:12px}
code{font:11.5px ui-monospace,Menlo,Consolas,monospace;background:var(--soft);padding:1px 4px;border-radius:3px}.actions td:first-child{width:118px}.actions td:last-child{width:38%;color:var(--muted)}
@page{size:A4;margin:12mm 12mm 16mm;@bottom-left{content:"pme-radar · Strictement confidentiel";font:9px Inter,Arial,sans-serif;color:#7a849a}
@bottom-right{content:counter(page) " / " counter(pages);font:9px Inter,Arial,sans-serif;color:#7a849a}}
@page:first{margin:0;@bottom-left{content:none}@bottom-right{content:none}}
@media print{body{background:#fff;font-size:11.5px}main{max-width:none}.sheet,.dossier{box-shadow:none;margin:0;padding:0}
.cover{min-height:297mm;break-after:page;padding:20mm 18mm}.sheet,.dossier{break-before:page}
.fin,.su,.sens,.score,.irl,.sig,.compact,.facts,.valbox,.credit,.mail,.kpi,.rating,.actions,svg{break-inside:avoid}thead{display:table-header-group}tr{break-inside:avoid}h3,h4{break-after:avoid}
.grid-profile{grid-template-columns:62mm 1fr}}
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
    body = (_cover(thesis, dossiers, chosen, source, as_of)
            + _summary(dossiers, chosen, scoring_cfg, campaign)
            + _pipeline(dossiers, chosen, thesis)
            + "".join(_dossier(i, d, thesis, as_of, footer) for i, d in enumerate(chosen, 1))
            + _method(scoring_cfg, thesis))  # fmt: skip
    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapport de pré-due diligence · pme-radar</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"""
    return html, chosen
