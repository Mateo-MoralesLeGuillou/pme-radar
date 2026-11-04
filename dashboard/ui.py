"""Données et composants partagés du dashboard (chargement en cache, formats, éléments d'interface).

Les pages de `dashboard/views/` font `import ui` : le point d'entrée `app.py` ajoute ce dossier au
chemin d'import. Sources : le dernier run local (`data/processed/analyzed.jsonl`, sinon
`scored.jsonl`) ou l'échantillon synthétique (`examples/sample_companies.jsonl`).
"""

from __future__ import annotations

import base64
import html
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pme_radar import labels
from pme_radar.config import DataPaths, load_scoring, load_thesis, load_yaml
from pme_radar.fmt import eur, pct
from pme_radar.funnel import REPLIED_STATUSES, SENT_STATUSES
from pme_radar.models import Company
from pme_radar.outreach import load_campaign
from pme_radar.pdf import find_browser, html_to_pdf_bytes
from pme_radar.report import Dossier, evaluate
from pme_radar.store import read_companies

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_COMPANIES = ROOT / "examples" / "sample_companies.jsonl"
SAMPLE_CAMPAIGN = ROOT / "examples" / "sample_campaign.csv"
CONFIG = {name: ROOT / "config" / f"{name}.yaml" for name in ("scoring", "thesis", "campaign")}
LOGO64 = base64.b64encode((ROOT / "docs/img/logo.svg").read_bytes()).decode()

# pages (chemins relatifs au point d'entrée)
P_HOME = "views/accueil.py"
P_COMPANY = "views/entreprise.py"
P_TARGETS = "views/cibles.py"
P_CAMPAIGN = "views/campagne.py"
P_REPORTS = "views/rapports.py"
P_HELP = "views/aide.py"

CYAN, GREEN, AMBER, VIOLET, RED, GRAY = (
    "#25c2f5",
    "#2ee6a6",
    "#ffb547",
    "#8c9bff",
    "#ff6b81",
    "#7b86a6",
)
TEXT, MUTED, GRID, CARD = "#e6ebf5", "#93a0bf", "#26304a", "#151d33"
FONT = "'Source Sans Pro', 'Source Sans 3', sans-serif"
MODE_LIVE, MODE_DEMO = "Mes données", "Démo"

# recommandation (ton) : libellé, couleur de badge Streamlit, couleur hex, explication en clair
RECO: dict[str, tuple[str, str, str, str]] = {
    "go": ("À approcher", "green", GREEN,
           "Qualifiée et sans signal bloquant : relire le brouillon et prendre contact."),
    "dig": ("À creuser", "orange", AMBER,
            "Qualifiée, mais un point est à lever d'abord (signal fort ou ticket trop élevé)."),
    "doc": ("À documenter", "violet", VIOLET,
            "Sous le seuil faute de données : elle peut se qualifier une fois documentée."),
    "low": ("Non prioritaire", "gray", GRAY, "Sous le seuil de qualification."),
    "out": ("Écartée", "red", RED, "Procédure collective publiée au BODACC : exclue d'office."),
}  # fmt: skip
RECO_LABELS = [v[0] for v in RECO.values()]
RECO_HEX = [v[2] for v in RECO.values()]
# statut de prise de contact : libellé, couleur de badge
STATUS: dict[str, tuple[str, str]] = {
    "": ("Non contactée", "gray"),
    "draft": ("Brouillon prêt", "blue"),
    "contacted": ("Contactée", "violet"),
    "replied": ("A répondu", "orange"),
    "meeting": ("RDV obtenu", "green"),
    "declined": ("A décliné", "gray"),
    "bounced": ("Rebond", "red"),
}
FOLLOW_UP_DAYS = 7  # relance suggérée après une semaine sans réponse


# ---------------------------------------------------------------- formats
def num(v: Any) -> float | None:
    """Nombre ou None (None, NaN et valeurs vides de pandas → None)."""
    if v is None or v == "":
        return None
    f = float(v)
    return None if math.isnan(f) else f


