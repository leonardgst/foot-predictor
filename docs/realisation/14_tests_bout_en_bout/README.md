# Étape 14 : tests de bout en bout (jalon J8)

Chaîne complète : brut → `load` → porte des données → inférence → API → interface → `ops.prediction`. Décision : ADR-0040. Deux volets : un **test automatisé** (base de test, CI) et une **procédure manuelle** sur une vraie journée de rejeu.

## 1. Test automatisé (`tests/bout_en_bout/test_rejeu.py`, marqué `db`)

```bash
uv run pytest tests/bout_en_bout -q        # base de test démarrée (port 5433), environ 8 s
```

| Étape | Ce qui est vérifié |
|---|---|
| Brut | petite ligue synthétique (4 équipes, aller-retour, 2022-23 et 2023-24) écrite comme le collecteur : bruts API-FOOTBALL (liste, détails, journal, file) et CSV football-data (tirs) |
| Migration et chargement | base de test à la révision `0008_ops_prediction` ; vrai `load` : 24 matchs, 12 lignes football-data appariées sur 12 par saison |
| Porte des données | contexte d'inférence construit par `load_matches` (filtre du scellé), noms, fraîcheur, dernier chargement |
| API (`TestClient`) | première journée : matchs indisponibles avec raisons (pas d'historique) ; 5e journée de 2023-24 : 2 matchs disponibles, modèle du pli `rejeu-2023-m3_g0g2` ; date scellée : 403 |
| Interface (`AppTest`) | branchée sur le transport du `TestClient` (aucun import de la logique métier) : bouton actif, clic « Prédiction », écran « Détail » (E[T], λ, P(T > 2,5), intervalle et couverture annoncée, score réel, version du modèle) |
| Traçabilité | une ligne dans `ops.prediction`, mode `replay`, statut `available`, loi du total de somme 1 |

Le modèle de rejeu 2023-24 est appris, par la procédure du pli, sur des lignes synthétiques réalistes (2015-16 à 2022-23) : la mini-ligue est trop petite pour les 18 coefficients de M3. La base de test est vidée à la fin (`TRUNCATE`, comme le test du pipeline).

## 2. Procédure manuelle sur données réelles

Prérequis : Docker Desktop lancé (les conteneurs `foot-predictor-dev` et `foot-predictor-test` redémarrent seuls : `restart: unless-stopped`), base de travail chargée.

```bash
uv sync --all-groups
uv run alembic current                                            # 0008_ops_prediction (head)
uv run python -m foot_predictor.inference predict --date 2025-05-18 --mode replay   # contrôle sans service
uv run python -m foot_predictor.api serve                         # terminal 1 : http://127.0.0.1:8000
curl -s http://127.0.0.1:8000/health                              # {"status":"ok", ...}
uv run streamlit run src/foot_predictor/ui/app.py                 # terminal 2 : http://127.0.0.1:8501
```

Dans l'interface : écran « Matchs », mode « Rejeu », date du 18/05/2025 (valeur par défaut), puis « Prédiction » sur un match à pastille verte ; écran « Détail » ; écran « Modèle ».

**Chiffres relevés le 2026-10-04** (base de travail, chargement n° 5, modèle de rejeu `rejeu-2024-m3_g0g2`) :

| Journée | Matchs (toutes compétitions) | Disponibles (top 5) | Indisponibles du top 5 | Hors périmètre | Log-loss du total | Couverture de [q10 ; q90] |
|---|---|---|---|---|---|---|
| 18/05/2025 (fin de saison) | 88 | 24 (Premier League 5, Liga 10, Serie A 9) | 0 | 64 (« hors périmètre du modèle H1 ») | 1,8129 | 21 sur 24 observés, 87,6 % annoncés en moyenne |
| 17/08/2024 (ouverture) | 196 | 15 | 0 (les promus ont leur historique de D2) | 181 | 1,8290 | — |

Pour échelle, la log-loss du total du modèle sur les 4 plis de validation est 1,8805 (7 156 matchs) : une journée isolée de 15 à 24 matchs fluctue beaucoup autour de cette valeur. Les prédictions de rejeu reproduisent celles de l'évaluation (`check --only predictions`, étape 11).

**Temps mesurés** (même jour, portable) : écran « Matchs » à froid 8,0 s (construction du contexte de l'API), à chaud 0,14 s ; clic « Prédiction » 1,2 s ; écran « Modèle » 2,2 s (étape 13). Commande `predict` d'une journée, à froid : environ 9 s.

## 3. Bout en bout réel, rejeu et live (5.15, 2026-10-31)

Même chaîne qu'en section 2, sur la vraie base (chargement n° 7, `load_run-7+fd-bf1f933826`), avec le modèle final H1 actif (ADR-0044, ADR-0045) et football-data du jour. **Aucun `load`** : la reconstruction depuis le brut est prouvée par 2.12 et 3.11 (critère 1, ci-dessous).

```bash
# 0. collecte (accord de l'utilisateur ; 11 requêtes au plus)
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10
# 1. live sans service : rapport et traçage des prédictions disponibles du top 5
uv run python -m foot_predictor.inference live --days 7 --save
# 2. rejeu sans service
uv run python -m foot_predictor.inference predict --date 2025-05-18 --mode replay
# 3. services (port 8000 occupé sur ce portable, E-064 : port 8001)
uv run python -m foot_predictor.api serve --port 8001
FP_API_URL=http://127.0.0.1:8001 uv run streamlit run src/foot_predictor/ui/app.py
```

L'interface a été pilotée par `AppTest` branché sur la vraie API, en HTTP (comme le 2026-10-22, étape 13). Le vrai serveur Streamlit a été lancé 75 s par la commande documentée : `/_stcore/health` répond `ok` au bout de 2 s, écoute sur `127.0.0.1:8501` seulement.

| Volet | Résultat |
|---|---|
| Collecte | 11 requêtes (1 + 10), 11 fichiers stockés, 0 échec ; 0 requête API-FOOTBALL |
| Live, 7 jours (`reports/inference/live_2026-10-31.md`) | 48 matchs du top 5, **43 disponibles, 10 % d'indisponibles** (sous le critère d'un sur cinq) ; les 5 indisponibles sont ceux du 6 novembre, « périmés » avec leur raison (une équipe joue ce week-end) ; 43 références de marché ; 0 ligne inutilisable |
| Traçage live | **41 prédictions écrites** à 13:04 UTC, toutes avant leur coup d'envoi ; **2 refusées** (coups d'envoi de 12:30 et 13:00 UTC, déjà passés) ; `ops.prediction` : 89 lignes live, toutes avec leur identifiant API, aucune écrite après le coup d'envoi |
| API | `/health` : `ok`, base `ok`, modèle final chargé ; `/data/freshness` : top 5 complet jusqu'au 29 ou 30 octobre selon le championnat ; **403** pour un jour passé en live (2026-10-30) et pour les saisons 2025-26 et 2026-27 en rejeu (ADR-0045) |
| Interface, live (31/10/2026) | 85 matchs : 22 🟢 disponibles, 63 hors périmètre ; Bologna – Monza : E[T] 2,76, λ 1,86 et 0,90, P(T > 2,5) 52,2 %, [1 ; 5] à 87,5 %, marché 52,3 % ; **prédiction n° 132 renvoyée telle quelle** (tracée par la commande à 13:04 UTC : mêmes valeurs) |
| Interface, rejeu (18/05/2025) | 88 matchs : 24 disponibles, 64 hors périmètre (comme le 2026-10-04) ; Everton – Southampton : E[T] 2,87, P(T > 2,5) 54,7 %, score réel 2 – 0, modèle du pli `rejeu-2024-m3_g0g2`, prédiction n° 78 renvoyée telle quelle |
| Interface, écran « Modèle » | carte, validation, limites, courbe d'apport, fraîcheur ; `API : ok ; base : ok` |

