"""CLI `pme-radar` : source → enrich → score → draft → export (+ onepager, track, deliverability)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import __version__, funnel, outreach
from . import enrich as enrich_mod
from . import export as export_mod
from . import onepager as onepager_mod
from . import report as report_mod
from .config import ConfigError, DataPaths, load_scoring, load_thesis, load_yaml
from .deliverability import render_report, run_checks
from .llm.analysis import analyze_top, get_provider
from .models import Stage
from .scoring import score_all
from .sources import bodacc
from .sources._http import CachedClient, FixtureFetcher, JsonFetcher, ttl_from_env
from .sources.inpi_ratios import fetch_ratios
from .sources.recherche_entreprises import (
    fetch_companies,
    fetch_company_by_siren,
    load_raw,
    save_raw,
)
from .store import read_companies, write_companies

app = typer.Typer(
    help="pme-radar : origination search fund à partir de l'open data française.",
    no_args_is_help=True,
)

DataDir = typer.Option("data", help="Dossier de travail (gitignoré).")
Offline = typer.Option(
    False, "--offline", help="Utiliser les fixtures synthétiques (aucun réseau)."
)
Refresh = typer.Option(False, "--refresh", help="Ignorer le cache disque et réinterroger les API.")
ThesisOpt = typer.Option("config/thesis.yaml", help="Fichier de thèse d'investissement.")
ScoringOpt = typer.Option("config/scoring.yaml", help="Fichier de barèmes de scoring.")
CampaignOpt = typer.Option("config/campaign.yaml", help="Seuils et mentions de campagne.")
FixturesOpt = typer.Option("tests/fixtures", help="Dossier des fixtures (mode --offline).")
SirenOpt = typer.Option(None, "--siren", help="Dossier(s) précis (option répétable).")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"pme-radar {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Afficher la version."
    ),
) -> None:
    load_dotenv()


def _fetcher(offline: bool, paths: DataPaths, fixtures: str, refresh: bool = False) -> JsonFetcher:
    if offline:
        return FixtureFetcher(fixtures)
    return CachedClient(paths.cache, ttl_seconds=ttl_from_env(), refresh=refresh)


STAGE_LABELS = {"qualified": "qualifiées", "identified": "identifiées", "excluded": "exclues"}


def _print_funnel(funnel_df: pd.DataFrame) -> None:
    """Entonnoir en tableau lisible (couleurs si terminal, texte simple sinon)."""
    table = Table(title="Entonnoir d'origination", title_style="bold cyan", header_style="bold")
    table.add_column("Étape")
    table.add_column("Nombre", justify="right")
    table.add_column("Conversion", justify="right", style="cyan")
    for _, row in funnel_df.iterrows():
        conv = row["conversion_vs_précédente"]
        table.add_row(str(row["étape"]), str(row["nombre"]), "" if pd.isna(conv) else f"{conv:.0%}")
    Console().print(table)


def _fail(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _thesis(path: str) -> dict:
    try:
        return load_thesis(path)
    except (ConfigError, FileNotFoundError) as exc:
        _fail(str(exc))
        raise  # pragma: no cover (inatteignable : _fail lève Exit)


def _scoring(path: str) -> dict:
    try:
        return load_scoring(path)
    except (ConfigError, FileNotFoundError) as exc:
        _fail(str(exc))
        raise  # pragma: no cover


def _read(path, step: str) -> list:
    try:
        return read_companies(path)
    except FileNotFoundError:
        _fail(f"{path} introuvable : lancer d'abord `pme-radar {step}`.")
        raise  # pragma: no cover


@app.command("check-config")
def check_config(thesis: str = ThesisOpt, scoring: str = ScoringOpt) -> None:
    """Valide thesis.yaml et scoring.yaml (structure, codes NAF, total de 100 points)."""
    t, s = _thesis(thesis), _scoring(scoring)
    typer.echo(
        f"Configuration valide : {len(t['naf_codes'])} codes NAF, "
        f"{len(t['departments'])} département(s), seuil de qualification {s['qualified_threshold']}."
    )


@app.command()
def source(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    fixtures: str = FixturesOpt,
    refresh: bool = Refresh,
) -> None:
    """Identifie les entreprises correspondant à la thèse → data/raw/companies.parquet."""
    paths = DataPaths(data_dir)
    th = _thesis(thesis)
    fetcher = _fetcher(offline, paths, fixtures, refresh)

    def progress(naf: str, n: int) -> None:
        typer.echo(f"  {naf} : {n} résultat(s)")

    results = fetch_companies(fetcher, th, on_progress=progress)
    save_raw(results, paths.raw)
    suffix = " [OFFLINE]" if offline else ""
    if isinstance(fetcher, CachedClient):
        suffix += f" ({fetcher.calls} appel(s) réseau, {fetcher.cache_hits} depuis le cache)"
    typer.echo(f"{len(results)} entreprises sourcées → {paths.raw}{suffix}")


@app.command()
def enrich(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    fixtures: str = FixturesOpt,
    skip_bodacc: bool = typer.Option(False, help="Ne pas interroger le BODACC."),
    skip_ratios: bool = typer.Option(False, help="Ne pas interroger les ratios BCE/INPI (EBE)."),
    refresh: bool = Refresh,
) -> None:
    """Normalise, calcule les champs dérivés et signale les procédures collectives."""
    paths = DataPaths(data_dir)
    th = _thesis(thesis)
    if not paths.raw.exists():
        _fail(f"{paths.raw} introuvable : lancer d'abord `pme-radar source`.")
    raw = load_raw(paths.raw)
    sirens = [r["siren"] for r in raw]
    api = _fetcher(offline, paths, fixtures, refresh)
    typer.echo("  BODACC (procédures collectives)…" if not skip_bodacc else "  BODACC ignoré")
    procs = None if skip_bodacc else bodacc.collective_procedure_sirens(api, sirens)
    typer.echo("  Ratios BCE/INPI (EBE, endettement)…" if not skip_ratios else "  Ratios ignorés")
    ratios = None if skip_ratios else fetch_ratios(api, sirens)
    labels = {n["code"]: n["label"] for n in th["naf_codes"]}
    companies = enrich_mod.enrich(
        raw,
        date.today(),
        labels,
        procs,
        lambda siren: fetch_company_by_siren(api, siren),
        ratios,
    )
    write_companies(companies, paths.enriched)
    n_proc = sum(bool(c.has_collective_procedure) for c in companies)
    n_hold = sum(c.holding_owner is not None for c in companies)
    typer.echo(
        f"{len(companies)} entreprises enrichies ({n_proc} avec procédure collective, "
        f"{n_hold} holding(s) personnelle(s)) → {paths.enriched}"
    )


@app.command()
def score(data_dir: str = DataDir, thesis: str = ThesisOpt, scoring: str = ScoringOpt) -> None:
    """Calcule le score explicable et le statut (identified / qualified / excluded)."""
    paths = DataPaths(data_dir)
    cfg, th = _scoring(scoring), _thesis(thesis)
    ranked = score_all(_read(paths.enriched, "enrich"), cfg, th)
    write_companies(ranked, paths.scored)
    counts = pd.Series([c.stage.value for c in ranked]).value_counts()
    summary = " · ".join(f"{n} {STAGE_LABELS.get(str(k), str(k))}" for k, n in counts.items())
    typer.echo(f"Scores calculés → {paths.scored} | {summary}")


@app.command()
def draft(
    data_dir: str = DataDir,
    scoring: str = ScoringOpt,
    llm: str = typer.Option("mock", help="mock (défaut, sans clé) ou anthropic."),
    top_n: int = typer.Option(0, help="Nb de cibles à analyser (0 = valeur de scoring.yaml)."),
    campaign_id: str = typer.Option("", help="Identifiant de campagne (défaut : date)."),
    campaign_config: str = CampaignOpt,
    reuse: bool = typer.Option(
        True, help="Réutiliser les analyses dont les faits n'ont pas changé (économise le LLM)."
    ),
) -> None:
    """Mini-thèse, signaux d'alerte et BROUILLON d'email pour le top N. N'envoie rien."""
    paths = DataPaths(data_dir)
    n = top_n or _scoring(scoring)["top_n_drafts"]
    try:
        provider = get_provider(llm)
    except (RuntimeError, ValueError) as exc:
        _fail(str(exc))
        raise  # pragma: no cover
    previous = {}
    if reuse and paths.analyzed.exists():
        previous = {c.siren: c.analysis for c in read_companies(paths.analyzed) if c.analysis}
    companies = _read(paths.scored, "score")
    report = analyze_top(companies, provider, n, previous)
    write_companies(companies, paths.analyzed)
    footer = load_yaml(campaign_config).get("compliance_footer")
    drafts = outreach.drafts_frame(companies, footer)
    paths.ensure(paths.out / "drafts.csv")
    drafts.to_csv(paths.out / "drafts.csv", index=False)
    outreach.init_campaign(
        companies, campaign_id or f"camp-{date.today():%Y%m%d}", paths.out / "campaign.csv"
    )
    typer.echo(
        f"{len(drafts)} brouillons à relire → {paths.out / 'drafts.csv'} (LLM : {llm} ; "
        f"{report.generated} généré(s), {report.reused} réutilisé(s), {len(report.failed)} échec(s))"
    )
    for siren, why in report.failed.items():
        typer.secho(f"  échec {siren} : {why}", fg=typer.colors.YELLOW, err=True)
    if report.failed and not (report.generated or report.reused):
        _fail("Aucune analyse produite : vérifier la clé API, le quota ou le modèle.")


