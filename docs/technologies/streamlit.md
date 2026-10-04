# Streamlit — mini-cours

*Entrée dans le projet : partie 5, sous-étape 5.9 (ADR-0040). Version : `streamlit` 1.64 (`uv.lock`, groupe `ui`).*

## À quoi ça sert

Streamlit fabrique une **page web interactive en Python pur** : pas de HTML, de CSS ni de JavaScript à écrire. On appelle `st.date_input`, `st.button`, `st.bar_chart`, et Streamlit dessine les widgets dans le navigateur. Idéal pour une interface locale de démonstration ou d'analyse ; c'est l'écran du projet (rapport F.7).

## Comment ça marche

Le principe surprend au début : **le script entier se réexécute de haut en bas à chaque interaction** (un clic, une date changée). La valeur d'un widget est simplement ce que renvoie son appel :

```python
mode_label = left.radio("Mode", ["Rejeu", "Live"], key="mode_label")  # src/foot_predictor/ui/app.py
date = middle.date_input("Date", value=default, key=f"date_{mode}")
matches = cached(key, lambda: client.matches(date, mode, selected))
```

Trois notions suffisent :

- **`st.session_state`** : un dictionnaire qui survit aux réexécutions (écran courant, match choisi, réponse de l'API). Un widget avec `key=` y range sa valeur.
- **Les rappels** (`on_click=`) : la fonction s'exécute *avant* la réexécution suivante ; c'est là qu'on peut changer d'écran (`state.screen = "Détail"`), ce qui est interdit après la création du widget.
- **Le coût d'une réexécution** : tout appel lent se refait à chaque clic. D'où le mémo de session (`cached`) autour de `/matches` ; Streamlit propose aussi `st.cache_data`, partagé entre sessions, écarté ici pour que les tests restent indépendants.

Le serveur Streamlit (sur `127.0.0.1:8501`) tient une connexion WebSocket avec le navigateur et lui envoie les éléments à dessiner.

## Sa place dans le projet

`src/foot_predictor/ui/`, dernière couche (rapport F.2) : `app.py` (écrans), `client.py` (httpx vers l'API), `views.py` (mise en forme, fonctions pures). Ce qui ne passe **jamais** par Streamlit : la base, l'inférence, le modèle. L'interface est un client HTTP de l'API comme un autre (ADR-0040) ; un test d'architecture refuse tout import de `foot_predictor` hors de `ui`.

Tests : `streamlit.testing.v1.AppTest` exécute le script sans navigateur, permet de cliquer (`at.button(key=…).click().run()`) et de lire ce qui est affiché (`at.metric`, `at.error`, `at.dataframe`). Le réseau est remplacé par un faux transport httpx (`ui.client.TRANSPORT`).

## Ce qu'elle remplace

Une application web classique (FastAPI + gabarits HTML + JavaScript) ou un tableau de bord (Dash) : plus souples, mais beaucoup plus de code pour trois écrans. Les notebooks (ADR-0034) restent l'outil d'exploration ; Streamlit est l'outil de **consultation**.

## Avantages et limites

| Avantages | Limites |
|---|---|
| trois écrans en environ 600 lignes de Python (écrans, client, mise en forme) | la réexécution complète coûte cher si on ne mémorise rien |
| widgets, graphiques et tableaux prêts à l'emploi | mise en page peu fine (colonnes, onglets) |
| `AppTest` pour tester sans navigateur | `AppTest` ne rend pas les graphiques (on teste leurs données) |
| rechargement automatique quand le fichier change | écoute sur toutes les interfaces par défaut : `server.address` à fixer (`.streamlit/config.toml`) |
| | envoie des statistiques d'usage par défaut : `gatherUsageStats = false` |

## Commandes essentielles

```bash
uv run streamlit run src/foot_predictor/ui/app.py     # lance l'interface (http://127.0.0.1:8501)
FP_API_URL=http://127.0.0.1:8001 uv run streamlit run src/foot_predictor/ui/app.py   # autre API
uv run streamlit config show                          # configuration effective (adresse, port…)
uv run pytest tests/ui -q                             # tests des écrans (AppTest, faux transport)
```

## Pour aller plus loin

Documentation officielle : <https://docs.streamlit.io> (notamment « Session State » et « App testing »). Point à approfondir en priorité : le modèle d'exécution (réexécution, rappels, `session_state`), source de la plupart des surprises.