def money(v: Any) -> str:
    """« 8,50 M€ », « 870 k€ », « n.d. »."""
    return eur(num(v))


def m_eur(v: Any, digits: int = 1) -> str:
    f = num(v)
    return "n.d." if f is None else f"{f / 1e6:.{digits}f} M€".replace(".", ",")


def percent(v: Any, digits: int = 1, signed: bool = False) -> str:
    return pct(num(v), digits, signed)


def years(v: Any) -> str:
    f = num(v)
    return "n.d." if f is None else f"{f:.0f} ans"


def fr_date(v: str | date | None) -> str:
    if not v or (isinstance(v, float) and pd.isna(v)):
        return "—"
    d = date.fromisoformat(v) if isinstance(v, str) else v
    return f"{d:%d/%m/%Y}"


def esc(v: object) -> str:
    return "" if _na(v) else html.escape(str(v))


def _na(v: object) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


# ---------------------------------------------------------------- données
@dataclass
class Data:
    live: bool
    source: str  # libellé de la source affiché dans l'en-tête
    companies: list[Company]
    by_siren: dict[str, Company]
    dossiers: dict[str, Dossier]
    table: pd.DataFrame  # une ligne par société notée, triée par score décroissant
    campaign: pd.DataFrame
    campaign_path: Path | None  # mode « Mes données » : suivi modifiable depuis le dashboard
    scoring: dict[str, Any]
    thesis: dict[str, Any]
    campaign_cfg: dict[str, Any]
    report_path: Path | None  # dernier rapport complet généré par `pme-radar run`

    @property
    def threshold(self) -> int:
        return int(self.scoring.get("qualified_threshold", 70))

    def label(self, siren: str) -> str:
        """Libellé de recherche : nom, ville, SIREN et dirigeant (tout est cherchable)."""
        r = self.table.loc[self.table["siren"] == siren]
        if r.empty:
            return siren
        row = r.iloc[0]
        director = f" · {row['director']}" if row["director"] else ""
        return f"{row['name']} — {row['city']} ({row['department']}) · {siren}{director}"


def live_paths() -> tuple[Path, Path, Path] | None:
    """(sociétés, suivi de campagne, rapport) du dernier run local, s'il existe."""
    paths = DataPaths(os.environ.get("PME_RADAR_DATA_DIR") or ROOT / "data")
    src = next((p for p in (paths.analyzed, paths.scored) if p.exists()), None)
    if src is None:
        return None
    return src, paths.out / "campaign.csv", paths.out / "rapport_deal_flow.html"


def default_mode() -> str:
    forced = os.environ.get("PME_RADAR_DATA", "").lower() in ("sample", "demo", "démo")
    return MODE_DEMO if forced or live_paths() is None else MODE_LIVE


def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def load() -> Data:
    """Données de la source choisie dans l'en-tête (cache : relues si un fichier change)."""
    live = live_paths()
    use_live = live is not None and st.session_state.get("data_mode", default_mode()) == MODE_LIVE
    comp, camp, rep = live if use_live and live else (SAMPLE_COMPANIES, SAMPLE_CAMPAIGN, None)
    stamps = tuple(_mtime(p) for p in (comp, camp, *CONFIG.values()))
    return _load(str(comp), str(camp), str(rep) if rep else "", use_live, stamps)


