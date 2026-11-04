# Décisions d'architecture (ADR courts)

Format : contexte → décision → conséquence.

## ADR-001 — API non lisibles à la construction : fixtures et mode `--offline`
- **Contexte** : le réseau de l'environnement de build bloquait `recherche-entreprises.api.gouv.fr`
  et `bodacc-datadila.opendatasoft.com`. La documentation n'a pas pu être consultée.
- **Décision** : ne rien contourner. Les paramètres sont ceux de `PLAN.md` (connaissance des API,
  **non vérifiée en direct**). Des fixtures synthétiques au format documenté alimentent `--offline`.
- **Conséquence** : la logique (pagination, parsing, scoring, export) est testée ; **le premier run
  réel peut révéler un nom de paramètre ou de champ à ajuster** — uniquement dans
  `sources/recherche_entreprises.py::build_params`, `sources/bodacc.py` et `enrich.parse_director`.

## ADR-002 — Codes NAF de la thèse
- **Décision** : 9 codes « cœur » (maintenance/réparation industrielle, installation électrique,
  thermique/CVC, sécurité, soutien aux bâtiments) et 4 « adjacents », classés dans `thesis.yaml`.
- **Limite** : libellés vérifiés de mémoire contre la NAF rév. 2, pas contre le référentiel INSEE en
  ligne (réseau bloqué). À revalider avant un run réel. La **NAF rév. 2.1 (2025)** doit entrer en
  vigueur début 2027 : prévoir un mapping de codes à ce moment-là.

## ADR-003 — Le score est déterministe ; le LLM ne le modifie jamais
- **Décision** : le score vient uniquement de `scoring.yaml` + données. Le LLM rédige mini-thèse,
  signaux d'alerte et brouillon. Un test garantit que `analysis` ne touche pas `score`.
- **Pourquoi** : auditabilité (« pourquoi 78/100 ? »), reproductibilité, absence de dérive du modèle,
  coût maîtrisé (LLM sur le top N seulement).

## ADR-004 — Donnée manquante ≠ zéro
- Comptes confidentiels, âge inconnu, dirigeant absent restent `None`. Le critère rapporte 0 point
  (affiché « n.d. ») et les comptes absents subissent une pénalité légère (−5), pas une exclusion :
  beaucoup de PME saines ne publient pas leurs comptes.

## ADR-005 — Ratios INPI/BCE non implémentés
- Jeu optionnel, non accessible à la construction. `sources/inpi_ratios.py` est un point d'extension
  documenté. EBE et endettement entreraient dans `scoring.yaml` (critère qualité) une fois branchés.

## ADR-006 — Aucun envoi d'email
- Le pipeline produit des brouillons marqués « À RELIRE ». Aucune dépendance SMTP. L'envoi, la
  relecture et la décision de contacter restent humains (éthique d'approche + RGPD).

## ADR-007 — `MockLLM` par défaut
- Le projet tourne sans clé. Le mock produit un JSON valide et déterministe à partir des faits.
  `AnthropicProvider` (clé dans `.env`) n'a **pas pu être exécuté en réel** ici ; sa sortie passe par
  la même validation pydantic que le mock. Modèle configurable via `ANTHROPIC_MODEL`.

## ADR-008 — Stockage : Parquet (brut) + JSONL (modèles)
- Brut : Parquet (SIREN + payload JSON) pour rejouer l'enrichissement sans rappeler l'API.
  Étapes suivantes : JSONL de modèles pydantic (structures imbriquées, relisible, diffable).

## ADR-009 — « Filiale de groupe » approchée par le dirigeant personne morale
- L'API ne donne pas l'arbre capitalistique. Proxy : le dirigeant principal est une personne morale
  → `is_owner_operator = False`, pénalité −10. **Limite** : une holding personnelle du fondateur est
  aussi pénalisée à tort (faux positif connu, à raffiner avec les bénéficiaires effectifs).

## ADR-010 — Âge avec date de naissance partielle
- Mois connu : âge exact. Année seule : `année_réf − année_naissance` (± 1 an). Absent : `None`.

## ADR-011 — Seuil de qualification à 70
- Calibré sur l'échantillon synthétique (≈ 45 % de qualifiées avec 70, 62 % avec 60 : trop large).
  À recalibrer sur un vrai run : viser les 10-20 % supérieurs de la population sourcée.

## ADR-012 — Une requête par code NAF
- Contourne le plafond de résultats par requête de l'API et permet un cache fin. Déduplication par
  SIREN.

## ADR-013 — Taux de campagne rapportés aux emails délivrés
- Réponse et RDV = / (envoyés − rebonds). Rebond = / envoyés. En dessous de `min_sample` (20) les
  taux ne sont pas jugés : évite de conclure sur du bruit.
