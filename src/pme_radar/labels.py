"""Libellés lisibles des codes INSEE utilisés dans le rapport et le dashboard."""

from __future__ import annotations

DEPARTMENTS = {
    "75": "Paris", "77": "Seine-et-Marne", "78": "Yvelines", "91": "Essonne",
    "92": "Hauts-de-Seine", "93": "Seine-Saint-Denis", "94": "Val-de-Marne", "95": "Val-d'Oise",
}  # fmt: skip
HEADCOUNT = {
    "00": "0 salarié", "01": "1-2 salariés", "02": "3-5 salariés", "03": "6-9 salariés",
    "11": "10-19 salariés", "12": "20-49 salariés", "21": "50-99 salariés",
    "22": "100-199 salariés", "31": "200-249 salariés", "32": "250-499 salariés",
}  # fmt: skip
LEGAL_FORMS = {  # catégories juridiques INSEE les plus fréquentes pour des PME
    "5202": "SNC", "5499": "SARL", "5498": "SARL unipersonnelle (EURL)", "5599": "SA à conseil d'administration",
    "5699": "SA à directoire", "5710": "SAS", "5720": "SASU", "6540": "SCI",
}  # fmt: skip


def department(code: str | None) -> str:
    return "n.d." if not code else f"{DEPARTMENTS.get(code, code)} ({code})"


def headcount(band: str | None) -> str:
    return "n.d." if not band else HEADCOUNT.get(band, f"tranche {band}")


def legal_form(code: str | None) -> str:
    return "n.d." if not code else LEGAL_FORMS.get(code, f"catégorie juridique {code}")
