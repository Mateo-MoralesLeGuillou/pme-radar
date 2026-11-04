# Architecture

```mermaid
flowchart LR
    subgraph Sources["Open data (sans clé)"]
        RE[API Recherche d'entreprises]
        BO[BODACC]
        FX[(Fixtures synthétiques<br/>mode --offline)]
    end
    CFG[/config/thesis.yaml<br/>config/scoring.yaml/]
    RE -->|pagination + cache| S[source]
    FX -.->|--offline| S
    CFG --> S
    S -->|raw parquet| E[enrich<br/>dérivés + flag BODACC]
    BO --> E
    FX -.-> E
    E -->|enriched.jsonl| SC[score<br/>déterministe, explicable]
    CFG --> SC
    SC -->|scored.jsonl| D[draft<br/>top N qualifiées]
    LLM{{LLMProvider<br/>Mock ou Anthropic}} --> D
    D -->|brouillons À RELIRE| O[outreach<br/>suivi campagne CSV]
    O --> X[export]
    SC --> X
    X --> CSV[(CSV)]
    X -.->|optionnel| GS[(Google Sheets)]
    CSV --> DB[Dashboard Streamlit]
    O --> DL[deliverability<br/>SPF/DKIM/DMARC/MX + KPI]
    N8N[n8n hebdo] -->|exécute run| S
    X --> N8N
    N8N --> GS
    N8N --> DG[Digest email fondateur]
    H((Humain)) -->|relit, envoie, pilote statuts| O
```

## Flux de données
| Étape | Entrée | Sortie |
|---|---|---|
| `source` | thèse, API | `data/raw/companies.parquet` |
| `enrich` | raw, BODACC | `data/processed/enriched.jsonl` |
| `score` | enriched, scoring.yaml | `data/processed/scored.jsonl` |
| `draft` | scored, LLM | `analyzed.jsonl`, `out/drafts.csv`, `out/campaign.csv` |
| `export` | analyzed, campaign | `out/{identified,qualified,contacted,meeting,funnel}.csv` (+ Sheets) |

## Principes
1. Chaque étape lit/écrit un fichier : reprise possible après n'importe quelle étape.
2. Tout ce qui peut changer sans toucher au code est en YAML.
3. Toute dépendance externe (API, LLM, Sheets) est injectable et remplaçable par un mock.
4. Le dossier `data/` (potentiellement nominatif) n'est jamais versionné.