@app.command()
def onepager(
    siren: str = typer.Option("", help="Une seule cible (défaut : toutes les qualifiées)."),
    top_n: int = typer.Option(0, help="Limiter aux N meilleures (0 = toutes)."),
    data_dir: str = DataDir,
    thesis: str = ThesisOpt,
) -> None:
    """Fiche Markdown d'une page par cible qualifiée → data/out/onepagers/<SIREN>.md."""
    paths = DataPaths(data_dir)
    src = paths.analyzed if paths.analyzed.exists() else paths.scored
    cfg = _thesis(thesis).get("valuation") or {"ebe_multiple_low": 4.0, "ebe_multiple_high": 6.0}
    companies = [
        c
        for c in _read(src, "score")
        if c.score is not None and (c.siren == siren if siren else c.stage == Stage.QUALIFIED)
    ]
    if siren and not companies:
        _fail(f"SIREN {siren} introuvable parmi les cibles notées.")
    companies = companies[:top_n] if top_n else companies
    for c in companies:
        paths.ensure(paths.out / "onepagers" / f"{c.siren}.md").write_text(
            onepager_mod.render(c, cfg), encoding="utf-8"
        )
    typer.echo(f"{len(companies)} fiche(s) → {paths.out / 'onepagers'}")


@app.command()
def export(
    data_dir: str = DataDir,
    sheets: bool = typer.Option(True, help="Exporter vers Google Sheets si configuré."),
    thesis: str = ThesisOpt,
    scoring: str = ScoringOpt,
) -> None:
    """Exporte CSV (toujours) et Google Sheets (si GOOGLE_* renseignés)."""
    paths = DataPaths(data_dir)
    src = paths.analyzed if paths.analyzed.exists() else paths.scored
    targets = export_mod.targets_frame(_read(src, "score"), _scoring(scoring), _thesis(thesis))
    tabs = export_mod.build_tabs(targets, outreach.load_campaign(paths.out / "campaign.csv"))
    files = export_mod.export_csv(tabs, paths.out)
    typer.echo(f"{len(files)} CSV écrits dans {paths.out}")
    if sheets and export_mod.sheets_configured():
        export_mod.export_sheets(export_mod.open_spreadsheet(), tabs)
        typer.echo("Google Sheets mis à jour.")
    else:
        typer.echo("Google Sheets non configuré : export CSV uniquement.")
    _print_funnel(tabs["Funnel"])


