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

## ADR-007 — `MockLLM` par défaut, provider Anthropic optionnel
- Le projet tourne sans clé. Le mock produit un JSON valide et déterministe à partir des faits.
- `AnthropicProvider` (identifiants dans `.env` ou profil `ant auth login`) n'a **pas été exécuté en
  réel** ; sa sortie passe par la même validation pydantic que le mock. Modèle par défaut
  `claude-opus-5-5` (audit du 2026-11-04), modifiable via `ANTHROPIC_MODEL`. `max_tokens` à 16 000 :
  la réflexion adaptative, active par défaut sur les modèles récents, consomme ce plafond.

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

## ADR-014 — Cache disque avec expiration (audit du 2026-11-04)
- **Contexte** : le cache n'expirait jamais. Le run hebdomadaire n8n relisait donc les réponses
  du premier run : ni nouvelles entreprises, ni nouvelles procédures collectives BODACC. Une
  société entrée en liquidation après le premier run n'aurait jamais été exclue.
- **Décision** : durée de validité de 6 jours par défaut (`PME_RADAR_CACHE_TTL_DAYS`), donc toujours
  inférieure à la cadence hebdomadaire ; `--refresh` force une relecture ; `0` rend le cache
  permanent (rejouer un run à l'identique). Écriture atomique (fichier temporaire puis
  renommage) ; un fichier corrompu est refait au lieu de faire échouer le run.
- **Conséquence** : le premier run de chaque semaine refait tous les appels (quota : ~2 req/s).

## ADR-015 — Lots d'analyses IA robustes et économes
- **Un échec n'arrête plus le lot** (réseau, quota, sortie invalide, refus du modèle) : la cible est
  listée en échec, les autres continuent ; code retour 1 seulement si aucune analyse n'est produite.
- **Réutilisation** : une analyse est réutilisée si l'empreinte (faits transmis + version du prompt
  + fournisseur) est identique au run précédent ; sinon nouvel appel. Sur un run hebdomadaire, seules
  les cibles nouvelles ou modifiées coûtent un appel. `--no-reuse` force la régénération.
- **`stop_reason` vérifié** avant de lire la réponse : `refusal` (classifieurs de sécurité) et
  `max_tokens` lèvent une erreur explicite **sans nouvel essai** (un essai identique serait refusé
  ou tronqué à nouveau, et facturé). Seule une sortie JSON invalide est retentée une fois.
