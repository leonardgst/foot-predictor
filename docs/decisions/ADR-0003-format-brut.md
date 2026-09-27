# ADR-0003 — Format de stockage du brut

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, F.1, F.2, G.6, G.7, G.8, décision M3

## Contexte

Le brut est aujourd'hui stocké uniquement en JSONB dans Postgres (volume Docker). Un `docker compose down -v` effacerait des données payantes, impossibles à recollecter après l'abonnement. Le contrôle des doublons parcourt tout le JSONB sans index, et certaines sources sont transformées avant stockage (football-data : 7 champs conservés sur plus de 100).

## Options envisagées

1. JSONB seul (existant) : simple, fragile, lent.
2. **Fichiers `.json.gz` + journal de requêtes comme source de vérité**, JSONB facultatif.
3. Les deux systématiquement : double stockage à maintenir.

## Décision

Option 2.

- Arborescence `data/raw/<source>/<endpoint>/<partition>/<clé>.json.gz` (rapport G.7), dossier **ignoré par Git**.
- Chaque fichier est autoportant : enveloppe `{request, fetched_at, http_status, headers_quota, body}`, où `body` est la réponse de l'API **intacte**.
- Un journal des requêtes (`data/raw/_manifest/<source>.jsonl`, une ligne par requête : horodatage, endpoint, paramètres, statut HTTP, `errors`, nombre de résultats, quota restant, fichier, sha256), reconstructible à partir des fichiers.
- Écriture atomique (fichier temporaire puis renommage) ; **aucun fichier n'est jamais écrasé** : une recollecte crée une nouvelle version horodatée.
- football-data : on stocke le CSV tel que téléchargé, toutes colonnes comprises (cotes, heure, statistiques).

## Conséquences

- Les tables `raw.*` deviennent facultatives : au mieux un journal ou une copie de confort, jamais la seule copie.
- `staging` se reconstruit entièrement à partir des fichiers (ADR à venir sur le référentiel, décision M7).
- La sauvegarde (ADR-0006) se résume à copier `data/raw/`.
