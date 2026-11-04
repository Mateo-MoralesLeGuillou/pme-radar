<p align="center"><img src="docs/img/banner.png" alt="pme-radar : moteur d'origination open source pour search funds" width="100%"></p>

<p align="center">
  <a href="https://github.com/Mateo-MoralesLeGuillou/pme-radar/actions/workflows/ci.yml"><img src="https://github.com/Mateo-MoralesLeGuillou/pme-radar/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-25c2f5" alt="Python 3.11 à 3.13">
  <img src="https://img.shields.io/badge/typage-mypy-1f5f8b" alt="Typage mypy">
  <img src="https://img.shields.io/badge/style-ruff-d7ff64" alt="Ruff">
  <img src="https://img.shields.io/badge/licence-MIT-9aa0c8" alt="Licence MIT">
</p>

<p align="center">
  <img src="docs/img/demo.gif" alt="Animation : les 343 sociétés du run réel traversent le pipeline, 29 sont exclues, 35 qualifiées" width="860">
  <br>
  <b><a href="docs/video/pme-radar-promo.mp4">🎬 Vidéo de présentation (91 s, avec son)</a></b>
  · <b><a href="examples/rapport_deal_flow_sample.pdf">📄 Exemple de rapport de pré-due diligence (PDF)</a></b>
  · générée par <code>scripts/promo/build_video.sh</code>
</p>

> **Moteur d'origination open source pour search fund français** : il transforme l'open data en une
> liste courte de PME transmissibles, notées de façon explicable, avec brouillon d'approche et
> pilotage de l'entonnoir.

- **Source** les PME d'une thèse (NAF, zone, taille) via l'API Recherche d'entreprises, avec cache et respect des limites de débit.
- **Qualifie** par un score /100 déterministe, détaillé critère par critère, avec sa fourchette (plafond si les données manquantes sont favorables) et sa fiabilité ; exclut les procédures collectives (BODACC).
- **Évalue** chaque cible dans un **rapport de pré-due diligence** au format private equity : synthèse exécutive, football field des valorisations, puis par cible thèse d'investissement, points de vigilance, financiers, sensibilité de la valeur, emplois et ressources du montage LBO, plan de DD référencé, demandes d'informations priorisées et recommandation argumentée (approcher, creuser, documenter).
- **Se consulte** dans un dashboard pensé comme un terminal financier : une barre de recherche (nom, ville, SIREN, dirigeant) ouvre la fiche complète de n'importe quelle entreprise.
- **Prépare** mini-thèse, signaux d'alerte et brouillon d'email par IA générative, **sans jamais toucher au score ni envoyer d'email**.
- **Pilote** l'entonnoir (identifiées → qualifiées → contactées → RDV), la délivrabilité (SPF/DKIM/DMARC) et l'export Sheets/n8n.

> ✅ **Statut honnête** : le pipeline a été **exécuté en réel** le 2026-11-04 sur le département 92
> (API Recherche d'entreprises, BODACC, ratios BCE/INPI) ; les paramètres et champs sont confirmés (voir
> [`PLAN.md`](PLAN.md)). **Non exécutés en réel** : provider Anthropic, Google Sheets, workflow n8n.
> Le mode `--offline` (fixtures synthétiques) reste la référence des tests et de la CI.

<table>
  <tr>
    <td width="50%"><img src="docs/img/dashboard-accueil.png" alt="Accueil du dashboard"><br><sub><b>Accueil</b> · la situation en une phrase, chiffres clés, actions du jour (à approcher, réponses et relances, à documenter)</sub></td>
    <td width="50%"><img src="docs/img/dashboard-recherche.png" alt="Recherche globale"><br><sub><b>Recherche</b> · quelques lettres d'un nom, d'une ville, d'un SIREN ou d'un dirigeant, et la fiche s'ouvre</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/img/dashboard-fiche.png" alt="Fiche entreprise"><br><sub><b>Fiche entreprise</b> · recommandation, score, chiffres clés, pourquoi / points forts / vigilance, puis onglets</sub></td>
    <td width="50%"><img src="docs/img/dashboard-valorisation.png" alt="Valorisation"><br><sub><b>Valorisation</b> · fourchette, sensibilité EBE × multiple, emplois et ressources, couverture</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/img/dashboard-contacts.png" alt="Prises de contact"><br><sub><b>Prises de contact</b> · taux et alertes, relances dues, pipeline par statut</sub></td>
    <td width="50%"><a href="examples/rapport_deal_flow_sample.pdf"><img src="docs/img/rapport-apercu.png" alt="Rapport de pré-due diligence"></a><br><sub><b>Rapport de pré-due diligence</b> · page de garde, synthèse exécutive, dossier par cible (PDF)</sub></td>
  </tr>
</table>

*Captures du dashboard sur l'échantillon **synthétique** (`examples/`) : aucune donnée réelle.*

## Run réel (département 92, 2026-11-04) — chiffres agrégés