@st.cache_resource(show_spinner="Chargement des données…", max_entries=4)
def _load(comp: str, camp: str, rep: str, live: bool, _stamps: tuple[float, ...]) -> Data:
    scoring, thesis = load_scoring(CONFIG["scoring"]), load_thesis(CONFIG["thesis"])
    campaign_cfg = load_yaml(CONFIG["campaign"])
    companies = [c for c in read_companies(Path(comp)) if c.score is not None]
    dossiers = {d.company.siren: d for d in evaluate(companies, scoring, thesis)}
    campaign = load_campaign(Path(camp)).drop_duplicates("siren", keep="last")
    if live:
        when = datetime.fromtimestamp(Path(comp).stat().st_mtime)
        source = f"Dernier run · {when:%d/%m/%Y %H:%M}"
    else:
        source = "Échantillon synthétique"
    report = Path(rep) if rep and Path(rep).exists() else None
    return Data(
        live=live,
        source=source,
        companies=companies,
        by_siren={c.siren: c for c in companies},
        dossiers=dossiers,
        table=_table(companies, dossiers, campaign),
        campaign=campaign,
        campaign_path=Path(camp) if live else None,
        scoring=scoring,
        thesis=thesis,
        campaign_cfg=campaign_cfg,
        report_path=report,
    )


def _table(
    companies: list[Company], dossiers: dict[str, Dossier], campaign: pd.DataFrame
) -> pd.DataFrame:
    status = dict(zip(campaign["siren"], campaign["status"], strict=True))
    rows = []
    for c in companies:
        d, s = dossiers.get(c.siren), c.score
        if d is None or s is None:
            continue
        p, person = d.plan, c.main_person()
        rows.append(
            {
                "siren": c.siren,
                "name": c.name,
                "city": c.city or "",
                "department": c.department or "",
                "naf_code": c.naf_code or "",
                "naf_label": c.naf_label or "",
                "director": person.name if person and person.name else "",
                "director_age": c.director_age,
                "headcount": labels.headcount(c.headcount_band),
                "company_age": c.company_age_years,
                "revenue": c.revenue_last,
                "revenue_cagr": c.revenue_cagr,
                "net_margin": c.net_margin,
                "ebe": c.ebe,
                "ebe_margin": c.ebe_margin,
                "debt_ratio": c.debt_ratio,
                "accounts": c.accounts_available,
                "stage": c.stage.value,
                "score": s.total,
                "ceiling": s.ceiling,
                "confidence": s.confidence,
                "tone": d.rec.tone,
                "reco": d.rec.label,
                "ev_low": p.ev_low if p else None,
                "ev_mid": p.ev_mid if p else None,
                "ev_high": p.ev_high if p else None,
                "equity": p.equity if p else None,
                "alerts": sum(x.level in ("élevé", "moyen") for x in d.signals),
                "has_draft": c.analysis is not None,
                "status": status.get(c.siren, ""),
            }
        )
    if not rows:
        return pd.DataFrame(columns=[*TABLE_COLUMNS, "status_label", "dept_label", "_order"])
    df = pd.DataFrame(rows)
    numeric = ["director_age", "company_age", "revenue", "revenue_cagr", "net_margin", "ebe", "ebe_margin",
               "debt_ratio", "ev_low", "ev_mid", "ev_high", "equity"]  # fmt: skip
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    df["status_label"] = df["status"].map(lambda v: STATUS.get(v, (v, "gray"))[0])
    df["dept_label"] = df["department"].map(lambda v: labels.DEPARTMENTS.get(v, v))
    order = {k: i for i, k in enumerate(RECO)}
    df["_order"] = df["tone"].map(order)
    return df.sort_values(["score", "_order"], ascending=[False, True]).reset_index(drop=True)


TABLE_COLUMNS = [
    "siren", "name", "city", "department", "naf_code", "naf_label", "director", "director_age", "headcount",
    "company_age", "revenue", "revenue_cagr", "net_margin", "ebe", "ebe_margin", "debt_ratio", "accounts",
    "stage", "score", "ceiling", "confidence", "tone", "reco", "ev_low", "ev_mid", "ev_high", "equity",
    "alerts", "has_draft", "status",
]  # fmt: skip


def require_data(data: Data) -> None:
    """Arrête la page avec un message clair si aucune entreprise n'est notée."""
    if data.table.empty:
        empty_state("Aucune entreprise notée pour l'instant : lancez <code>pme-radar run</code> "
                    "(ou <code>pme-radar run --offline</code> pour la démo).")  # fmt: skip
        st.stop()