**Temps mesurés** (portable, `AppTest` sur la vraie API) :

| Opération | Live | Rejeu |
|---|---|---|
| Écran « Matchs » à froid (contexte de l'API) | 11,8 s | 16,7 s |
| Écran « Matchs » à chaud | 0,24 s | 0,27 s |
| Clic « Prédiction » | 4,9 s | 2,1 s |
| Écran « Modèle » | 10,3 s | — |
| Commande sans service | `live --days 7 --save` : 76 s | `predict` d'une journée : 28 s |

Les temps à froid sont deux à trois fois ceux du 2026-10-04 (8,0 s ; `predict` 9 s). Cause non mesurée ; hypothèse : la table des matchs contient maintenant l'historique ouvert (ADR-0045) et la superposition de football-data. Ils restent sous le délai de 60 s du client de l'interface.

## Limites connues

- Le test automatisé n'utilise pas le vrai modèle de rejeu (lignes d'apprentissage synthétiques) : la reproduction exacte du rejeu est contrôlée sur données réelles par `inference check` (étape 11), pas en CI.
- Le live de bout en bout est vérifié à la main (section 3), pas en CI : il dépend des fichiers du jour de football-data et de l'heure.
- Le graphique de l'écran « Détail » n'est pas rendu par `AppTest` : ses données le sont (étape 13).