Run limité aux Hauts-de-Seine, 13 codes NAF, tranches d'effectif 10-249. Aucune donnée nominative n'est
versionnée (`data/` ignoré). Distinct de l'échantillon synthétique ci-dessous.

| Étape | Nombre |
|---|---:|
| Sociétés sourcées (API Recherche d'entreprises) | 343 |
| Exclues (procédure collective BODACC) | 29 |
| Notées | 314 |
| Qualifiées (score ≥ 70) | 35 (11,1 %) |

Distribution des scores (hors exclues), médiane 41/100 : 0-29 : 85 · 30-49 : 112 · 50-69 : 82 · 70-100 : 35.
Couverture des données : CA connu pour 48 % des sociétés, EBE pour 44 %, CAGR pour 36 % (sans les ratios
INPI : CA 40 %, EBE 0 %, CAGR 0 %). 29 holdings personnelles résolues via ADR-009. Seuil de 70 conservé :
voir ADR-011.

## Résultat d'un run type (échantillon synthétique, `--offline`)

| Étape | Nombre | Conversion vs étape précédente |
|---|---:|---:|
| Identifiées | 45 | — |
| Qualifiées (score ≥ 70) | 27 | 60 % |
| Contactées | 14 | 52 % |
| Ont répondu | 6 | 43 % |
| RDV | 1 | 17 % |

3 entreprises exclues automatiquement (procédure collective). Les étapes « contactées » et au-delà
viennent d'un suivi de campagne **fictif** (`examples/sample_campaign.csv`) ; les 14 envois sont sous
le seuil de 20 : les taux ne sont pas jugés. Exemple de ligne : *« 95/100 : dirigeant 64 ans, CA
8,5 M€, marge d'EBE 12 %, 33 ans d'ancienneté. »*

## Architecture

```mermaid
flowchart LR
    A[Recherche d'entreprises<br/>+ BODACC] --> B[source]
    B --> C[enrich]
    C --> D[score<br/>déterministe]
    D --> E[draft<br/>LLM ou Mock]
    E --> F[outreach<br/>brouillons à relire]
    D --> G[export CSV / Sheets]
    F --> G
    G --> H[Dashboard Streamlit]
    F --> I[Délivrabilité + KPI]
    J[n8n hebdo] -.-> B
    J -.-> G
```
Détail : [`docs/architecture.md`](docs/architecture.md).

## Démarrage rapide (sans aucune clé)

```bash
pip install -e ".[all]"
pme-radar run --offline
streamlit run dashboard/app.py
```

Le dashboard s'ouvre sur votre dernier run (`data/`) ou, à défaut, sur l'échantillon synthétique
(`examples/sample_companies.jsonl`) ; un bouton de l'en-tête bascule entre les deux.

## Le dashboard : trouver une information sans chercher
| Je cherche… | Où |
|---|---|
| Une entreprise précise | Barre de recherche en haut de chaque page (nom, ville, SIREN, dirigeant) ; lien direct `…/entreprise?siren=<SIREN>` |
| Quoi faire aujourd'hui | **Accueil** › À faire maintenant : cibles prêtes, réponses à traiter, relances dues, cibles à documenter |
| Pourquoi ce score, combien elle vaut, quoi demander | **Fiche entreprise** › onglets Score, Valorisation, Due diligence |
| Le brouillon d'email | **Fiche entreprise** › Contact : à copier et relire ; avec vos données, le statut se met à jour ici |
| Comparer, filtrer, exporter | **Cibles** : sélections rapides, filtres, tri, bouton « Ouvrir », Excel, rapport d'une sélection |
| Un document à partager | **Rapports** : rapport complet ou dossier d'une entreprise, en PDF ou HTML ; chaque fiche a aussi son onglet Documents |
| Un terme (EBE, plafond, couverture…) | **Aide** : glossaire cherchable et questions fréquentes |

## Méthodologie de scoring
100 points : **Transmission 40** (âge du dirigeant, dirigeant-exploitant, pas de successeur) · **Taille 25**
(CA, effectif) · **Qualité 20** (marge d'EBE, repli marge nette ; régularité du CA, ancienneté) · **Thèse 15** (NAF cœur/adjacent),
moins pénalités (dirigeant personne morale −10, comptes absents −5). Procédure collective = exclusion.
Une donnée manquante n'est jamais un zéro : 0 point + mention « n.d. ». Détail et limites :
[`docs/scoring_methodology.md`](docs/scoring_methodology.md).

## Configuration

| Fichier | Rôle |
|---|---|
| `config/thesis.yaml` | NAF (cœur/adjacent), tranches d'effectif, départements, état |
| `config/scoring.yaml` | Barèmes, seuil de qualification, nombre de cibles passées à l'IA |
| `config/campaign.yaml` | Seuils d'alerte rebonds / réponses / RDV, mention de conformité ajoutée à chaque brouillon |
| `.env` (copie de `.env.example`) | **Optionnel** : `ANTHROPIC_API_KEY` (ou profil `ant auth login`), `ANTHROPIC_MODEL`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_SHEET_ID`, `PME_RADAR_CACHE_TTL_DAYS`, `PME_RADAR_DATA_DIR` et `PME_RADAR_BROWSER` (dashboard, PDF) |

Les deux YAML sont **validés à chaque commande** (total de 100 points, codes NAF, paliers) :
`pme-radar check-config` le fait seul. Le cache des API expire après 6 jours, pour qu'un run
hebdomadaire voie les nouvelles entreprises et procédures ; `--refresh` force une relecture.

| Commande | Rôle |
|---|---|
| `run [--offline] [--llm mock\|anthropic] [--refresh]` | Enchaîne source → enrich → score → draft → export |
| `source`, `enrich`, `score`, `draft`, `export` | Les étapes une à une (reprise possible après chacune) |
| `onepager [--siren … \| --top-n …]` | Fiche cible + fourchette de valorisation ([exemple](examples/onepager_sample.md)) |
| `track <SIREN> <statut> [--date AAAA-MM-JJ]` | Suivi manuel : contacted, replied, meeting, declined, bounced |
| `deliverability --domain … [--selector …]` | Audit SPF / DKIM / DMARC / MX + KPI de campagne |
| `report [--top-n N] [--siren …] [--pdf]` | Rapport de pré-due diligence (mémo PE) : synthèse exécutive + dossier par cible, en HTML et, avec `--pdf`, en PDF A4 (Chrome, Chromium ou Edge installé) ([exemple PDF](examples/rapport_deal_flow_sample.pdf), [HTML](examples/rapport_deal_flow_sample.html)) |
| `check-config`, `--version` | Validation de la configuration, version |

`draft` réutilise les analyses dont les faits n'ont pas changé (aucun nouvel appel LLM) et
continue si une cible échoue ; le bilan généré / réutilisé / échecs s'affiche à la fin.

## Conformité RGPD et éthique d'approche
`data/` non versionné, échantillon synthétique, minimisation des données envoyées au LLM, **aucun envoi
automatique** : seulement des brouillons « À RELIRE », un droit d'opposition tracé, un ton respectueux
sans pression ni prix. Voir [`docs/rgpd.md`](docs/rgpd.md) (pas un avis juridique).

## Limites connues
- **Testé en réel sur un seul département (92)** ; les 7 autres départements d'Île-de-France n'ont pas été
  lancés. Le quota de l'API Recherche d'entreprises (redirection 302 « sorry ») impose 2 req/s.
- **Données financières partielles** : ~50 % des sociétés ne publient pas leur CA (`ca: 0`), l'API ne
  fournit qu'un exercice ; l'historique et l'EBE viennent du jeu INPI, parfois ancien (bilans > 4 ans
  écartés) et masqué pour les bilans confidentiels. Sans EBE : repli sur la marge nette.
- **Valorisation et montage** : EBE × multiples et structure de financement configurables, purs ordres de
  grandeur pour décider d'un appel (ni dette nette, ni BFR, ni EBE normalisé). La couverture de la dette
  dépend des hypothèses, pas de la cible : elle est affichée, jamais utilisée pour trier (ADR-020).
- **Holdings** : une holding de fondateur d'un autre NAF que 64.20Z reste pénalisée comme « groupe » (ADR-009) ;
  sur le run réel, 58 sociétés dirigées par une société non-holding à dirigeant personne physique sont dans ce cas.
- Procédures collectives BODACC : toute annonce de famille « collective » exclut, y compris ancienne ou clôturée.
- **NAF 2025 applicable au 01/01/2027** : l'API expose `activite_principale_naf25`, non encore utilisée.
  Les correspondances de codes sont à vérifier sur la table INSEE avant cette date (recommandation n° 1 de
  [l'audit](docs/audit.md)).
- Provider Anthropic, Google Sheets, workflow n8n et voix off ElevenLabs non exécutés en réel (chaîne voix
  testée avec une API simulée). Pondérations non apprises.

## Feuille de route
Scraping des sites web des cibles (taille réelle, clients, offres d'emploi) · détection de signaux de
cession (annonces légales, ventes d'actifs, changement de dirigeant) · intégration CRM · scoring appris
sur les RDV obtenus · endettement INPI dans le score · bénéficiaires effectifs pour mieux détecter les groupes.

## Documentation
[Runbook (reprise en 30 min + warm-up)](docs/runbook.md) · [Walkthrough pédagogique + 10 questions d'entretien](docs/walkthrough.md) ·
[Décisions](docs/decisions.md) · [Audit du 2026-11-04](docs/audit.md) · [Memo sectoriel](memo/memo_sectoriel.md) · [n8n](n8n/README.md) · [Plan](PLAN.md)

## Méthode
Projet construit en développement assisté par IA (Claude Code), **conçu, piloté et vérifié par
l'auteur** : cadrage de la thèse et du scoring, choix d'architecture consignés en ADR, relecture du code
et des tests, et signalement explicite de ce qui n'a pas pu être vérifié.
