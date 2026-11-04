import os
import shlex
import stat
import sys

import pytest
from typer.testing import CliRunner

from pme_radar import pdf
from pme_radar.cli import app

from .conftest import ROOT

pytestmark = pytest.mark.skipif(os.name == "nt", reason="faux navigateur en script POSIX")

# Faux navigateur : vérifie les options d'impression et écrit un PDF minimal.
FAKE = """import sys
from pathlib import Path
args = sys.argv[1:]
assert "--headless" in args and "--no-pdf-header-footer" in args, args
out = next(a.split("=", 1)[1] for a in args if a.startswith("--print-to-pdf="))
src = Path(args[-1][len("file://"):])
Path(out).write_bytes(b"%PDF-1.7 " + src.read_bytes()[:40])
sys.exit({code})
"""


def make_browser(path, code=0):
    # lanceur sh : un shebang ne supporte pas les espaces dans le chemin de l'interpréteur
    script = path.with_suffix(".py")
    script.write_text(FAKE.format(code=code), encoding="utf-8")
    launcher = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n'
    path.write_text(launcher, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_find_browser_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PME_RADAR_BROWSER", str(tmp_path / "absent"))
    assert pdf.find_browser() is None
    exe = make_browser(tmp_path / "chrome")
    monkeypatch.setenv("PME_RADAR_BROWSER", str(exe))
    assert pdf.find_browser() == str(exe)


def test_html_to_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("PME_RADAR_BROWSER", str(make_browser(tmp_path / "chrome")))
    out = pdf.html_to_pdf("<p>Rapport</p>", tmp_path / "sortie" / "r.pdf")
    assert out.read_bytes().startswith(b"%PDF") and b"Rapport" in out.read_bytes()
    assert pdf.html_to_pdf_bytes("<p>x</p>").startswith(b"%PDF")


def test_pdf_unavailable_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("PME_RADAR_BROWSER", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))  # aucun navigateur dans le PATH
    monkeypatch.setattr(pdf, "INSTALLS", ())
    with pytest.raises(pdf.PdfUnavailable, match="Imprimer"):
        pdf.html_to_pdf("<p>x</p>", tmp_path / "r.pdf")
    failing = make_browser(tmp_path / "casse", code=1)
    with pytest.raises(pdf.PdfUnavailable):
        pdf.html_to_pdf("<p>x</p>", tmp_path / "r.pdf", browser=str(failing))


def test_cli_report_pdf(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("PME_RADAR_BROWSER", str(make_browser(tmp_path / "chrome")))
    data = str(tmp_path / "data")
    assert CliRunner().invoke(app, ["run", "--offline", "--data-dir", data]).exit_code == 0
    out = tmp_path / "rapport.html"
    r = CliRunner().invoke(app, ["report", "--data-dir", data, "--output", str(out), "--pdf"])
    assert r.exit_code == 0, r.output
    assert "PDF A4" in r.output and (tmp_path / "rapport.pdf").read_bytes().startswith(b"%PDF")
    monkeypatch.setenv("PME_RADAR_BROWSER", str(tmp_path / "absent"))  # sans navigateur : HTML seul
    r = CliRunner().invoke(app, ["report", "--data-dir", data, "--output", str(out), "--pdf"])
    assert r.exit_code == 0 and "PDF non produit" in r.output
