# FastAPI, uvicorn et httpx — mini-cours

*Entrée dans le projet : partie 5, sous-étape 5.6 (ADR-0040). Versions : `fastapi` 0.142, `uvicorn` 0.54, `httpx` 0.28 (`uv.lock`).*

## À quoi ça sert

Une **API HTTP** sépare le calcul (l'inférence) de ce qui l'affiche (l'interface) : l'interface demande « les matchs du 19 mai 2024 » par une requête HTTP et reçoit du JSON, sans rien savoir de la base ni du modèle. FastAPI écrit ces routes en Python ; uvicorn est le serveur qui les fait tourner ; httpx est le client qui les appelle (l'interface Streamlit, et les tests).

## Comment ça marche

Une route est une fonction décorée ; ses paramètres typés deviennent des paramètres de requête validés, et son type de retour un schéma de réponse (`src/foot_predictor/api/app.py`) :

```python
@app.get("/matches", response_model=list[schemas.MatchSummary])
def matches(date: dt.date, mode: schemas.Mode = "replay") -> list[dict]:
    ...
```

- `date: dt.date` : FastAPI refuse `?date=hier` (422) sans une ligne de code ;
- `response_model` : la réponse est **validée** par un schéma Pydantic (`schemas.py`) avant de partir ;
- le tout produit une documentation OpenAPI interactive (`/docs`).

Les **codes HTTP** disent ce qui s'est passé : 200 (lu), 201 (créé), 403 (interdit : date sous scellés), 404 (inconnu), 409 (conflit avec l'état : match indisponible), 422 (entrée invalide), 501 (pas encore fait : H2), 503 (service indisponible : modèle absent).

uvicorn est un serveur **ASGI** : il reçoit les connexions sur `127.0.0.1:8000` et passe chaque requête à l'application. Liaison `127.0.0.1` = seul le portable peut appeler l'API ; `0.0.0.0` = tout le réseau (refusé ici).

## Sa place dans le projet

`api/` (couche « API » du rapport F.2) appelle `inference/` et rien d'autre. L'interface (`ui/`) l'appelle par httpx, jamais par un import Python (rapport F.7). Les tests utilisent `TestClient` (httpx sans réseau) avec un contexte synthétique injecté par la fabrique `create_app(provider, sessions)`.

## Ce qu'elle remplace

Rien d'existant ; l'alternative écartée était FastAPI + Jinja et HTMX (plus « web », plus long, décision M21) ou Flask (validation et documentation à écrire soi-même).

## Avantages et limites

| Avantages | Limites |
|---|---|
| validation et documentation automatiques par les types | une dépendance de plus à maintenir (Pydantic, Starlette) |
| `TestClient` : tests d'API rapides, sans serveur | pas d'authentification ici (usage local seulement) |
| codes HTTP et schémas : un contrat clair avec l'interface | un processus à démarrer à côté de la base |

## Commandes essentielles

```bash
uv run python -m foot_predictor.api serve                     # démarre l'API (127.0.0.1:8000)
curl -s "http://127.0.0.1:8000/matches?date=2024-05-19"        # une requête à la main
uv run pytest tests/api -q                                     # tests de l'API
```

Documentation interactive : http://127.0.0.1:8000/docs (API démarrée).

## Pour aller plus loin

https://fastapi.tiangolo.com/tutorial/ ; à approfondir en priorité : l'injection de dépendances de FastAPI (`Depends`), qui remplacerait ici la fabrique et ses fonctions injectées.
