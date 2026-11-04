"""LLM factice déterministe : utilisé par défaut et dans les tests (aucune clé, aucun coût)."""

from __future__ import annotations

import json

from .base import LLMProvider
from .prompts import FACTS_CLOSE, FACTS_OPEN


class MockLLM(LLMProvider):
    name = "mock"

    def complete(self, system: str, user: str) -> str:
        facts = json.loads(user.split(FACTS_OPEN)[1].split(FACTS_CLOSE)[0])
        rev = facts.get("revenue_last")
        rev_txt = f"{rev / 1e6:.1f} M€ de CA".replace(".", ",") if rev else "un CA non publié"
        age = facts.get("director_age")
        who = facts.get("director_name") or "Madame, Monsieur"
        flags = []
        if not facts.get("accounts_available"):
            flags.append("Comptes non publiés : situation financière à vérifier.")
        if facts.get("n_natural_directors") == 1:
            flags.append("Activité possiblement liée à la personne du dirigeant unique.")
        flags.append("Dépendance client et cyclicité à vérifier lors d'un premier échange.")
        body = (
            f"Bonjour {who},\n\n"
            f"Je dirige une démarche de reprise d'entreprise et je me permets de vous écrire à "
            f"propos de {facts['name']}, que je suis depuis quelque temps. Je recherche une PME "
            f"de services techniques à reprendre et à développer sur le long terme, en préservant "
            f"l'équipe en place et l'identité de l'entreprise.\n\n"
            f"Si la question de la transmission fait un jour partie de vos réflexions, je serais "
            f"heureux d'échanger quelques minutes, sans engagement, pour comprendre votre "
            f"projet et vos priorités. Si ce n'est pas le cas, je l'entends parfaitement et vous "
            f"remercie de m'avoir lu.\n\nCordialement,\n[Prénom Nom]"
        )
        return json.dumps(
            {
                "mini_thesis": [
                    f"Entreprise de {facts.get('company_age_years') or '?'} ans dans un secteur de "
                    f"services techniques récurrents ({facts.get('naf_label') or 'NAF n.d.'}).",
                    f"Taille cohérente avec une reprise par un searcher : {rev_txt}.",
                    (
                        f"Dirigeant de {age} ans : fenêtre de transmission plausible."
                        if age
                        else "Âge du dirigeant inconnu : calendrier de transmission à confirmer."
                    ),
                ],
                "red_flags": flags,
                "email_subject": "Transmission et continuité de votre entreprise",
                "email_body": body,
            },
            ensure_ascii=False,
        )
