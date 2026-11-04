# PLAN — pme-radar

**Objectif** : moteur d'origination search fund (open data française) : sourcer → enrichir → noter →
préparer le contact → piloter l'entonnoir. Portfolio pour un poste d'analyste PE « Origination & IA ».

## Notes d'API (Phase 0)

> ⚠ **Le réseau de l'environnement de construction bloquait `recherche-entreprises.api.gouv.fr` et
> `bodacc-datadila.opendatasoft.com`** (proxy 403 / hôte non résolu). La documentation n'a donc **pas pu
> être lue en direct**. Les paramètres ci-dessous proviennent de ma connaissance de ces API et sont
> **à vérifier au premier run réel** (`pme-radar source` sans `--offline`). Le code est isolé dans
> `sources/` pour que la correction éventuelle tienne en quelques lignes (voir ADR-001).

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
| Débit | ≈ 7 requêtes/s annoncées → client limité à ~4 req/s par prudence, retry sur 429/5xx |
| Identité | `siren`, `nom_complet`, `nature_juridique`, `date_creation`, `categorie_entreprise` |
| Siège | `siege.{siret, code_postal, libelle_commune, departement, activite_principale}` |
| Dirigeants | `dirigeants[].{type_dirigeant, nom, prenoms, qualite, date_de_naissance (AAAA-MM), annee_de_naissance, denomination, siren}` |
| Finances | `finances` = `{ "2023": {"ca": int, "resultat_net": int}, … }` (absent/vidé si comptes confidentiels) |

### BODACC — Opendatasoft v2.1, dataset `annonces-commerciales` (sans clé)
`GET /api/explore/v2.1/catalog/datasets/annonces-commerciales/records` avec `where`, `limit`, `offset`.
Champs : `familleavis` (`collective` = procédures collectives), `typeavis`, `dateparution`, `commercant`,
`registre` (liste de SIREN au format « 123 456 789 »).

### Ratios BCE/INPI — optionnel, non implémenté en réseau (ADR-005).

## Phases
Voir « Avancement » ci-dessous.

## Avancement
- [x] Phase 0 — Cadrage (pyproject, config, CLI, PLAN)
- [x] Phase 1 — Sourcing (client, cache, fixtures, `source`)
- [x] Phase 2 — Enrichissement (modèles, dérivés, BODACC, `enrich`)
- [x] Phase 3 — Scoring explicable (`score`)
- [x] Phase 4 — Couche IA (LLMProvider, Mock, Anthropic, `draft`)
- [x] Phase 5 — Outreach, suivi, délivrabilité
- [ ] Phase 6 — Export, dashboard, `run`
- [ ] Phase 7 — Workflow n8n
- [ ] Phase 8 — Tests, CI, docs, README, memo, walkthrough
