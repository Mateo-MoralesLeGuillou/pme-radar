"""Narration de la vidéo (voix off et sous-titres), calée sur la timeline de motion.js.

`text` est affiché en sous-titres ; `say` est envoyé à la synthèse vocale (nombres en toutes lettres
pour une diction sûre). Chaque segment doit tenir avant le début du suivant : voiceover.py accélère
légèrement (jusqu'à x1,15) un segment trop long et signale ceux qui débordent encore.
Aucun chiffre de marché n'est avancé : seuls les agrégats du run réel (Hauts-de-Seine) sont cités.
"""

from __future__ import annotations

from dataclasses import dataclass

DURATION = 91.0  # doit rester égal à DURATION dans motion.js


@dataclass(frozen=True)
class Segment:
    start: float  # secondes, sur la timeline de la vidéo
    text: str  # sous-titre
    say: str = ""  # texte lu, si différent du sous-titre

    @property
    def spoken(self) -> str:
        return self.say or self.text


SEGMENTS = [
    Segment(0.9, "pme-radar repère, dans l'open data, les PME qui pourraient bientôt changer de mains.",
            "P.M.E. radar repère, dans l'open data, les P.M.E. qui pourraient bientôt changer de mains."),
    Segment(7.9, "Rien que dans les Hauts-de-Seine, 343 sociétés correspondent à notre thèse. Mais sans "
                 "signal clair, impossible de savoir qui appeler.",
            "Rien que dans les Hauts-de-Seine, trois cent quarante-trois sociétés correspondent à notre "
            "thèse. Mais sans signal clair, impossible de savoir qui appeler."),
    Segment(17.6, "Le moteur enrichit chaque société, écarte celles en procédure collective, et calcule "
                  "un score sur 100, critère par critère.",
            "Le moteur enrichit chaque société, écarte celles en procédure collective, et calcule un "
            "score sur cent, critère par critère."),
    Segment(26.3, "Résultat : 35 cibles qualifiées. Une liste courte, et défendable.",
            "Résultat : trente-cinq cibles qualifiées. Une liste courte, et défendable."),
    Segment(31.3, "Chaque point du score est expliqué : âge du dirigeant, taille, rentabilité, ancienneté. "
                  "Quand une donnée manque, le modèle le dit, au lieu de l'inventer."),
    Segment(42.6, "Pour chaque cible, un rapport de pré-due diligence : valeur indicative, montage LBO, "
                  "signaux d'alerte, et les questions à poser au cédant.",
            "Pour chaque cible, un rapport de pré-due diligence : valeur indicative, montage L.B.O., "
            "signaux d'alerte, et les questions à poser au cédant."),
    Segment(52.1, "Avec une recommandation claire : approcher, creuser, ou documenter."),
    Segment(56.6, "L'IA rédige le brouillon d'approche. Mais rien ne part sans relecture humaine.",
            "L'intelligence artificielle rédige le brouillon d'approche. Mais rien ne part sans "
            "relecture humaine."),
    Segment(68.0, "Tout le pipeline se pilote depuis un tableau de bord : filtres, indicateurs, suivi "
                  "des contacts."),
    Segment(78.3, "Score déterministe, données publiques, conformité RGPD : un outil conçu pour la "
                  "confiance.",
            "Score déterministe, données publiques, conformité R.G.P.D. : un outil conçu pour la "
            "confiance."),
    Segment(85.2, "pme-radar. Un radar d'origination pour search funds, en open source.",
            "P.M.E. radar. Un radar d'origination pour search funds, en open source."),
]  # fmt: skip


def slots(segments: list[Segment] = SEGMENTS, duration: float = DURATION) -> list[float]:
    """Durée disponible pour chaque segment (jusqu'au suivant, avec une respiration)."""
    ends = [s.start for s in segments[1:]] + [duration - 0.8]
    return [round(end - s.start - 0.25, 3) for s, end in zip(segments, ends, strict=True)]


def srt(entries: list[tuple[float, float, str]]) -> str:
    """Sous-titres SRT à partir de (début, fin, texte)."""

    def ts(x: float) -> str:
        ms = int(round(x * 1000))
        return (
            f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        )

    return "\n".join(
        f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n" for i, (a, b, text) in enumerate(entries, 1)
    )
