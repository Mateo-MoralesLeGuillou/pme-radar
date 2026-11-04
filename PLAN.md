# PLAN — pme-radar

**Objectif** : moteur d'origination search fund (open data française) : sourcer → enrichir → noter →
préparer le contact → piloter l'entonnoir. Portfolio pour un poste d'analyste PE « Origination & IA ».

## Notes d'API (Phase 0)

> ✅ **Vérifié en réel le 2026-11-04** (run limité au département 92) : tous les paramètres et champs
> ci-dessous sont confirmés tels quels. Corrections issues du run : (1) l'API de recherche répond par
> une **redirection 302 vers `sorry.data.gouv.fr`** quand le quota est dépassé → traitée comme un
> statut réessayable, intervalle entre appels porté à 0,5 s ; (2) `finances` renvoie **`ca: 0` quand le
> CA n'est pas publié** (≈ 50 % des sociétés avec comptes) → 0 est lu comme « non publié » (None) ;
> (3) `finances` ne contient **qu'un seul exercice** → le CAGR du CA n'est pas calculable depuis cette
> seule source. L'API expose aussi `activite_principale_naf25` (NAF 2025, applicable au 01/01/2027).

### Recherche d'entreprises — `GET https://recherche-entreprises.api.gouv.fr/search` (sans clé)
| Besoin | Paramètre / champ utilisé |
|---|---|
| Pagination | `page` (1..), `per_page` (≤ 25), réponse : `total_results`, `total_pages`, `results` |
| Filtre NAF | `activite_principale` (ex. `43.21A`, liste séparée par virgules) |
| Effectif | `tranche_effectif_salarie` (codes INSEE `11,12,21,22,31`) |
| Catégorie | `categorie_entreprise` (`PME`, `ETI`, `GE`) |
| Zone | `departement` (liste) / `region` |
| État | `etat_administratif` (`A` active) |
| CA (optionnel) | `ca_min`, `ca_max` |
| Débit | ≈ 7 requêtes/s annoncées ; le quota réel se déclenche plus tôt → client à 2 req/s, retry sur 429/302/5xx |
| Identité | `siren`, `nom_complet`, `nature_juridique`, `date_creation`, `categorie_entreprise` |
| Siège | `siege.{siret, code_postal, libelle_commune, departement, activite_principale}` |
| Dirigeants | `dirigeants[].{type_dirigeant, nom, prenoms, qualite, date_de_naissance (AAAA-MM), annee_de_naissance, denomination, siren}` |
| Finances | `finances` = `{ "2023": {"ca": int, "resultat_net": int}, … }` (absent/vidé si comptes confidentiels) |

### BODACC — Opendatasoft v2.1, dataset `annonces-commerciales` (sans clé)
`GET /api/explore/v2.1/catalog/datasets/annonces-commerciales/records` avec `where`, `limit`, `offset`.
Champs : `familleavis` (`collective` = procédures collectives), `typeavis`, `dateparution`, `commercant`,
`registre` (liste de SIREN au format « 123 456 789 »).

### Ratios BCE/INPI — `GET https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/ratios_inpi_bce/records` (sans clé) ✅
Opendatasoft v2.1 : `where=siren IN ("…")`, `order_by`, `limit` ≤ 100, `offset`. Champs : `siren`,
`date_cloture_exercice`, `chiffre_d_affaires`, `ebe`, `resultat_net`, `taux_d_endettement`, `marge_ebe`,
`confidentiality`. Bilans « partiellement confidentiels » : CA et EBE masqués à 0 (ADR-005).

## Phases
Voir « Avancement » ci-dessous.

## Avancement
- [x] Phase 0 — Cadrage (pyproject, config, CLI, PLAN)
- [x] Phase 1 — Sourcing (client, cache, fixtures, `source`)
- [x] Phase 2 — Enrichissement (modèles, dérivés, BODACC, `enrich`)
- [x] Phase 3 — Scoring explicable (`score`)
- [x] Phase 4 — Couche IA (LLMProvider, Mock, Anthropic, `draft`)
- [x] Phase 5 — Outreach, suivi, délivrabilité
- [x] Phase 6 — Export, dashboard, `run`
- [x] Phase 7 — Workflow n8n
- [x] Phase 8 — Tests, CI, docs, README, memo, walkthrough
- [x] Phase 9 — CI vérifiée (Python 3.11 et 3.12 : ruff + pytest + run offline)
- [x] Phase 10 — Run réel dép. 92 : API, BODACC, holdings, NAF validés ; corrections 302 et `ca: 0`
- [x] Phase 11 — EBE via ratios BCE/INPI (ADR-005), repli marge nette
- [x] Phase 12 — `pme-radar onepager` + exemple synthétique
- [x] Phase 13 — Captures dashboard (`docs/img/`), licence MIT
- [ ] Run réel sur les 7 autres départements IDF ; utiliser le NAF 2025 ; noter l'endettement
- [ ] Provider Anthropic, Google Sheets, n8n : premier run réel

## Audit du 2026-11-04
Détail : [`docs/audit.md`](docs/audit.md). 18 constats corrigés, 7 recommandations ouvertes.
- [x] Cache avec expiration + `--refresh` (constat critique : run hebdomadaire aveugle)
- [x] Lots IA robustes : échec isolé, réutilisation des analyses, `stop_reason` vérifié, repli serveur
- [x] Configuration validée et résolue hors du dépôt (`check-config`)
- [x] Données aberrantes (âge, ancienneté, dates INPI) et mention de conformité des brouillons
- [x] Délivrabilité (SPF `redirect=`, DMARC multiples), export Sheets, dashboard (filtres, export)
- [x] Qualité : mypy à 0 erreur, formatage, CI 3.11-3.13, documentation et vidéo à jour
- [ ] NAF 2025 avant le 01/01/2027 (recommandation n° 1)
- [ ] BODACC : filtrer les procédures anciennes ou clôturées (recommandation n° 2)

