# Orchestration n8n

`weekly_origination.json` : workflow importable (n8n ≥ 1.x, installation **auto-hébergée** : le nœud
« Execute Command » n'existe pas sur n8n Cloud).

```
Cron lundi 7h → pme-radar run → lire qualified.csv → parser → garder les nouvelles cibles
   → ajout dans Google Sheets (onglet Qualified, clé = siren)
   → digest (top 10 par score) → email au fondateur
```

## Importer
1. n8n → *Workflows* → *Import from file* → `n8n/weekly_origination.json`.
2. Variables d'environnement du serveur n8n :
   `PME_RADAR_DIR` (chemin du dépôt, avec `.venv` installé), `DIGEST_FROM`, `DIGEST_TO`.
3. Nœud **Google Sheets** : créer l'identifiant OAuth2/compte de service dans n8n, remplacer
   `REMPLACER_PAR_ID_DU_CLASSEUR` par l'ID du classeur (créer un onglet `Qualified`).
4. Nœud **Digest email** : créer un identifiant SMTP (ce compte envoie *le digest interne*, pas les
   emails aux dirigeants, qui restent des brouillons humains).
5. Exécuter une fois manuellement, vérifier, puis activer le workflow.

## Points d'attention
- **Déduplication** : la mémoire des SIREN déjà vus est dans les *static data* du workflow (actives
  uniquement en exécution planifiée, pas en test manuel). La première exécution notifie donc tout.
- Le workflow lance un run réel (sans `--offline`) : vérifier que
  `pme-radar source` atteint bien les API (voir `docs/runbook.md`).
- Ce workflow n'a pas pu être exécuté dans l'environnement de construction (pas d'instance n8n) :
  structure validée en JSON uniquement. À tester avant mise en production.
