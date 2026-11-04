"""CLI `pme-radar` : source → enrich → score → draft → export (+ deliverability, track)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import typer
from dotenv import load_dotenv

from . import enrich as enrich_mod
from . import export as export_mod
from . import funnel, outreach
from .config import DataPaths, load_yaml
from .deliverability import render_report, run_checks
from .llm.analysis import analyze_top, get_provider
from .scoring import score_all
from .sources import bodacc
from .sources._http import CachedClient, FixtureFetcher, JsonFetcher
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
ThesisOpt = typer.Option("config/thesis.yaml", help="Fichier de thèse d'investissement.")
ScoringOpt = typer.Option("config/scoring.yaml", help="Fichier de barèmes de scoring.")
FixturesOpt = typer.Option("tests/fixtures", help="Dossier des fixtures (mode --offline).")


@app.callback()
def _main() -> None:
    load_dotenv()


def _fetcher(offline: bool, paths: DataPaths, fixtures: str) -> JsonFetcher:
    return FixtureFetcher(fixtures) if offline else CachedClient(paths.cache)


@app.command()
def source(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    fixtures: str = FixturesOpt,
) -> None:
    """Identifie les entreprises correspondant à la thèse → data/raw/companies.parquet."""
    paths = DataPaths(data_dir)
    results = fetch_companies(_fetcher(offline, paths, fixtures), load_yaml(thesis))
    save_raw(results, paths.raw)
    typer.echo(
        f"{len(results)} entreprises sourcées → {paths.raw}" + (" [OFFLINE]" if offline else "")
    )


@app.command()
def enrich(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    fixtures: str = FixturesOpt,
    skip_bodacc: bool = typer.Option(False, help="Ne pas interroger le BODACC."),
) -> None:
    """Normalise, calcule les champs dérivés et signale les procédures collectives."""
    paths = DataPaths(data_dir)
    th = load_yaml(thesis)
    raw = load_raw(paths.raw)
    procs = (
        None
        if skip_bodacc
        else bodacc.collective_procedure_sirens(
            _fetcher(offline, paths, fixtures), [r["siren"] for r in raw]
        )
    )
    labels = {n["code"]: n["label"] for n in th["naf_codes"]}
    api = _fetcher(offline, paths, fixtures)
    companies = enrich_mod.enrich(
        raw, date.today(), labels, procs, lambda siren: fetch_company_by_siren(api, siren)
    )
    write_companies(companies, paths.enriched)
    n_proc = sum(bool(c.has_collective_procedure) for c in companies)
    typer.echo(
        f"{len(companies)} entreprises enrichies ({n_proc} avec procédure collective) "
        f"→ {paths.enriched}"
    )


@app.command()
def score(data_dir: str = DataDir, thesis: str = ThesisOpt, scoring: str = ScoringOpt) -> None:
    """Calcule le score explicable et le statut (identified / qualified / excluded)."""
    paths = DataPaths(data_dir)
    cfg = load_yaml(scoring)
    ranked = score_all(read_companies(paths.enriched), cfg, load_yaml(thesis))
    write_companies(ranked, paths.scored)
    counts = pd.Series([c.stage.value for c in ranked]).value_counts().to_dict()
    typer.echo(f"Scores calculés → {paths.scored} | {counts}")


@app.command()
def draft(
    data_dir: str = DataDir,
    scoring: str = ScoringOpt,
    llm: str = typer.Option("mock", help="mock (défaut, sans clé) ou anthropic."),
    top_n: int = typer.Option(0, help="Nb de cibles à analyser (0 = valeur de scoring.yaml)."),
    campaign_id: str = typer.Option("", help="Identifiant de campagne (défaut : date)."),
) -> None:
    """Mini-thèse, signaux d'alerte et BROUILLON d'email pour le top N. N'envoie rien."""
    paths = DataPaths(data_dir)
    n = top_n or load_yaml(scoring)["top_n_drafts"]
    companies = analyze_top(read_companies(paths.scored), get_provider(llm), n)
    write_companies(companies, paths.analyzed)
    drafts = outreach.drafts_frame(companies)
    paths.ensure(paths.out / "drafts.csv")
    drafts.to_csv(paths.out / "drafts.csv", index=False)
    outreach.init_campaign(
        companies, campaign_id or f"camp-{date.today():%Y%m%d}", paths.out / "campaign.csv"
    )
    typer.echo(f"{len(drafts)} brouillons à relire → {paths.out / 'drafts.csv'} (LLM : {llm})")


@app.command()
def export(
    data_dir: str = DataDir,
    sheets: bool = typer.Option(True, help="Exporter vers Google Sheets si configuré."),
) -> None:
    """Exporte CSV (toujours) et Google Sheets (si GOOGLE_* renseignés)."""
    paths = DataPaths(data_dir)
    src = paths.analyzed if paths.analyzed.exists() else paths.scored
    targets = export_mod.targets_frame(read_companies(src))
    tabs = export_mod.build_tabs(targets, outreach.load_campaign(paths.out / "campaign.csv"))
    files = export_mod.export_csv(tabs, paths.out)
    typer.echo(f"{len(files)} CSV écrits dans {paths.out}")
    if sheets and export_mod.sheets_configured():
        export_mod.export_sheets(export_mod.open_spreadsheet(), tabs)
        typer.echo("Google Sheets mis à jour.")
    else:
        typer.echo("Google Sheets non configuré : export CSV uniquement.")
    typer.echo(tabs["Funnel"].to_string(index=False))


@app.command()
def run(
    data_dir: str = DataDir,
    offline: bool = Offline,
    thesis: str = ThesisOpt,
    scoring: str = ScoringOpt,
    fixtures: str = FixturesOpt,
    llm: str = typer.Option("mock"),
    top_n: int = typer.Option(0),
) -> None:
    """Enchaîne source → enrich → score → draft → export."""
    source(data_dir, offline, thesis, fixtures)
    enrich(data_dir, offline, thesis, fixtures, False)
    score(data_dir, thesis, scoring)
    draft(data_dir, scoring, llm, top_n, "")
    export(data_dir, True)


@app.command()
def track(
    siren: str,
    status: str = typer.Argument(..., help="contacted|replied|meeting|declined|bounced"),
    data_dir: str = DataDir,
    note: str = typer.Option(""),
) -> None:
    """Met à jour le suivi de campagne après une action humaine (envoi, réponse, RDV…)."""
    outreach.update_status(DataPaths(data_dir).out / "campaign.csv", siren, status, note=note)
    typer.echo(f"{siren} → {status}")


@app.command()
def deliverability(
    domain: str = typer.Option(None, help="Domaine d'envoi à auditer (ex. exemple.fr)."),
    selector: str = typer.Option(None, help="Sélecteur DKIM (ex. google, selector1)."),
    data_dir: str = DataDir,
    campaign_config: str = "config/campaign.yaml",
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
