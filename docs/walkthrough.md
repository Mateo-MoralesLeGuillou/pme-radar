# Walkthrough — comprendre et défendre pme-radar

Pour chaque module : **ce qu'il fait · pourquoi ce choix · une limite connue.** Aucune connaissance
de code requise.

## Vue d'ensemble en une phrase
Un entonnoir automatisé : on part de *toutes* les PME d'Île-de-France d'un secteur, on élimine, on
note, on prépare un message pour les meilleures, et on mesure ce qui se passe ensuite.

## Les modules

### `config/` (thesis.yaml, scoring.yaml, campaign.yaml)
- **Fait** : décrit la thèse (secteurs, taille, zone), les points du score et les seuils d'alerte.
- **Pourquoi** : un analyste doit pouvoir changer d'avis (« on monte le seuil à 75 ») sans développeur.
- **Limite** : les pondérations sont des hypothèses de jugement, pas des paramètres appris.

### `sources/` (recherche_entreprises, bodacc, _http)
- **Fait** : interroge deux bases publiques gratuites : l'annuaire des entreprises (identité,
  dirigeants, chiffres) et le BODACC (annonces légales, dont les faillites). Gère la pagination, la
  limite de débit, les erreurs temporaires, et mémorise les réponses sur disque.
- **Pourquoi** : open data = zéro coût, auditable ; le cache rend les runs reproductibles et polis.
  Il expire au bout de 6 jours pour que le run hebdomadaire voie les nouvelles entreprises et les
  nouvelles procédures collectives (ADR-014).
- **Limite** : les API n'étaient pas joignables pendant la construction. Le code suit leur documentation
  telle que connue ; **le premier run réel doit confirmer les noms de paramètres** (ADR-001).

### `enrich.py`
- **Fait** : transforme les données brutes en fiche propre : âge du dirigeant, ancienneté, marge,
  croissance du CA, procédure collective.
- **Pourquoi** : règle centrale, un compte absent n'est **pas** un zéro. Beaucoup de PME ne publient
  pas leurs comptes ; leur attribuer 0 € fausserait tout.
- **Limite** : on voit le dirigeant *mandataire*, pas l'actionnaire réel ; âge parfois estimé à ±1 an.

### `scoring.py`
- **Fait** : note chaque cible sur 100 en additionnant des critères lisibles et produit une phrase
  d'explication (« 78/100 : dirigeant 64 ans, CA 6,2 M€, marge 9 %… »).
- **Pourquoi** : un score qu'on ne sait pas expliquer ne se défend pas devant un fondateur. Pas de
  boîte noire : tout est dans un tableau YAML.
- **Limite** : l'âge est un proxy de l'intention de céder ; le score classe, il ne prédit pas.

### `llm/` (base, mock, anthropic, prompts, analysis)
- **Fait** : pour les meilleures cibles, une IA rédige une mini-thèse, des signaux d'alerte et un
  brouillon d'email. Un faux modèle (`MockLLM`) permet de tout faire tourner sans clé ni coût.
- **Pourquoi** : l'IA est utile là où il faut rédiger et nuancer ; elle est **tenue à l'écart du
  score** pour garder un classement stable et auditable. Sa sortie est vérifiée automatiquement
  (3 lignes de thèse, ton, mots interdits). Une cible en échec n'arrête pas le lot, et une analyse
  dont les faits n'ont pas changé est réutilisée au lieu d'être repayée (ADR-015).
- **Limite** : la qualité réelle des textes avec un vrai modèle n'a pas été mesurée ici (pas de clé) ;
  l'IA ne connaît que les faits fournis et peut rester générique.

### `outreach.py`
- **Fait** : exporte les brouillons (marqués « À RELIRE ») et tient un tableau de suivi : contacté,
  répondu, RDV, refus, rebond, avec dates.
- **Pourquoi** : **le programme n'envoie jamais rien**. Écrire à un cédant est un acte humain.
- **Limite** : suivi manuel (`pme-radar track`) ; pas de lien avec une boîte mail ou un CRM.

### `deliverability.py`
- **Fait** : vérifie que le domaine d'envoi est correctement configuré (MX, SPF, DKIM, DMARC), avec
  recommandations en clair.
- **Pourquoi** : sans cela, les emails finissent en spam et l'entonnoir s'effondre sans qu'on sache pourquoi.
- **Limite** : ne mesure pas la réputation réelle du domaine ni le placement en boîte de réception.

### `funnel.py`
- **Fait** : calcule identifiées → qualifiées → contactées → réponses → RDV, avec taux, et alerte si
  les rebonds ou les réponses sortent des seuils.
- **Pourquoi** : piloter par les conversions, pas à l'intuition. En dessous de 20 envois, aucune
  conclusion n'est tirée.
- **Limite** : l'échantillon d'un search fund est petit ; les taux sont indicatifs.

