"""Export PDF du rapport par un navigateur Chrome, Chromium ou Edge installé (impression sans fenêtre).

Aucune dépendance Python : le navigateur imprime le HTML autonome en A4, avec les marges, la
pagination et les pieds de page « Strictement confidentiel » de la feuille de style (@page). Sans
navigateur, le rapport reste disponible en HTML (« Imprimer > Enregistrer en PDF »). Le chemin d'un
navigateur peut être imposé par la variable PME_RADAR_BROWSER.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome",
         "msedge", "microsoft-edge")  # fmt: skip
INSTALLS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


class PdfUnavailable(RuntimeError):
    """Aucun navigateur utilisable, ou l'impression a échoué."""


def find_browser() -> str | None:
    """Chemin d'un navigateur capable d'imprimer en PDF, ou None."""
    forced = os.environ.get("PME_RADAR_BROWSER")
    if forced:
        return forced if Path(forced).exists() else shutil.which(forced)
    for name in NAMES:
        path = shutil.which(name)
        if path:
            return path
    return next((p for p in INSTALLS if Path(p).exists()), None)


def html_to_pdf(html: str, out: Path, browser: str | None = None, timeout: int = 180) -> Path:
    """Imprime `html` en PDF A4 dans `out` (écrasé s'il existe)."""
    exe = browser or find_browser()
    if exe is None:
        raise PdfUnavailable(
            "Aucun navigateur Chrome, Chromium ou Edge trouvé (variable PME_RADAR_BROWSER pour en "
            "indiquer un) : ouvrir le HTML puis « Imprimer > Enregistrer en PDF »."
        )
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "rapport.html"
        src.write_text(html, encoding="utf-8")
        # profil temporaire par défaut en mode sans tête (un --user-data-dir explicite peut bloquer
        # Chrome) ; sorties vers des fichiers, pas des tubes : des processus auxiliaires du
        # navigateur peuvent garder un tube ouvert après la fin de l'impression
        cmd = [exe, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}",
               src.as_uri()]  # fmt: skip
        if getattr(os, "geteuid", lambda: 1)() == 0:
            cmd.insert(1, "--no-sandbox")  # Chrome refuse le bac à sable en root (conteneurs)
        log = Path(tmp) / "navigateur.log"
        try:
            with log.open("wb") as err:
                subprocess.run(
                    cmd, check=True, stdout=subprocess.DEVNULL, stderr=err, timeout=timeout
                )
        except (OSError, subprocess.SubprocessError) as exc:
            detail = log.read_text(errors="replace")[-300:] if log.exists() else ""
            raise PdfUnavailable(
                f"Impression PDF impossible avec {exe} : {exc} {detail}".strip()
            ) from exc
    if not out.exists() or out.stat().st_size == 0:
        raise PdfUnavailable(f"Le navigateur {exe} n'a produit aucun PDF.")
    return out


def html_to_pdf_bytes(html: str, browser: str | None = None) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        return html_to_pdf(html, Path(tmp) / "rapport.pdf", browser).read_bytes()
