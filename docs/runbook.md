# Runbook — reprendre le projet en 30 minutes

## 0-5 min : installer et vérifier
```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[all]"
pytest && pme-radar run --offline
```
Doit finir par un tableau d'entonnoir (45 identifiées / 23 qualifiées sur les fixtures).

## 5-10 min : comprendre
`docs/architecture.md` (schéma) → `docs/walkthrough.md` (module par module). Les réglages sont dans
`config/` : on ne touche presque jamais au code.

## 10-20 min : premier run réel
1. Vérifier l'accès réseau aux API (voir `PLAN.md` pour les paramètres attendus) et la configuration :
   `pme-radar check-config`.
2. `pme-radar source && pme-radar enrich && pme-radar score` (sans `--offline`). La commande
   `source` affiche le nombre de résultats par code NAF et le nombre d'appels réseau / servis
   par le cache.
3. **Si une erreur 400/422 apparaît** : les noms de paramètres de `build_params` sont à corriger
   (ADR-001). Si des champs sont vides : `enrich.parse_director` / `parse_financials`.
4. Regarder la distribution des scores, **recalibrer `qualified_threshold`** (ADR-011).
5. Revalider les codes NAF de `thesis.yaml` (ADR-002).

## 20-30 min : cycle hebdomadaire
```bash
pme-radar run                       # ajoute --llm anthropic si clé dans .env
streamlit run dashboard/app.py
# Après relecture et envoi MANUELS des emails :
pme-radar track <SIREN> contacted
pme-radar track <SIREN> replied     # puis meeting / declined / bounced
pme-radar track <SIREN> meeting --date 2026-11-20   # saisie rétroactive
pme-radar deliverability --domain votre-domaine.fr --selector <sélecteur DKIM>
```
Automatisation hebdomadaire : `n8n/README.md`.

**Cache et coûts d'un run hebdomadaire** : les réponses des API sont gardées 6 jours
(`PME_RADAR_CACHE_TTL_DAYS`) ; chaque semaine repart donc de données fraîches, et `--refresh`
force une relecture immédiate. Côté IA, `draft` ne rappelle le modèle que pour les cibles
nouvelles ou dont les faits ont changé (`--no-reuse` pour tout régénérer). Avant d'envoyer,
relire la mention de conformité ajoutée en fin de brouillon (`config/campaign.yaml`).

## Délivrabilité : warm-up et bonnes pratiques d'envoi
- **Domaine dédié** à la prospection (ex. `cabinet-xyz.fr`), jamais le domaine principal : une
  mauvaise réputation ne doit pas contaminer les emails du quotidien.
- **Avant le premier envoi** : MX, SPF (`-all` à terme), DKIM actif, DMARC (`p=none` + `rua` pour
  commencer, puis `quarantine`) → `pme-radar deliverability --domain …` doit être sans ❌.
- **Warm-up (3-4 semaines)** : démarrer à ~10-20 emails/jour, boîte déjà utilisée en échanges réels,
  augmenter d'environ 20-30 % par semaine tant que les rebonds restent sous le seuil. Ce sont des
  ordres de grandeur prudents, à ajuster selon le fournisseur.
- **Volumes** : un seul expéditeur humain, quelques dizaines d'emails/jour maximum, envois étalés.
  Ici le volume est faible par construction (PME ciblées, emails personnalisés).
- **Hygiène** : vérifier les adresses avant envoi, stopper dès que le rebond dépasse 2 % (alerte) et
  5 % (critique) — seuils de `config/campaign.yaml` ; pas d'images/pièces jointes/liens raccourcis au
  premier contact ; texte brut ; lien de désinscription ou mention d'opposition.
- **Suivi** : un `bounced` n'est jamais relancé ; un `declined` n'est jamais recontacté.
- **Réputation** : surveiller le domaine via les outils des fournisseurs (ex. Google Postmaster) et
  les rapports DMARC `rua`.

## Dépannage
| Symptôme | Piste |
|---|---|
| « … introuvable : lancer d'abord `pme-radar …` » | Lancer l'étape indiquée |
| « scoring.yaml invalide » / « thesis.yaml invalide » | Corriger les points listés ; `pme-radar check-config` pour vérifier |
| 429 ou redirection 302 de l'API | Augmenter `min_interval` dans `CachedClient` ; le cache évite de refaire les pages |
| Résultats identiques d'une semaine à l'autre | Vérifier `PME_RADAR_CACHE_TTL_DAYS` (0 = cache permanent) ou lancer avec `--refresh` |
| `draft` : « échec … refus du modèle » | Le modèle a décliné la demande : relire les faits de la cible ; pas de nouvel essai automatique |
| `draft` : « Aucune analyse produite » | Identifiants Anthropic, quota ou nom de modèle (`ANTHROPIC_MODEL`) |
| Résultats trop nombreux/peu | Ajuster NAF/effectif dans `thesis.yaml` |
| Sheets non mis à jour | `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_SHEET_ID`, classeur partagé avec le compte de service |