def campaign_view(data: Data) -> pd.DataFrame:
    """Suivi de campagne enrichi (nom, score, recommandation, délai depuis l'envoi)."""
    camp = data.campaign.copy()
    if camp.empty:
        return camp.assign(name=[], score=[], reco=[], days=[])
    info = data.table.set_index("siren")
    camp["name"] = camp["siren"].map(info["name"]).fillna(camp["siren"])
    camp["score"] = camp["siren"].map(info["score"])
    camp["reco"] = camp["siren"].map(info["reco"])
    sent = pd.to_datetime(camp["sent_date"].replace("", None), errors="coerce")
    camp["days"] = (pd.Timestamp(date.today()) - sent).dt.days
    return camp


def follow_ups(data: Data) -> pd.DataFrame:
    """Réponses à traiter et relances dues (contactées depuis 7 jours ou plus, sans réponse)."""
    camp = campaign_view(data)
    if camp.empty:
        return camp
    due = (camp["status"] == "contacted") & (camp["days"] >= FOLLOW_UP_DAYS)
    todo = camp[(camp["status"] == "replied") | due].copy()
    todo["action"] = todo["status"].map(
        {"replied": "Répondre et proposer un échange", "contacted": "Relancer (sans réponse)"}
    )
    return todo.sort_values(["status", "days"], ascending=[False, False])


def campaign_counts(data: Data) -> dict[str, int]:
    s = data.campaign["status"] if len(data.campaign) else pd.Series(dtype=str)
    return {
        "drafts": int((s == "draft").sum()),
        "sent": int(s.isin(SENT_STATUSES).sum()),
        "replied": int(s.isin(REPLIED_STATUSES).sum()),
        "meetings": int((s == "meeting").sum()),
        "bounced": int((s == "bounced").sum()),
    }


# ---------------------------------------------------------------- navigation
def open_company(siren: str) -> None:
    """À appeler depuis un rappel (bouton, recherche) : la fiche s'ouvre au prochain passage."""
    st.session_state["goto"] = siren


def handle_goto() -> None:
    target = st.session_state.pop("goto", None)
    if target:
        st.switch_page(P_COMPANY, query_params={"siren": target})


def _on_global_search() -> None:
    siren = st.session_state.get("global_search")
    if siren:
        open_company(siren)
        st.session_state["global_search"] = None  # la recherche se vide après ouverture


def company_link(siren: str, name: str, key: str | None = None) -> None:
    st.page_link(
        P_COMPANY, label=name, icon=":material/arrow_forward:", query_params={"siren": siren}
    )


def open_button_column(df: pd.DataFrame, key: str) -> Any:
    """Colonne « Ouvrir » d'un tableau : ouvre la fiche de la ligne cliquée."""

    def _click() -> None:
        click = st.session_state.get(key)
        if click is not None:
            open_company(str(df.iloc[int(click["row"])]["siren"]))

    return st.column_config.ButtonColumn(
        "Fiche", type="secondary", on_click=_click, key=key, width=88, pinned=True,
        help="Ouvre la fiche complète de l'entreprise.",
    )  # fmt: skip


# ---------------------------------------------------------------- composants
def header(data_mode_available: bool) -> Data:
    """En-tête commun : marque, recherche globale, source des données."""
    brand, search, source = st.columns([2.1, 5.2, 2.2], vertical_alignment="center")
    with source:
        if data_mode_available:
            st.segmented_control(
                "Données", [MODE_LIVE, MODE_DEMO], key="data_mode", required=True,
                default=default_mode(), label_visibility="collapsed", width="stretch",
                help="**Mes données** : dernier run local (`data/`). **Démo** : échantillon synthétique.",
            )  # fmt: skip
    data = load()
    with brand:
        st.html(
            f"""<div class="pr-brand"><img src="data:image/svg+xml;base64,{LOGO64}" alt="">
            <div><b>pme<span>-</span>radar</b><small>Origination search fund</small></div></div>"""
        )
    with search:
        st.selectbox(
            "Recherche", list(data.table["siren"]) if len(data.table) else [], index=None,
            format_func=data.label, key="global_search", on_change=_on_global_search,
            placeholder="Rechercher une entreprise : nom, ville, SIREN ou dirigeant…",
            label_visibility="collapsed",
            help="Tapez quelques lettres puis choisissez : la fiche complète de l'entreprise s'ouvre.",
        )  # fmt: skip
    with source:
        kind = "live" if data.live else "demo"
        st.html(f'<div class="pr-source {kind}">{esc(data.source)}</div>')
    return data


