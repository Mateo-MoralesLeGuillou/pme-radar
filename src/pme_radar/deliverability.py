"""Vérifications DNS de délivrabilité : MX, SPF, DMARC, DKIM (sélecteur fourni)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import dns.exception
import dns.resolver


class Resolver(Protocol):
    def txt(self, name: str) -> list[str]: ...
    def mx(self, name: str) -> list[str]: ...


class DnsResolver:
    """Adaptateur dnspython. Retourne [] si le nom n'existe pas ou ne répond pas."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._r = dns.resolver.Resolver()
        self._r.lifetime = timeout

    def _q(self, name: str, rtype: str):
        try:
            return self._r.resolve(name, rtype)
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout,
        ):
            return []

    def txt(self, name: str) -> list[str]:
        return ["".join(p.decode() for p in r.strings) for r in self._q(name, "TXT")]

    def mx(self, name: str) -> list[str]:
        return [str(r.exchange).rstrip(".") for r in self._q(name, "MX")]


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail | skipped
    detail: str
    recommendation: str = ""


def check_mx(r: Resolver, domain: str) -> Check:
    hosts = r.mx(domain)
    if not hosts:
        return Check(
            "MX",
            "fail",
            "aucun enregistrement MX",
            "Configurer les MX : sans eux, le domaine ne peut pas recevoir les réponses.",
        )
    return Check("MX", "ok", ", ".join(hosts))


def check_spf(r: Resolver, domain: str) -> Check:
    recs = [t.strip() for t in r.txt(domain) if t.strip().lower().startswith("v=spf1")]
    if not recs:
        return Check(
            "SPF",
            "fail",
            "aucun enregistrement SPF",
            "Publier un TXT « v=spf1 include:<fournisseur> -all ».",
        )
    if len(recs) > 1:
        return Check(
            "SPF",
            "fail",
            "plusieurs enregistrements SPF (invalide)",
            "Fusionner en un seul enregistrement SPF.",
        )
    rec = recs[0].lower()
    m = re.search(r"(?:^|\s)([-~?+]?)all(?:\s|$)", rec)
    if m is None:
        if "redirect=" in rec:  # politique déléguée à un autre domaine : valide
            return Check("SPF", "ok", recs[0] + " (politique déléguée via redirect=)")
        return Check("SPF", "fail", recs[0], "Terminer par -all (ou ~all).")
    qualifier = m.group(1) or "+"
    if qualifier == "-":
        return Check("SPF", "ok", recs[0])
    if qualifier == "~":
        return Check("SPF", "warn", recs[0], "Passer de ~all à -all une fois les flux validés.")
    return Check("SPF", "fail", recs[0], "Terminer par -all (ou ~all) ; éviter ?all et +all.")


def check_dmarc(r: Resolver, domain: str) -> Check:
    recs = [
        t.strip() for t in r.txt(f"_dmarc.{domain}") if t.strip().lower().startswith("v=dmarc1")
    ]
    if not recs:
        return Check(
            "DMARC",
            "fail",
            "aucun enregistrement DMARC",
            "Publier _dmarc : « v=DMARC1; p=none; rua=mailto:dmarc@<domaine> » pour "
            "commencer, puis durcir.",
        )
    if len(recs) > 1:
        return Check(
            "DMARC",
            "fail",
            "plusieurs enregistrements DMARC (ignorés par les destinataires)",
            "Ne garder qu'un seul enregistrement TXT sur _dmarc.",
        )
    tags = {
        kv.split("=", 1)[0].strip().lower(): kv.split("=", 1)[1].strip()
        for kv in recs[0].split(";")
        if "=" in kv
    }
    policy = tags.get("p", "").lower()
    if policy == "none":
        return Check(
            "DMARC",
            "warn",
            recs[0],
            "Politique p=none : monitoring seul. Viser quarantine puis reject.",
        )
    if policy in ("quarantine", "reject"):
        extra = "" if "rua" in tags else "Ajouter rua=mailto:… pour recevoir les rapports."
        return Check("DMARC", "ok" if not extra else "warn", recs[0], extra)
    return Check("DMARC", "fail", recs[0], "Politique p= absente ou invalide.")


def check_dkim(r: Resolver, domain: str, selector: str | None) -> Check:
    if not selector:
        return Check(
            "DKIM",
            "skipped",
            "aucun sélecteur fourni",
            "Relancer avec --selector <sélecteur> (visible dans les en-têtes d'un email "
            "envoyé : « s=… »).",
        )
    recs = r.txt(f"{selector}._domainkey.{domain}")
    if any("p=" in t for t in recs):
        return Check("DKIM", "ok", f"clé publique trouvée pour le sélecteur « {selector} »")
    return Check(
        "DKIM",
        "fail",
        f"aucune clé pour le sélecteur « {selector} »",
        "Activer DKIM chez le fournisseur d'emailing et publier l'enregistrement fourni.",
    )


def run_checks(
    domain: str, selector: str | None = None, resolver: Resolver | None = None
) -> list[Check]:
    r = resolver or DnsResolver()
    return [
        check_mx(r, domain),
        check_spf(r, domain),
        check_dmarc(r, domain),
        check_dkim(r, domain, selector),
    ]


def render_report(domain: str, checks: list[Check]) -> str:
    icon = {"ok": "✅", "warn": "⚠️", "fail": "❌", "skipped": "⏭️"}
    lines = [f"# Rapport de délivrabilité — {domain}", ""]
    for c in checks:
        lines.append(f"- {icon[c.status]} **{c.name}** : {c.detail}")
        if c.recommendation:
            lines.append(f"  - Recommandation : {c.recommendation}")
    fails = sum(c.status == "fail" for c in checks)
    warns = sum(c.status == "warn" for c in checks)
    verdict = (
        "NON PRÊT : corriger les ❌ avant tout envoi."
        if fails
        else "Prêt avec réserves."
        if warns
        else "Prêt."
    )
    return "\n".join(lines + ["", f"**Verdict : {verdict}**"])
