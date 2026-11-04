# Méthodologie de scoring « search fund fit »

Score sur **100 points**, entièrement piloté par `config/scoring.yaml`. Chaque cible reçoit un
`ScoreBreakdown` : points par critère, détail de la valeur, et une phrase de synthèse.

| Bloc | Critère | Pts | Logique |
|---|---|---|---|
| **Transmission (40)** | Âge du dirigeant | 25 | Paliers : ≥ 65 ans : 25 ; ≥ 60 : 22 ; ≥ 58 : 18 ; ≥ 55 : 10 ; ≥ 50 : 4 |
| | Dirigeant-exploitant | 10 | Dirigeant principal = personne physique, ou holding personnelle d'une personne physique (ADR-009) |
| | Pas de successeur évident | 5 | Un seul dirigeant personne physique identifié |
| **Taille (25)** | Chiffre d'affaires | 15 | 5-20 M€ : 15 ; 3-30 M€ : 11 ; 1,5-40 M€ : 5 |
| | Effectif | 10 | Tranches INSEE : 20-99 salariés = optimum |
| **Qualité (20)** | Marge nette | 8 | ≥ 8 % : 8 ; ≥ 5 % : 6 ; ≥ 3 % : 4 ; ≥ 0 : 2 |
| | CAGR du CA | 6 | Régularité : ≥ 5 % : 6 ; ≥ 0 : 4 ; ≥ −5 % : 2 |
| | Ancienneté | 6 | ≥ 20 ans : 6 ; ≥ 10 : 4 ; ≥ 5 : 2 |
| **Thèse (15)** | Secteur | 15 | NAF « cœur » : 15 ; « adjacent » : 8 |
| **Pénalités** | Dirigeant personne morale (vrai groupe) | −10 | Société dirigeante qui n'est pas une holding personnelle (ADR-009) |
| | Comptes absents/confidentiels | −5 | Légère, jamais d'exclusion |
| | Endettement élevé | −5 | Dettes > 150 % des capitaux propres (ADR-019) |
| **Exclusion** | Procédure collective BODACC | — | Statut `excluded`, score 0 |

## Pourquoi ces choix
- **Âge ≥ 58** : proxy d'une fenêtre de transmission à 3-7 ans. Le palier est volontairement
  progressif, un seuil binaire serait arbitraire. Ce n'est **qu'un proxy** : un dirigeant de 64 ans
  peut ne pas vouloir vendre, un de 52 ans peut y être contraint.
- **Taille** : un search fund finance typiquement une PME rentable de quelques M€ à ~30 M€ de CA ;
  sous ~1,5 M€ l'entreprise ne supporte pas un dirigeant salarié + dette d'acquisition.
- **Qualité** : marge et régularité plutôt que la croissance, car on achète de la stabilité.
- **Données absentes** : 0 point sur le critère concerné (on n'invente pas) + pénalité légère.
  Une cible à fort potentiel mais sans comptes reste visible, avec son « n.d. ».
- **EBE plutôt que résultat net** : l'EBE est neutre vis-à-vis de la dette, des amortissements et de
  l'exceptionnel, et c'est la base des multiples de valorisation. Les paliers d'EBE sont plus
  hauts que ceux de la marge nette (l'EBE est calculé avant amortissements, charges financières et impôts) :
  ≥ 12 % est un bon niveau pour des services techniques. Le repli sur la marge
  nette est mentionné dans le détail du critère. Un EBE de plus de 4 ans n'est pas utilisé.
- **Seuil** : `qualified_threshold: 70` (ADR-011). Sur le run réel du département 92 (314 sociétés non
  exclues, médiane 41/100, avec EBE), 70 qualifie 11,1 % de la population, 65 en qualifierait 17,8 %, 60
  22,3 %. Avant l'enrichissement EBE, 70 qualifiait 8,9 % : le manque de CA (60 % des sociétés) tirait
  les scores vers le bas, ce qui justifiait d'enrichir plutôt que d'abaisser le seuil.

## Limites assumées
- Pondérations posées par jugement, **non apprises** : la feuille de route prévoit de les
  recalibrer sur les RDV obtenus.
- Aucune donnée sur la dépendance client ni la récurrence réelle ; l'endettement INPI est exporté mais non noté : c'est le rôle
  des « signaux d'alerte » qualitatifs puis de la due diligence.
- Les dirigeants sont des mandataires sociaux, pas nécessairement les propriétaires du capital.

## Fourchette et fiabilité (ADR-018)
- **Score (plancher)** : le score officiel, seules les données disponibles rapportent des points.
- **Plafond** : le score obtenu si chaque donnée manquante s'avérait favorable.
- **Fiabilité** : la part du barème évaluée sur des données réelles (100 % = rien ne manque).
- **À documenter** : sous le seuil, mais plafond au-dessus. Un appel ou une liasse fiscale peut
  qualifier la cible : elle apparaît dans le rapport de deal flow au lieu de disparaître.

## Du score à la décision (ADR-020)
Le rapport de deal flow ajoute au score des **signaux factuels** (règles sur les données), un
**montage LBO indicatif** et une **recommandation** argumentée : à approcher, à creuser, à
documenter, non prioritaire ou écartée. Seuils dans `risk_thresholds` (scoring.yaml) et hypothèses
de financement dans `financing` (thesis.yaml).