@app.command()
def report(
    data_dir: str = DataDir,
    thesis: str = ThesisOpt,
    scoring: str = ScoringOpt,
    campaign_config: str = CampaignOpt,
    top_n: int = typer.Option(
        10, help="Cibles à approcher détaillées (+ cibles à creuser et à documenter, N/4 au plus)."
    ),
    siren: list[str] | None = SirenOpt,
    output: str = typer.Option(
        "", help="Fichier de sortie (défaut : data/out/rapport_deal_flow.html)."
    ),
) -> None:
    """Rapport de deal flow : synthèse du pipeline + dossier de pré-due diligence par cible."""
    paths = DataPaths(data_dir)
    src = paths.analyzed if paths.analyzed.exists() else paths.scored
    companies = _read(src, "score")
    html_text, chosen = report_mod.build_report(
        companies,
        _scoring(scoring),
        _thesis(thesis),
        campaign=outreach.load_campaign(paths.out / "campaign.csv"),
        top_n=top_n,
        sirens=siren or None,
        footer=load_yaml(campaign_config).get("compliance_footer"),
    )
    if siren and not chosen:
        _fail("Aucun des SIREN demandés n'est parmi les cibles notées.")
    out = Path(output) if output else paths.out / "rapport_deal_flow.html"
    paths.ensure(out).write_text(html_text, encoding="utf-8")
    labels = Counter(d.rec.label for d in chosen)
    detail = ", ".join(f"{n} {lbl.lower()}" for lbl, n in labels.most_common())
    typer.echo(f"Rapport de deal flow : {len(chosen)} dossier(s) ({detail}) → {out}")
    typer.echo(
        "Ouvrir dans un navigateur ; « Imprimer > Enregistrer en PDF » pour une version papier."
    )


