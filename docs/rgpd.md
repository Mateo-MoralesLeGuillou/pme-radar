# RGPD et éthique d'approche

## Nature des données
- **Entreprises** : informations publiques (SIREN, NAF, comptes publiés, annonces BODACC).
- **Dirigeants** : nom, prénoms, mois/année de naissance sont des **données personnelles**, publiées
  par l'API pour transparence économique mais soumises au RGPD dès qu'on les réutilise.

## Mesures dans ce dépôt
- `data/` est gitignoré : aucun fichier de run n'est versionné. `.env` et clés idem.
- `examples/` ne contient que des données **synthétiques** (noms fictifs, SIREN `999…`), générées
  par `scripts/make_fixtures.py`.
- **Minimisation vers le LLM** : seuls les faits utiles sont transmis (pas de SIREN, pas de date de
  naissance exacte ; le nom du dirigeant sert uniquement à la salutation).
- Le mode par défaut (`MockLLM`) n'envoie aucune donnée à un tiers.

## À faire par l'utilisateur d'un run réel (hors périmètre du code)
- **Base légale** : intérêt légitime (prospection B2B). Information des personnes au premier contact
  (identité, source des données, finalité, droit d'opposition) : chaque brouillon se termine déjà
  par une mention fixe sur la source des données et le droit d'opposition (`compliance_footer` dans
  `config/campaign.yaml`, ADR-016). Compléter l'identité de l'expéditeur avant tout envoi.
- **Droit d'opposition** : tout « non » ou demande d'effacement est enregistré (`declined`) et la
  personne n'est plus jamais sollicitée.
- **Durée de conservation** : définir et purger (ex. 3 ans après dernier contact).
- Vérifier la politique de réutilisation des API et, pour un envoi à une adresse professionnelle
  nominative, les règles CNIL de prospection B2B. *Cette page n'est pas un avis juridique.*

## Éthique d'approche des cédants
Un dirigeant qui reçoit un email parle potentiellement de l'œuvre de sa vie et de ses salariés :
- ton respectueux, jamais de pression ni d'urgence artificielle, **aucun prix annoncé**, aucune
  fausse promesse (le validateur de sortie LLM rejette « garanti », « urgent », « offre ferme »…) ;
- un refus est explicitement entendable et respecté ;
- l'email ne précise pas que l'entreprise est « en difficulté » ou « à vendre » : on parle de
  continuité et de transmission, jamais d'opportunisme ;
- relecture humaine obligatoire avant tout envoi.

## Rapport de deal flow
Le rapport (`pme-radar report`) nomme les dirigeants, leur âge et leurs mandats : c'est un document
de travail confidentiel, écrit dans `data/out/` (non versionné) et marqué comme tel en couverture.
Seul l'exemple construit sur l'échantillon synthétique est dans le dépôt
(`examples/rapport_deal_flow_sample.*`). La voix off de la vidéo n'envoie à ElevenLabs que le texte
de narration : aucune donnée personnelle.

