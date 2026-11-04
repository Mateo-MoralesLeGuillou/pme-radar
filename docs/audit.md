# Audit du 2026-11-04

Revue complète du code, de la configuration, des tests, de la CI et de la documentation après le
run réel (dép. 92), l'ajout des ratios INPI et du one-pager. Objectif : fiabilité d'un run
**hebdomadaire sans surveillance** (n8n), coût de la couche IA, conformité des brouillons,
lisibilité pour un repreneur du projet.

**Bilan** : 18 constats corrigés, 7 recommandations laissées ouvertes (fin de page).
Tests : 98 → 131 · couverture 95 % · mypy : 20 erreurs → 0 · CI : Python 3.11 à 3.13.

## Constats corrigés

| # | Gravité | Constat | Correctif | Preuve (test) |
|---|---|---|---|---|
| 1 | **Critique** | Le cache disque n'expirait jamais : le run hebdomadaire relisait les réponses du premier run, donc **aucune nouvelle entreprise ni nouvelle procédure collective BODACC** n'était vue. Une société entrée en liquidation restait « qualifiée ». | Expiration à 6 jours (`PME_RADAR_CACHE_TTL_DAYS`), `--refresh`, écriture atomique, fichier corrompu refait (ADR-014). | `test_cache_expires_after_ttl`, `test_refresh_bypasses_cache_and_rewrites_it`, `test_corrupted_cache_file_is_refetched` |
| 2 | Élevée | Un seul échec LLM (réseau, quota, JSON invalide) **interrompait tout `draft`**, donc tout `run` : plus d'export, plus de digest n8n. | Échec isolé par cible, bilan affiché, code retour 1 seulement si rien n'est produit (ADR-015). | `test_one_failure_does_not_stop_the_batch`, `test_cli_draft_exits_1_when_every_analysis_fails` |
| 3 | Élevée | Provider Anthropic : `max_tokens=1200` alors que la réflexion adaptative (active par défaut sur les modèles récents) consomme ce plafond → JSON possiblement coupé ; un refus des classifieurs n'était pas détecté et déclenchait un nouvel essai payant voué à l'échec. | `max_tokens` 16 000, `stop_reason` vérifié (`refusal`, `max_tokens`) sans nouvel essai, repli serveur `fallbacks: "default"` (ADR-015). | `test_anthropic_refusal_is_not_retried`, `test_anthropic_truncated_answer_is_explicit`, `test_anthropic_request_shape_and_text_extraction` |
| 4 | Élevée | Chaque run régénérait toutes les analyses IA, même inchangées : coût récurrent inutile en hebdomadaire. | Réutilisation si faits + version de prompt + fournisseur identiques ; `--no-reuse` pour forcer. | `test_unchanged_facts_reuse_previous_analysis` |
| 5 | Élevée | La CLI cherchait `config/` et `tests/fixtures/` dans le **dossier courant** : lancée depuis un autre dossier (cron, script), elle échouait. | Repli sur la racine du dépôt (ADR-017). | `test_resolve_falls_back_to_project_root` |
| 6 | Élevée | Configuration non validée : une faute de frappe dans `scoring.yaml` (total ≠ 100, palier sans `points`, pénalité positive) produisait des scores faux **sans erreur**. | Validation au chargement, toutes les erreurs listées, commande `check-config` (ADR-017). | `test_scoring_total_must_be_100`, `test_scoring_reports_all_problems`, `test_thesis_validation` |
| 7 | Moyenne | Données aberrantes acceptées : dirigeant de 126 ans ou de 11 ans (erreur de saisie) noté comme une cible en transmission ; date de création future → ancienneté négative ; ancienneté calculée à l'année civile (jusqu'à +1 an). | Âge hors 18-100 ans = manquant ; date future = manquante ; ancienneté en années révolues. | `test_implausible_director_age_is_missing`, `test_company_age_exact_and_future_dates` |
| 8 | Moyenne | Ratios INPI : une date de clôture absente faisait planter `enrich` ; l'EBE « le plus récent » dépendait de l'ordre renvoyé par l'API. | Dates illisibles ignorées, tri explicite. | `test_ratios_sorted_and_bad_dates_ignored` |
| 9 | Moyenne | Les brouillons ne mentionnaient ni la source des coordonnées ni le droit d'opposition (information RGPD au premier contact). | Mention fixe ajoutée par le code, hors LLM (ADR-016). | `test_compliance_footer_is_appended_to_every_draft` |
| 10 | Moyenne | Délivrabilité : un SPF valide en `redirect=` était signalé ❌ (verdict « NON PRÊT » à tort) ; plusieurs enregistrements DMARC (ignorés par les destinataires) passaient inaperçus ; balises DMARC sensibles à la casse. | Les trois cas traités. | `test_spf_redirect_is_valid`, `test_multiple_dmarc_records_fail_and_tags_case_insensitive` |
| 11 | Moyenne | Export Sheets : `except Exception` traitait une erreur d'accès (classeur non partagé, quota) comme un onglet absent, puis tentait d'en créer un. | Seule l'exception « onglet absent » crée un onglet ; les autres remontent. | `test_sheets_auth_errors_are_not_swallowed` |
| 12 | Moyenne | Filtre de ton par sous-chaîne : « je ne peux rien garantir » était rejeté (nouvel essai payant). | Mots entiers et leurs accords. | `test_forbidden_words_match_whole_words_only` |
| 13 | Moyenne | Provider Anthropic : un profil `ant auth login` était refusé (seule `ANTHROPIC_API_KEY` acceptée). | Toutes les sources d'identifiants du SDK reconnues. | `test_anthropic_accepts_cli_profile` |
| 14 | Moyenne | Dashboard : deux homonymes se confondaient dans le détail du score ; ni filtres ni export ; montants bruts. | Sélection « nom · SIREN », filtres département/NAF/score/comptes, export CSV, CA en M€. | `test_dashboard_filters_and_empty_selection` |
| 15 | Moyenne | Documentation périmée : l'exemple de score du README et la citation de la vidéo dataient d'avant l'EBE (« 100/100… »). | README et vidéo régénérés sur l'échantillon actuel. | relecture |
| 16 | Faible | 20 erreurs mypy (valeurs optionnelles non gardées), 13 fichiers non formatés, CI sans typage ni Python 3.13. | Code typé et formaté ; CI : `ruff format --check`, `mypy src`, `check-config`, 3.11-3.13. | CI |
| 17 | Faible | Erreurs utilisateur affichées en traces Python (étape manquante, statut ou date invalides). | Messages clairs, code retour 1. | `test_version_and_track_with_date` |
| 18 | Faible | Ni `--version`, ni date rétroactive pour `track`, ni progression pendant un run réel de plusieurs minutes. | `--version`, `track --date`, progression par code NAF et compte d'appels réseau / cache. | `test_version_and_track_with_date` |

