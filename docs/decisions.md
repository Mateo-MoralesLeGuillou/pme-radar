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

## ADR-005 — Ratios BCE/INPI : EBE comme métrique de rentabilité principale
- **Implémenté** (`sources/inpi_ratios.py`, jeu `ratios_inpi_bce` de data.economie.gouv.fr, sans clé, interrogé
  par lots de 10 SIREN). Apporte `ebe`, `taux_d_endettement` et un historique pluriannuel.
- **Pourquoi l'EBE** : le résultat net dépend de la structure financière, de l'amortissement et d'éléments
  exceptionnels ; l'EBE est ce que l'acquéreur capitalise (et ce que les banques financent). Le score
  utilise la **marge d'EBE** si elle est disponible, **sinon la marge nette** (repli signalé dans le libellé).
- **Pièges constatés sur données réelles** : pour les bilans « partiellement confidentiels », le jeu met
  CA et EBE à **0** (valeur masquée, pas réelle) → ces lignes ne servent ni au CA ni à l'EBE
  (`inpi_ratios.usable`). L'API Recherche d'entreprises n'a qu'un exercice : l'historique INPI comble
  CA et CAGR. Les bilans de plus de 4 ans sont écartés (`MAX_RATIO_AGE`).
- **Effet mesuré (dép. 92, 314 sociétés notées)** : CA connu 40 % → 48 %, EBE connu pour 44 %, CAGR
  calculable pour 36 % (0 % avant). Les sociétés sans bilan public récent restent en repli sur la marge nette.
- Hors score : l'endettement (`debt_ratio`) est exporté et transmis au LLM, pas noté (à calibrer).
- Mode `--offline` : fixtures synthétiques `tests/fixtures/inpi_ratios.json` (`scripts/make_fixtures.py`).

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

## ADR-009 — Holding personnelle de fondateur vs vrai groupe
- **Contexte** : l'API ne donne pas l'arbre capitalistique. Pénaliser tout dirigeant personne morale
  (version initiale) écartait à tort les holdings patrimoniales de fondateurs, cibles typiques.
- **Décision** : si le dirigeant principal est une société, on interroge l'API Recherche d'entreprises
  sur son SIREN (`q=<SIREN>`, une requête par société grâce au cache et à une mémoïsation). Si elle est
  **NAF 64.20Z et dirigée par une personne physique** : holding personnelle → `is_owner_operator = True`,
  `director_age` = âge de cette personne, `holding_owner`/`holding_name` renseignés, pas de
  pénalité, et la personne devient l'interlocuteur du brouillon d'email. Sinon (autre NAF, holding
  dirigée par une société, société introuvable, pas de SIREN) : « vrai groupe », `is_owner_operator = False`,
  pénalité −10.
- **Limites** : un seul niveau de remontée (pas de holding de holding) ; une holding 64.20Z dirigée
  par une personne physique peut être un fonds ou une holding de groupe à gouvernance individuelle
  (faux négatif) ; une holding de fondateur d'un autre NAF reste pénalisée ; `q=<SIREN>` est le
  mode de recherche attendu de l'API mais **non vérifié en direct** (ADR-001). En cas d'échec de
  la recherche, on retombe sur le comportement prudent (pénalité), jamais sur un « oui » inventé.

## ADR-010 — Âge avec date de naissance partielle
- Mois connu : âge exact. Année seule : `année_réf − année_naissance` (± 1 an). Absent : `None`.

## ADR-011 — Seuil de qualification à 70
- Première version : 70, calibrée sur l'échantillon synthétique (volontairement favorable).
- Run réel (dép. 92, 314 sociétés non exclues), **avant EBE** : 70 ne qualifiait que 8,9 % de la
  population (65 : 11,8 %) car 60 % des sociétés n'avaient pas de CA exploitable.
- **Après EBE (ADR-005)** : 60 → 22,3 % · 65 → 17,8 % · **70 → 11,1 %** · 75 → 8,6 %. Le seuil **reste à 70**
  (cible : les 10-20 % supérieurs) ; l'abaissement à 65 envisagé avant l'EBE aurait été un artefact de
  données manquantes. Un seuil tenu ne doit pas compenser un manque de données.

## ADR-012 — Une requête par code NAF
- Contourne le plafond de résultats par requête de l'API et permet un cache fin. Déduplication par
  SIREN.

## ADR-013 — Taux de campagne rapportés aux emails délivrés
- Réponse et RDV = / (envoyés − rebonds). Rebond = / envoyés. En dessous de `min_sample` (20) les
  taux ne sont pas jugés : évite de conclure sur du bruit.