def page_title(title: str, subtitle: str = "") -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.html(f'<div class="pr-title"><h1>{title}</h1>{sub}</div>')


def reco_badge(tone: str, big: bool = False) -> str:
    label, _, color, _ = RECO.get(tone, RECO["low"])
    cls = "pr-reco big" if big else "pr-reco"
    return f'<span class="{cls}" style="--c:{color}">{esc(label)}</span>'


def status_badge(status: str) -> str:
    label, color = STATUS.get(status, (status, "gray"))
    hexes = {
        "gray": GRAY,
        "blue": CYAN,
        "violet": VIOLET,
        "orange": AMBER,
        "green": GREEN,
        "red": RED,
    }
    return f'<span class="pr-reco" style="--c:{hexes[color]}">{esc(label)}</span>'


def empty_state(text: str, icon: str = "🔎") -> None:
    st.html(f'<div class="pr-empty"><span>{icon}</span><p>{text}</p></div>')


def report_downloads(make_html: Callable[[], str], stem: str, what: str, disabled: bool = False,
                     help_: str | None = None) -> None:  # fmt: skip
    """Rapport en PDF A4 (si un navigateur sait imprimer sur cette machine) et en HTML."""
    browser = find_browser()
    with st.container(horizontal=True, gap="small"):
        if browser:
            st.download_button(f"{what} (PDF)", lambda: html_to_pdf_bytes(make_html(), browser),
                               file_name=f"{stem}.pdf", mime="application/pdf", type="primary",
                               icon=":material/picture_as_pdf:", on_click="ignore", disabled=disabled,
                               help=help_)  # fmt: skip
        st.download_button(f"{what} (HTML)", make_html, file_name=f"{stem}.html", mime="text/html",
                           type="secondary" if browser else "primary", icon=":material/code:",
                           on_click="ignore", disabled=disabled,
                           help="S'ouvre dans le navigateur ; « Imprimer > Enregistrer en PDF » au besoin.")  # fmt: skip
    if not browser:
        st.caption(
            "PDF direct indisponible (Chrome, Chromium ou Edge introuvable) : HTML imprimable en PDF."
        )


def styled(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=TEXT, size=13),
        margin=dict(l=0, r=8, t=12, b=0),
        height=height,
        hoverlabel=dict(font_family=FONT),
        showlegend=False,
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID)
    return fig