### `risks.py`, `deal.py` et `report.py` : le rapport de pré-due diligence
- **Fait** : un mémo au format private equity. Une synthèse exécutive (chiffres clés, entonnoir, plan
  d'action), une vue d'ensemble (tableau comparatif, football field des valorisations), puis un dossier
  par cible : thèse d'investissement et points de vigilance, financiers, analyse du score, valorisation
  et sensibilité, emplois et ressources du montage LBO (frais compris), signaux factuels, plan de due
  diligence référencé (T.1, C.2…), demandes d'informations priorisées, prochaines étapes. Sortie
  HTML et PDF A4 (`--pdf`, par un navigateur installé).
- **Pourquoi** : le score dit « qui regarder » ; le dossier dit « vaut-elle un appel, et que
  demander », dans la forme qu'attend un investisseur. Le score a aussi une fourchette : une cible
  notée 55 sur 60 % du barème peut valoir 80 ; le modèle la signale « à documenter ».
- **Limite** : valeur et montage sont des ordres de grandeur (ni dette nette, ni BFR, ni EBE
  normalisé) ; la couverture de la dette ne dépend que des hypothèses, elle n'entre donc pas dans
  la recommandation.

### `export.py` et `dashboard/`
- **Fait** : CSV toujours ; Google Sheets si configuré. Le dashboard est construit comme un terminal
  financier : une **recherche globale** (nom, ville, SIREN, dirigeant) ouvre la **fiche entreprise**
  (recommandation, score, chiffres clés, puis onglets profil, finances, score, valorisation, due
  diligence, contact, documents). S'y ajoutent l'accueil (actions du jour), les cibles (filtres,
  export Excel, rapport d'une sélection), les prises de contact (relances, pipeline par statut), les
  rapports et une aide « je cherche… → où ».
- **Pourquoi** : on ne doit pas avoir à comprendre l'outil pour trouver une information ; chaque
  fiche se partage par un lien (`?siren=`) et se défend en comité en montrant d'où vient chaque point.
- **Limite** : l'export Sheets n'a pas été testé sur un vrai classeur (testé avec un faux) ; le
  dashboard est local (pas de comptes ni de droits d'accès).

### `n8n/`
- **Fait** : relance l'ensemble chaque lundi, ajoute les nouvelles cibles au Sheet, envoie un digest.
- **Pourquoi** : transformer un script en routine. **Limite** : non exécuté sur une vraie instance.

## 10 questions d'entretien (et éléments de réponse)
1. **Pourquoi ce score et pas un modèle de machine learning ?** Pas de données d'apprentissage au
   départ (aucun RDV observé) ; un score transparent se défend et s'ajuste. Roadmap : l'apprendre sur
   les RDV obtenus.
2. **Pourquoi l'âge du dirigeant compte-t-il autant ?** C'est le meilleur signal public d'une
   transmission proche (25 pts sur 100), mais c'est un proxy : d'où les 75 autres points et le suivi.
3. **Que faites-vous des comptes confidentiels ?** Donnée manquante, pas zéro : 0 point sur les critères
   financiers, −5 de pénalité légère, jamais d'exclusion, signalé « n.d. ».
4. **Comment évitez-vous les entreprises en difficulté ?** BODACC : toute procédure collective exclut
   automatiquement. Limite : la difficulté sans procédure (marge faible) n'est vue qu'au score.
5. **À quoi sert l'IA, concrètement ?** Mini-thèse, signaux d'alerte, brouillon personnalisé pour le
   top N. Elle ne modifie jamais le score (ADR-003).
6. **Comment garantissez-vous que l'IA n'invente rien ?** Elle ne reçoit que des faits structurés,
   la consigne interdit d'inventer, la sortie est validée (format, ton, mots interdits) et un humain
   relit. Ce n'est pas une garantie absolue, d'où la relecture.
7. **Comment gérez-vous le RGPD ?** `data/` non versionné, échantillon synthétique, minimisation vers
   le LLM, droit d'opposition tracé (`declined`). Voir `docs/rgpd.md` ; pas un avis juridique.
8. **Qu'est-ce qui n'a pas été testé en conditions réelles ?** Les appels aux API (réseau bloqué
   pendant la construction), le provider Anthropic, Google Sheets, n8n. Tout le reste est testé.
9. **Comment mesurez-vous le succès ?** L'entonnoir : taux de qualification, réponse, RDV, avec
   alertes. Un bon signal n'est pas le volume d'emails mais le taux de RDV par email délivré.
10. **Comment passer du score à la décision ?** Le rapport de deal flow : signaux factuels, montage
    indicatif, documents à obtenir et questions de DD ; la recommandation suit des règles
    explicites (ADR-020), pas le jugement de l'IA.
11. **Prochaine amélioration à plus fort effet ?** Signaux de cession (annonces, ventes d'actifs,
    changement de dirigeant), puis scoring appris sur les RDV, puis intégration CRM.