@app.command()
def run(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    scoring: str = ScoringOpt,
    fixtures: str = FixturesOpt,
    llm: str = typer.Option("mock", help="mock (défaut, sans clé) ou anthropic."),
    top_n: int = typer.Option(0, help="Nb de cibles à analyser (0 = valeur de scoring.yaml)."),
    refresh: bool = Refresh,
    campaign_config: str = CampaignOpt,
) -> None:
    """Enchaîne source → enrich → score → draft → export."""
    _thesis(thesis), _scoring(scoring)  # échoue tôt si la configuration est invalide
    source(data_dir, offline, thesis, fixtures, refresh)
    enrich(data_dir, offline, thesis, fixtures, False, False, refresh)
    score(data_dir, thesis, scoring)
    draft(data_dir, scoring, llm, top_n, "", campaign_config, True)
    export(data_dir, True, thesis, scoring)
    report(data_dir, thesis, scoring, campaign_config, 10, None, "")


@app.command()
def track(
    siren: str,
    status: str = typer.Argument(..., help="contacted|replied|meeting|declined|bounced"),
    data_dir: str = DataDir,
    note: str = typer.Option("", help="Commentaire libre."),
    on: str = typer.Option("", "--date", help="Date de l'événement AAAA-MM-JJ (défaut : jour)."),
) -> None:
    """Met à jour le suivi de campagne après une action humaine (envoi, réponse, RDV…)."""
    try:
        day = date.fromisoformat(on) if on else None
        outreach.update_status(
            DataPaths(data_dir).out / "campaign.csv", siren, status, on=day, note=note
        )
    except (ValueError, KeyError) as exc:
        _fail(str(exc).strip("'\""))
    typer.echo(f"{siren} → {status}")


@app.command()
def deliverability(
    domain: str = typer.Option(None, help="Domaine d'envoi à auditer (ex. exemple.fr)."),
    selector: str = typer.Option(None, help="Sélecteur DKIM (ex. google, selector1)."),
    data_dir: str = DataDir,
    campaign_config: str = CampaignOpt,
) -> None:
    """Audit DNS (MX/SPF/DKIM/DMARC) et KPI de campagne avec seuils d'alerte."""
    if domain:
        typer.echo(render_report(domain, run_checks(domain, selector)))
    camp = outreach.load_campaign(DataPaths(data_dir).out / "campaign.csv")
    if not camp.empty:
        typer.echo(
            "\n" + funnel.campaign_metrics(camp, load_yaml(campaign_config)).to_string(index=False)
        )
    elif not domain:
        typer.echo("Rien à faire : passer --domain ou produire un suivi de campagne.")


if __name__ == "__main__":
    app()