def chart(fig: go.Figure, height: int, key: str | None = None, legend: bool = False) -> None:
    fig = styled(fig, height)
    fig.update_layout(showlegend=legend)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def hbar(
    labels_: list[str],
    values: list[float],
    colors: str | list[str] = CYAN,
    text: list[str] | None = None,
) -> go.Figure:
    bar = go.Bar(
        x=values, y=labels_, orientation="h", marker_color=colors,
        text=text if text is not None else values, textposition="outside", cliponaxis=False,
        hovertemplate="%{y} : %{x}<extra></extra>",
    )  # fmt: skip
    fig = go.Figure(bar)
    fig.update_xaxes(visible=False, range=[0, (max(values) if values else 1) * 1.25])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def targets_columns(threshold: int) -> dict[str, Any]:
    """Configuration commune des tableaux de cibles (libellés, formats, aides)."""
    cc = st.column_config
    return {
        "name": cc.TextColumn("Entreprise", width="medium"),
        "city": cc.TextColumn("Ville"),
        "department": cc.TextColumn("Dépt", width="small"),
        "naf_label": cc.TextColumn("Activité", width="medium"),
        "director_age": cc.NumberColumn("Âge dirigeant", format="%d ans",
                                        help="Âge du dirigeant principal (ou de la personne derrière sa holding)."),
        "revenue_m": cc.NumberColumn("CA (M€)", format="localized", help="Chiffre d'affaires du dernier exercice publié."),
        "ebe_margin": cc.NumberColumn("Marge EBE", format="percent", help="EBE / chiffre d'affaires (ratios INPI)."),
        "score": cc.ProgressColumn("Score", min_value=0, max_value=100, format="%d", width=110,
                                   help=f"Score sur 100. Qualifiée à partir de {threshold}."),
        "reco_tag": cc.MultiselectColumn("Recommandation", options=RECO_LABELS, color=RECO_HEX,
                                         help="Décision suggérée par des règles explicites (voir Aide)."),
        "ev_mid_m": cc.NumberColumn("VE (M€)", format="localized",
                                    help="Valeur d'entreprise indicative, milieu de fourchette (EBE × multiple)."),
        "equity_m": cc.NumberColumn("FP (M€)", format="localized",
                                    help="Fonds propres à réunir dans le montage indicatif (milieu de fourchette)."),
        "status_label": cc.TextColumn("Contact", help="Statut de la prise de contact."),
        "open": None,
    }  # fmt: skip


def targets_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Colonnes d'affichage (montants en M€, recommandation en étiquette colorée)."""
    out = df.copy()
    out["revenue_m"] = (out["revenue"] / 1e6).round(1)
    out["ev_mid_m"] = (out["ev_mid"] / 1e6).round(1)
    out["equity_m"] = (out["equity"] / 1e6).round(1)
    out["reco_tag"] = out["reco"].map(lambda r: [r])
    out["open"] = "Ouvrir"
    return out