- **Repli serveur** `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) sur les modèles
  qui l'acceptent ; `ANTHROPIC_FALLBACKS=off` le désactive. Limite : pour Claude Sonnet 5.5, le repli
  ne couvre que certaines catégories de refus.

## ADR-016 — Mention de conformité ajoutée hors LLM
- Chaque brouillon se termine par une mention fixe (`config/campaign.yaml` : `compliance_footer`) :
  source publique des coordonnées et droit d'opposition. Elle est ajoutée par le code, pas
  demandée au LLM : elle ne peut être ni oubliée ni reformulée. À adapter (identité de
  l'expéditeur) avant tout envoi ; ce n'est pas un avis juridique (`docs/rgpd.md`).

## ADR-017 — Configuration validée au chargement
- `thesis.yaml` et `scoring.yaml` sont validés avant chaque commande (`pme-radar check-config` pour
  le faire seul) : total de 100 points, paliers complets, pénalités négatives, codes NAF au format
  `43.21A` sans doublon, tranches d'effectif INSEE, multiples de valorisation cohérents. Toutes les
  erreurs sont listées d'un coup, avec un message lisible au lieu d'une trace Python.
- Les chemins par défaut (`config/…`, `tests/fixtures`) sont cherchés dans le dossier courant puis
  à la racine du dépôt : la CLI fonctionne lancée depuis n'importe quel dossier.


## ADR-018 — Score plancher, plafond et fiabilité
- **Contexte** : une donnée manquante vaut 0 point (ADR-004). C'est prudent, mais deux cibles à
  60/100 ne se valent pas si l'une est évaluée sur 100 % du barème et l'autre sur 60 %.
- **Décision** : le score officiel reste le **plancher** (seules les données disponibles rapportent
  des points). On y ajoute le **plafond** (score si chaque donnée manquante s'avérait favorable, la
  pénalité « comptes non disponibles » levée) et la **fiabilité** (part du barème évaluée sur des
  données réelles). Une cible sous le seuil dont le plafond l'atteint est marquée **à documenter** :
  un appel ou une liasse fiscale peut la qualifier.
- **Conséquence** : la qualification et l'entonnoir sont inchangés ; le rapport et le dashboard
  font apparaître les cibles à documenter au lieu de les laisser se perdre sous le seuil.

## ADR-019 — Pénalité d'endettement
- Au-delà de 150 % des capitaux propres (ratios BCE/INPI, `risk_thresholds.high_debt_ratio`), −5
  points (`penalties.high_debt`). La dette existante est refinancée à l'acquisition : elle réduit le
  prix des titres et la capacité d'endettement du repreneur. Les scores des sociétés très endettées
  baissent donc de 5 points par rapport aux runs précédents (à recalibrer sur le run réel si besoin).

## ADR-020 — Rapport de deal flow : signaux factuels, montage indicatif, recommandation
- **Signaux factuels** (`risks.py`) : règles déterministes sur les données (procédure, endettement,
  rentabilité faible, CA en baisse, déficit, comptes anciens, dépendance au dirigeant, holding,
  CA par salarié atypique…), chacune avec sa question de due diligence. Ils sont distincts des
  signaux de l'IA, présentés comme des **hypothèses à vérifier**, et transmis au LLM (prompt v2).
- **Montage indicatif** (`deal.py`) : valeur = EBE x 4 à 6 ; dette senior 2,5x l'EBE plafonnée à
  60 % du prix, crédit vendeur 10 %, le reste en fonds propres ; service annuel de la dette et
  couverture. Hypothèses dans `config/thesis.yaml` (`financing`). Ordre de grandeur, pas une
  évaluation : ni dette nette, ni BFR, ni EBE normalisé.
- **Recommandation** (règles, dans cet ordre) : écartée (procédure) ; à creuser (qualifiée mais
  signal fort, ou ticket de fonds propres au-delà de `max_equity_ticket`) ; à documenter (fiabilité
  sous 70 %, ou sous le seuil avec un plafond au-dessus) ; à approcher (qualifiée) ; sinon non
  prioritaire.
- **Ce qui n'entre pas dans la règle** : la couverture du service de la dette. Avec des hypothèses
  proportionnelles à l'EBE, elle est identique pour toutes les cibles (constat fait en testant) :
  elle ne mesure que les hypothèses. Elle est affichée, pas utilisée pour trier.
- **Rapport** (`report.py`) : HTML autonome imprimable en PDF ; les N meilleures cibles à approcher
  plus les cibles à creuser et à documenter. Il contient des données personnelles de dirigeants :
  il reste dans `data/`, seul l'exemple synthétique est versionné.

## ADR-021 — Voix off ElevenLabs optionnelle
- La vidéo se construit sans clé (musique synthétisée). Avec `ELEVENLABS_API_KEY`, la narration
  (`scripts/promo/motion/narration.py`) est synthétisée segment par segment, mise en cache
  (`data/cache/voice`, rien n'est repayé à la reconstruction), calée sur la timeline et mixée avec
  une baisse automatique de la musique sous la voix ; les sous-titres SRT sont produits au passage.
- La narration ne cite que des agrégats réels du run et des faits sur l'outil : aucun chiffre de
  marché, aucune donnée personnelle n'est envoyée à ElevenLabs.
- Non exécuté pendant la construction (clé absente et domaine inaccessible) : la chaîne est testée
  avec une API simulée et une fausse voix (décodage, accéléré, calage, mixage réels).

## ADR-022 — Rapport au format PE/M&A et dashboard orienté recherche
- **Rapport** : structure d'un mémo de pré-due diligence (page de garde, synthèse exécutive avec plan
  d'action, vue d'ensemble avec football field et répartition des qualifiées, un dossier par cible,
  méthodologie et avertissement). Montants en k€ au format comptable (négatifs entre parenthèses),
  tableaux à en-têtes répétés d'une page à l'autre, pieds de page « Strictement confidentiel » et
  pagination. La mise en page tient dans la largeur A4 : un tableau trop large faisait réduire
  toutes les pages à l'impression (page de garde à 79 %), constat fait sur le PDF.
- **Montage** : les emplois incluent des frais de transaction (4 % du prix, `transaction_fees`) ; les
  fonds propres = prix + frais − dette senior − crédit vendeur. Effet : une cible proche du ticket
  maximal (6 M€) passe « à creuser ». Sensibilité : multiples de la thèse ± 0,5x, EBE ± 10 et 20 %.
- **Plan de DD et demandes d'informations** : questions référencées par chantier (T.1, C.2…), en
  priorité haute quand un signal factuel de la cible les déclenche ; documents à demander dédoublonnés,
  les plus urgents d'abord. Points forts : règles factuelles (âge, taille, marge, croissance,
  ancienneté, cœur de thèse, endettement), jamais l'IA seule.
- **Dashboard** : la question de l'utilisateur est « où est l'information ? ». D'où une recherche
  globale (nom, ville, SIREN, dirigeant) en haut de chaque page, une fiche entreprise qui rassemble
  tout (onglets), une navigation en haut de page et une page Aide « je cherche… → où ». Pages en
  fichiers (`dashboard/views/`) pour être testables (`AppTest.switch_page`).
- **Lien direct** `?siren=` synchronisé à la main avec la sélection : l'option de persistance des
  widgets écrasait la valeur venue de l'URL (constat dans le navigateur), et le harnais de test ne
  simule pas la liaison automatique aux paramètres d'URL.
- **Données** : modèles complets (`analyzed.jsonl`) plutôt que le CSV exporté, pour afficher
  historique financier, dirigeants, signaux et montage. Dernier run local par défaut, échantillon
  synthétique sinon (`examples/sample_companies.jsonl`, `PME_RADAR_DATA=sample` pour le forcer).
- **Suivi depuis la fiche** (avec vos données) : même fonction que `pme-radar track` ; un contact pris
  hors brouillon est ajouté au suivi (campagne « manuel »). Toujours aucun envoi d'email.
- **Noms synthétiques uniques** : deux homonymes de l'échantillon se confondaient dans le rapport ; le
  générateur prend le nom suivant de la liste sans nouveau tirage, les autres données sont inchangées.
- **PDF direct** (`pdf.py`, `report --pdf`, boutons du dashboard) : impression par un Chrome, Chromium
  ou Edge déjà installé, sans dépendance Python ; la feuille de style fixe le format A4, les marges et
  les pieds de page. Sans navigateur, le HTML reste la sortie de référence. Deux pièges constatés :
  un `--user-data-dir` explicite bloque Chrome sans tête (le profil temporaire par défaut suffit), et
  des processus auxiliaires gardent ouverts les tubes de sortie (sorties redirigées vers des fichiers).

