# Étape 13 : interface (jalon J8)

Mode d'emploi de l'interface locale. Décision : **ADR-0040** (rapport F.7). Code : `src/foot_predictor/ui/` (`app.py` les écrans, `client.py` le client HTTP, `views.py` la mise en forme). L'interface **ne parle qu'à l'API** (étape 12) : elle ne lit jamais la base et n'importe aucune logique métier (un test d'architecture le vérifie).

## Démarrer

Deux terminaux, depuis la racine du dépôt (la base de travail doit tourner, en révision 0008) :

```bash
uv run python -m foot_predictor.api serve           # terminal 1 : API sur http://127.0.0.1:8000
uv run streamlit run src/foot_predictor/ui/app.py   # terminal 2 : interface sur http://127.0.0.1:8501
```

Ouvrir `http://127.0.0.1:8501` dans le navigateur. Autre adresse d'API : `FP_API_URL=http://127.0.0.1:8001 uv run streamlit run …`.

La configuration `.streamlit/config.toml` (lue quand `streamlit run` est lancé depuis la racine) lie l'interface à **127.0.0.1** (Streamlit écoute sinon sur toutes les interfaces du portable), coupe l'envoi de statistiques d'usage à Streamlit, et n'ouvre pas le navigateur tout seul (`headless`).

## Les trois écrans (barre latérale « Écran »)

| Écran | Contenu | Routes appelées |
|---|---|---|
| **Matchs** | mode (rejeu ou live), date, championnats ; une ligne par match : heure UTC, championnat, équipes, **pastille** de disponibilité (raison au survol, et tableau des matchs bloqués dans la légende), bouton **Prédiction** actif seulement si le match est disponible, bouton **Variables** (matrice de disponibilité seule) | `/competitions`, `/matches` |
| **Détail** | E[T], λ domicile et extérieur, P(T > 2,5) ; **intervalle [q10 ; q90] avec sa couverture annoncée** ; diagramme en barres de P(T = k), cases de l'intervalle colorées ; score réel en rejeu (et la probabilité que le modèle donnait à ce total) ; référence de marché avant clôture, si elle existe (jamais une variable, ADR-0036) ; tableau des variables présentes, manquantes ou périmées ; version du modèle, des données, ligne de `ops.prediction` | `POST /matches/{id}/predictions`, `/matches/{id}/availability` |
| **Modèle** | carte d'identité du modèle actif, variables requises, métriques de validation (4 plis), comparaisons avec leurs IC, limites connues, courbe d'apport (`docs/resultats/figures/courbe_apport.png`), fraîcheur des sources, état de l'API | `/models/active`, `/data/freshness`, `/health` |

| Pastille | Sens |
|---|---|
| 🟢 disponible | toutes les variables requises sont présentes : prédiction possible |
| 🔴 indisponible | au moins une variable manquante ou périmée : aucune prédiction |
| ⚪ hors périmètre | D2, coupe, barrage, autre championnat que le top 5 |
| ⚫ exclu | match annulé, abandonné ou sur tapis vert (ADR-0009) |
| 🟣 H2 non disponible | horizon avec composition : partie 6 |

**Le bouton « Prédiction » écrit dans `ops.prediction`** (mode `replay` ou `live`) : la création est idempotente, un second clic relit la prédiction déjà tracée (« déjà tracée, renvoyée telle quelle »).

**Erreurs** : chaque erreur de l'API s'affiche avec un titre selon son code (403 date refusée : saison scellée ou non ouverte au rejeu ; 404 ; 409 indisponible avec les raisons ; 501 H2 ; 503 modèle absent) et le message de l'API. Une API arrêtée donne « API injoignable » et la commande pour la lancer. En phase A, le mode **live** répond toujours 403 (aujourd'hui est sous scellés jusqu'au test scellé).

## Temps mesurés (2026-10-04, base de travail, vraie API, interface pilotée par `AppTest`)

| Action | Temps |
|---|---|
| Écran « Matchs », journée du 18/05/2025 (88 matchs : 24 disponibles, 64 hors périmètre), API à froid | 8,0 s |
| Même écran réexécuté (mémo de session) | 0,14 s |
| Clic « Prédiction » → écran « Détail » (prédiction créée et tracée) | 1,2 s |
| Écran « Modèle » | 2,2 s |

Le mémo de session garde au plus 20 réponses de `/competitions` et `/matches` ; le bouton **Rafraîchir** le vide (nouvelles données, statut qui change à l'approche du coup d'envoi en live).

## Tests

`tests/ui/` : un faux API (`fake_api.py`, `httpx.MockTransport`, réponses écrites à la main au format du contrat) remplace le réseau par `ui.client.TRANSPORT`.

- `test_client.py` : paramètres envoyés (championnats répétés), erreurs 403, 404, 409, 422 traduites, API injoignable, URL de `FP_API_URL` ;
- `test_views.py` : pastilles, ordre 0…9, 10+ de la loi, intervalle toujours avec sa couverture, variable manquante laissée vide avec sa raison, score réel, cartes ;
- `test_app.py` (`streamlit.testing.v1.AppTest`) : boutons actifs et inactifs, écran « Détail » après une prédiction, matrice d'un match indisponible, date scellée en live, API injoignable, écran « Modèle » ; test d'architecture : aucun module de `ui/` n'importe la base ni la logique métier.

## Limites connues

- Heures affichées en UTC (celles de l'API) : pas de conversion à l'heure de Paris.
- La courbe d'apport est une figure statique du dépôt (partie 4), lue sur le disque comme une illustration, pas une donnée servie par l'API.
- `AppTest` ne rend pas le graphique : les tests vérifient les données du diagramme (`views.distribution_frame`), pas son dessin.
- Le mode live n'affichera des matchs qu'en phase B (après le test scellé et la sous-étape 5.14).