CSS = f"""<style>
[data-testid="stHeader"] {{background:rgba(15,22,41,.92); backdrop-filter:blur(8px);
  border-bottom:1px solid {GRID};}}
.block-container {{padding-top:4.2rem; max-width:1500px;}}
h1, h2, h3 {{letter-spacing:-.015em;}}
[data-testid="stMetric"] {{background:linear-gradient(180deg,#1a2340 0%,{CARD} 100%);}}
[data-testid="stMetricLabel"] p {{font-size:.8rem; color:{MUTED}; font-weight:600; letter-spacing:.02em;}}
.pr-brand {{display:flex; align-items:center; gap:12px;}}
.pr-brand img {{width:44px; height:44px; filter:drop-shadow(0 4px 14px rgba(37,194,245,.35));}}
.pr-brand b {{display:block; font-size:1.45rem; font-weight:750; letter-spacing:-.03em; line-height:1.05;}}
.pr-brand b span {{color:{CYAN};}}
.pr-brand small {{color:{MUTED}; font-size:.8rem;}}
.pr-source {{text-align:center; font-size:.78rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  border-radius:999px; padding:5px 10px; margin-top:2px;}}
.pr-source.demo {{color:{AMBER}; border:1px solid rgba(255,181,71,.45); background:rgba(255,181,71,.08);}}
.pr-source.live {{color:{CYAN}; border:1px solid rgba(37,194,245,.45); background:rgba(37,194,245,.08);}}
.pr-title h1 {{font-size:1.9rem; margin:.4rem 0 0; padding:0;}}
.pr-title p {{color:{MUTED}; margin:.2rem 0 .4rem; font-size:1rem;}}
.pr-hero {{background:radial-gradient(120% 140% at 0% 0%, #1d3a63 0%, #172038 45%, {CARD} 100%);
  border:1px solid {GRID}; border-radius:18px; padding:1.4rem 1.6rem; margin:.3rem 0 .2rem;}}
.pr-hero .k {{color:{CYAN}; font-size:.8rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase;}}
.pr-hero h2 {{font-size:2.3rem; margin:.2rem 0 .3rem; padding:0; line-height:1.15;}}
.pr-hero h2 b {{color:{CYAN};}}
.pr-hero p {{color:#c4cde3; font-size:1.05rem; margin:0;}}
.pr-reco {{display:inline-block; padding:3px 10px; border-radius:999px; font-size:.8rem; font-weight:700;
  color:var(--c); border:1px solid color-mix(in srgb, var(--c) 55%, transparent);
  background:color-mix(in srgb, var(--c) 12%, transparent); white-space:nowrap;}}
.pr-reco.big {{font-size:1.05rem; padding:6px 16px;}}
.pr-ts {{background:linear-gradient(135deg,#1b2c4f 0%,{CARD} 70%); border:1px solid {GRID}; border-radius:18px;
  padding:1.2rem 1.5rem; display:flex; gap:1.5rem; align-items:center; justify-content:space-between;}}
.pr-ts h2 {{font-size:2rem; margin:0; padding:0; line-height:1.1;}}
.pr-ts .sub {{color:{MUTED}; margin-top:.35rem; font-size:.98rem;}}
.pr-ts .tags {{margin-top:.6rem; display:flex; gap:8px; flex-wrap:wrap;}}
.pr-ts .right {{text-align:right; min-width:220px;}}
.pr-ts .score {{font-size:2.6rem; font-weight:800; line-height:1; margin-top:.5rem;}}
.pr-ts .score small {{font-size:1rem; color:{MUTED}; font-weight:600;}}
.pr-ts .meta {{color:{MUTED}; font-size:.85rem;}}
.pr-kv {{display:grid; grid-template-columns:max-content 1fr; gap:.45rem 1.2rem; font-size:.95rem;}}
.pr-kv dt {{color:{MUTED};}} .pr-kv dd {{margin:0; font-weight:600;}}
.pr-list {{margin:.2rem 0 0; padding-left:1.1rem;}} .pr-list li {{margin:.25rem 0;}}
.pr-pos li::marker {{content:"＋ "; color:{GREEN}; font-weight:800;}}
.pr-neg li::marker {{content:"! "; color:{AMBER}; font-weight:800;}}
.pr-mail {{background:#111a2e; border:1px solid {GRID}; border-radius:12px; padding:1rem 1.2rem;
  line-height:1.6; white-space:pre-wrap;}}
.pr-warn {{display:inline-block; font-size:.75rem; font-weight:800; letter-spacing:.06em; color:{RED};
  border:1px solid rgba(255,107,129,.5); border-radius:6px; padding:3px 8px; margin-bottom:.5rem;}}
.pr-empty {{text-align:center; padding:2.2rem 1rem; color:{MUTED}; border:1px dashed {GRID}; border-radius:14px;}}
.pr-empty span {{font-size:2rem;}} .pr-empty p {{margin:.4rem 0 0;}}
.pr-item {{display:flex; justify-content:space-between; gap:10px; color:{MUTED}; font-size:.85rem; margin:-.35rem 0 .5rem 2rem;}}
.pr-foot {{color:{MUTED}; font-size:.8rem; text-align:center; margin-top:2.5rem; padding-top:1rem;
  border-top:1px solid {GRID};}}
[data-testid="stPageLink"] a {{border-radius:10px;}}
[data-testid="stPageLink"] a:hover {{background:rgba(37,194,245,.08);}}
.st-key-pr-actions [data-testid="stPageLink"] a {{border:1px solid {GRID}; background:{CARD}; padding:.55rem .8rem;
  justify-content:center;}}
</style>"""


def inject_css() -> None:
    st.html(CSS)


def footer() -> None:
    st.html(
        '<div class="pr-foot">Score déterministe et explicable · brouillons à relire, aucun envoi '
        "automatique · données publiques (annuaire des entreprises, BODACC, INPI) · "
        '<a href="https://github.com/Mateo-MoralesLeGuillou/pme-radar">code source</a></div>'
    )
