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

## Limites connues

- Le test automatisé n'utilise pas le vrai modèle de rejeu (lignes d'apprentissage synthétiques) : la reproduction exacte du rejeu est contrôlée sur données réelles par `inference check` (étape 11), pas en CI.
- Le mode live de bout en bout attend la phase B (sous-étape 5.15, données réelles après le test scellé).
- Le graphique de l'écran « Détail » n'est pas rendu par `AppTest` : ses données le sont (étape 13).