## Recommandations ouvertes (par ordre d'impact)

1. **NAF 2025 avant le 01/01/2027** : la nomenclature change dans moins de deux mois. Ajouter dans
   `thesis.yaml` les codes NAF 2025 équivalents et filtrer sur le champ correspondant de l'API.
   Non fait ici : les correspondances doivent être vérifiées sur la table officielle de l'INSEE,
   inaccessible depuis cet environnement.
2. **BODACC trop large** : toute annonce de la famille « collective » exclut, même ancienne ou
   clôturée (plan de continuation réussi). Filtrer par date et par type de jugement demande de
   vérifier sur données réelles le contenu du champ `jugement`.
3. **Exécuter en réel** le provider Anthropic, l'export Google Sheets et le workflow n8n : ils sont
   testés avec des doublures, jamais contre les vrais services.
4. **Endettement INPI dans le score** : collecté (`debt_ratio`) et affiché dans le one-pager, mais
   non noté. À intégrer quand les seuils auront été posés sur le run réel.
5. **Purge RGPD** : la durée de conservation est documentée (`docs/rgpd.md`) mais pas appliquée par
   une commande.
6. **Runs concurrents** : deux runs simultanés (n8n + manuel) écriraient les mêmes fichiers de
   `data/`. Un verrou de fichier simple suffirait.
7. **Pondérations apprises** : recalibrer le score sur les RDV obtenus dès qu'il y aura une
   cinquantaine de contacts suivis.
