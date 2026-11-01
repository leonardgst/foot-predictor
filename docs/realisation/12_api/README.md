# Étape 12 : API (jalon J7)

Mode d'emploi de l'API locale. Décision : **ADR-0040** (rapport F.6). Code : `src/foot_predictor/api/` (`app.py`, `schemas.py`). L'API ne fait que servir l'inférence (`inference/`, étape 11) ; elle n'a aucune logique de calcul propre.

## Démarrer

```bash
uv run python -m foot_predictor.api serve                  # http://127.0.0.1:8000, documentation sur /docs
uv run python -m foot_predictor.api serve --port 8001      # autre port
```

Liaison **locale seulement** : `--host` n'accepte que `127.0.0.1` ou `localhost` (`0.0.0.0` exposerait l'API au réseau : refusé). Pas d'authentification ni de CORS, pour un usage sur le portable seul. La base de travail doit être démarrée et en révision 0008 (`uv run alembic current`).

## Routes

| Méthode et route | Rôle | Réponses |
|---|---|---|
| `GET /health` | vivacité, base, modèle actif | 200 (`ok` ou `degraded`, jamais une erreur) |
| `GET /competitions` | championnats présents ; `in_model_scope` vrai pour le top 5 | 200 |
| `GET /matches?date=AAAA-MM-JJ&mode=replay\|live&competition=<id>&horizon=H1\|H2` | matchs du jour avec leur statut de disponibilité et leurs raisons ; `horizon=H2` : avec la composition (rejeu seulement, 6.10) | 200 ; 403 date refusée ; 422 paramètre invalide |
| `GET /matches/{id}/availability?horizon=H1&mode=replay` | détail par variable et par équipe | 200 ; 403 ; 404 (H2 en live : 200, statut `h2_unavailable` et sa raison) |
| `POST /matches/{id}/predictions?horizon=H1&mode=replay&force=false` | calcule et trace dans `ops.prediction` | **201** créée ; **200** déjà tracée (renvoyée) ; 403 ; 404 ; **409** indisponible (raisons) ou live après le coup d'envoi, ou H2 en live |
| `GET /models/active` | carte d'identité du modèle actif (sans chemin de fichier) | 200 ; 503 modèle absent |
| `GET /models/h2/contribution` | apport mesuré des groupes de variables H2 (chemin de décision, diagnostics, structures, gain de G5 par tranche de journées), lu dans les rapports d'expériences (6.10, ADR-0051) | 200 ; 503 rapport absent |
| `GET /data/freshness` | dernière mise à jour de chaque source ; en live, une ligne par championnat du top 5 (complet jusqu'au…) | 200 |

Toutes les erreurs ont le même corps : `{"detail": "…", "reasons": ["…"]}`.

**Refus du scellé** : toute date à partir du 1er juillet 2025 répond **403** tant que le test scellé H1 n'est pas terminé ; le rejeu ne s'ouvre que sur 2021-22 à 2024-25 (403 sinon), jusqu'au test scellé de H2 (ADR-0045). Un match scellé déjà joué n'est jamais servi : 404 tant que la table est fermée ; depuis l'ouverture à l'inférence (5.13), 403 (rejeu fermé, ou live sur un jour passé). Un match à venir est servi en live, avec l'historique complet.

## Exemple complet (`curl`, API démarrée)

```bash
curl -s http://127.0.0.1:8000/health
curl -s "http://127.0.0.1:8000/competitions"
curl -s "http://127.0.0.1:8000/matches?date=2024-05-19&mode=replay"                 # 77 matchs, 33 disponibles
curl -s "http://127.0.0.1:8000/matches/<id>/availability"                           # <id> pris dans la liste
curl -s -X POST "http://127.0.0.1:8000/matches/<id>/predictions"                    # 201, puis 200 si on relance
curl -s -X POST "http://127.0.0.1:8000/matches/<id>/predictions?force=true"         # nouvelle ligne tracée
curl -s "http://127.0.0.1:8000/matches?date=2025-08-16"                             # 403 : sous scellés
curl -s http://127.0.0.1:8000/models/active
curl -s http://127.0.0.1:8000/data/freshness
```

## Cache et version des données

Le contexte d'inférence (table des matchs, noms, cotes, jeu versionné) est construit une fois par processus et gardé en mémoire ; il est reconstruit quand sa **clé** change : dernier `ops.load_run` réussi, empreinte des fichiers de football-data du live (noms seulement, sans les relire : un nouveau téléchargement suffit) et jour UTC (« aujourd'hui » du live). Depuis 5.14, il contient la table superposée par football-data (ADR-0042). Les lignes d'un jour sont en cache (étape 11) ; les modèles de rejeu aussi (`models/rejeu/`).

## Temps mesurés (2026-10-01, base de travail, vrai serveur uvicorn)

| Requête | Temps |
|---|---|
| Première requête (`/health`, construction du contexte) | 7,0 s |
| `GET /matches`, journée de 77 matchs, à froid | 6,2 s |
| `GET /matches`, même journée, à chaud | 1,3 s |
| `GET /matches/{id}/availability`, à chaud | 0,08 s |
| `POST /matches/{id}/predictions`, à chaud | 0,08 s |
| `GET /competitions`, `/models/active`, `/data/freshness` | 0,01 à 0,04 s |

## Tests

`tests/api/test_app.py` (`TestClient`, contexte synthétique) : compétitions et périmètre, résumé d'une journée, 403 (scellé, saison fermée), 422, 404, 409 (indisponible, hors périmètre), carte sans chemin et 503, fraîcheur, documentation OpenAPI, refus d'une adresse non locale ; en base (`db`) : 201, puis 200 (idempotence), puis 201 avec `force`.

## Limites connues

- Pas d'authentification : à ne jamais exposer au réseau (la partie 6 étudiera Compose et le réseau Docker).
- Live réel depuis 5.14 : vérifié sur les vraies données le 2026-10-22 (5 matchs disponibles le 23 octobre, 20 « périmés » le 24, 403 pour un jour passé). La part d'indisponibles dépend de la règle de fraîcheur (README de l'étape 11).
- `starlette` signale qu'il préférera bientôt `httpx2` pour `TestClient` : avertissement sans effet aujourd'hui, à suivre lors d'une mise à jour.
