# Étape 11 : inférence (jalon J7)

Mode d'emploi de l'inférence : variables d'un match quelconque, modèles actif et de rejeu, matrice de disponibilité, prédiction, traçabilité. Décision : **ADR-0040**. Le code vit dans `src/foot_predictor/inference/` ; il **importe** `features/` et `modeling/` (figés par le tag `pre-scelle-h1`) sans jamais les modifier.

## En bref

- **Même fonction que l'entraînement** : les variables d'un jour J viennent de `features.dataset.build_frame`, appelée sur la table des matchs tronquée au jour J, les matchs cibles à 0-0 sans statistiques ; un jour à la fois ; colonnes d'après-match retirées (`goals_for`, `goals_against`, `shots_source`). Contrôle réel : 622 lignes identiques au bit près au jeu `ds-2026-09-30-ba2b91f7`.
- **Modèle de rejeu** de la saison S : le pli S (appris sur 2015-16 à S − 1, procédure de `experiments/scelle_h1.yaml`), mis en cache dans `models/rejeu/<S>/`. Contrôle réel : écart nul avec les prédictions de l'évaluation (7 156 matchs).
- **Modèle actif** (live) : celui du registre `ops.model_registry`, allégé au chargement (25 Mo → 576 Ko, prédictions identiques).
- **Disponibilité** : chaque variable requise est présente, manquante (raison) ou périmée (source en retard) ; une seule non présente ⇒ `unavailable`, aucune prédiction.
- **Traçabilité** : `ops.prediction` (migration 0008), idempotente ; live écrit avant le coup d'envoi seulement.
- **Scellé** : rejeu ouvert sur 2021-22 à 2024-25 ; toute date à partir du 1er juillet 2025 refusée tant que le test scellé n'est pas terminé.

## Commandes

```bash
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay            # une journée
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --json     # réponse complète
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --save     # + ops.prediction
uv run python -m foot_predictor.inference models                 # modèle actif et modèles de rejeu en cache
uv run python -m foot_predictor.inference models --register      # inscription dans ops.model_registry
uv run python -m foot_predictor.inference check                  # contrôles réels (environ 2 min)
```

| Option | Rôle |
|---|---|
| `--mode replay\|live` | rejeu (modèle du pli de la saison, score réel affiché) ou live (modèle actif, matchs à venir) |
| `--competition <id>` | filtre sur l'identifiant **interne** du championnat (plusieurs fois possible) |
| `--match <id>` | un match (identifiant interne) |
| `--save [--force]` | écrit dans `ops.prediction` ; sans `--force`, une prédiction existante est gardée |

Codes de sortie de `predict` : 0 (réponses rendues, disponibles ou non), 3 (date refusée : scellé, saison de rejeu fermée, live dans le passé).

## Réponse d'un match

| Champ | Contenu |
|---|---|
| `status` | `available`, `unavailable`, `out_of_scope` (D2, coupe, barrage, autre championnat), `excluded`, `h2_unavailable` |
| `reasons` | raisons lisibles (vide si disponible) |
| `availability` | une entrée par variable requise et par équipe : statut, valeur, raison, date de la source |
| `prediction` | λ domicile et extérieur, `expected_total`, `total_distribution` (0 à 9 et « 10+ »), `p_over_2_5`, `interval` (`low`, `high`, `announced_coverage`) ; absente si le match n'est pas disponible |
| `actual_score` | en rejeu, avant le 1er juillet 2025 |
| `market_reference` | probabilité implicite de plus de 2,5 buts avant clôture (référence, jamais une variable, ADR-0036) |
| `model_version`, `data_version`, `data_complete_until` | traçabilité |

## Contrôles sur données réelles (`check`)

| Contrôle | Rapport | Résultat du 2026-09-30 |
|---|---|---|
| `rows` : lignes d'inférence contre le jeu d'entraînement | `reports/inference/lignes_2026-09-30.md` | 17 jours, 622 lignes identiques au bit près |
| `replay` : modèles de rejeu contre l'évaluation | `reports/inference/rejeu_2026-09-30.md` | écart nul, 4 saisons, 7 156 matchs |
| `predictions` : journées de rejeu contre l'évaluation | `reports/inference/predictions_2026-09-30.md` | 8 journées, λ à 9e-16 près, log-loss identique |

## Tirs de football-data en live (`shots_check`, 5.7)

```bash
uv run python -m foot_predictor.inference.shots_check   # 30 s : écrit reports/inference/tirs_football_data.json et docs/resultats/tirs_live.md
```

Effet, sur les 4 plis de développement, d'un historique dont les tirs viennent de football-data (décision 12, ADR-0035) : la saison S seule (situation du live) ou toute l'histoire (extrême), même modèle de rejeu. Résultat du 2026-10-01 : écart de log-loss −0,00002 [−0,00021 ; +0,00018] pour le live, +0,00086 [−0,00012 ; +0,00189] pour l'extrême ; aucun championnat significatif après correction de Holm. Pas de recalibration (ADR-0041) ; mesure à refaire avec la même règle quand l'historique de football-data s'allongera.

## Sources live : football-data (5.10, ADR-0042)

Après le gel, le calendrier 2026-27 de `staging` reste figé (identifiants justes, dates souvent fausses, aucun résultat). Le live le complète par football-data, **en mémoire** (`inference/live_sources.py`) : `load` et le référentiel ne changent pas.

```bash
# collecte (bruts externes, ADR-0024 ; plafond obligatoire, verrou, journal, aucun écrasement)
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1          # prochains matchs
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10   # phase B seulement
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1 --dry-run   # plan, rien d'envoyé
# répétition sur la période de développement (gel simulé, « aujourd'hui » simulé)
uv run python -m foot_predictor.inference check --only live
```

| Étape | Règle |
|---|---|
| Fichiers | prochains matchs : toutes les versions de `football_data/fixtures/` (la plus récente fait foi) ; résultats : dernière version de `football_data/csv/season=S/<div>__*.csv` |
| Appariement | (championnat, saison, domicile, extérieur), **sans la date**, matchs de saison régulière seulement ; noms par `football_data_team_ids.yaml` |
| Jamais deviné | nom absent du YAML, affiche ambiguë, match introuvable : ligne comptée, matchs candidats `unavailable` avec la raison |
| Superposition | match déjà joué dans `staging` : valeurs de l'API ; sinon buts, tirs et date réelle de football-data ; match à venir : date et heure réelles (heure de Londres convertie en UTC), cote avant clôture comme référence |
| Fraîcheur | par championnat : complet jusqu'à la veille du premier match sans résultat ; sinon variables « périmées », pas de prédiction |
| Scellé | `season` refuse 2025-26 et après tant que le test scellé n'est pas fait |

**Répétition du 2026-10-04** (`reports/inference/live_repetition_2026-10-04.md`) : gel simulé au 15/02/2024, « aujourd'hui » le 09/03/2024 : 335 résultats rétablis sur 335, 0 score différent de l'API, 0 ligne inutilisable ; lignes du jour identiques pour les buts et l'Elo, seules les variables de tirs diffèrent (attendu, ADR-0041) ; 20 matchs du top 5 sur 20 disponibles ; superposition en 0,3 s.

Le branchement sur l'API et l'interface en mode live (commande `live --days`) est la sous-étape 5.14, en phase B.

## Temps mesurés (portable, 2026-09-30)

| Opération | Temps |
|---|---|
| Table des matchs (`load_matches`) | 3,2 s |
| Lignes d'un jour, à froid | 3,4 à 5,3 s |
| Lignes d'un jour, à chaud (cache) | < 1 ms |
| Modèle de rejeu d'une saison (entraînement et cache) | 0,6 à 1,7 s |
| `predict` d'une journée de 77 matchs, commande complète à froid | 8,3 s |
| Journée de rejeu, contexte chargé | 2 à 3 s |

## Limites connues

- Le live réel attend la phase B (après le test scellé) ; en phase A il est testé sur des données synthétiques et par la répétition sur la période de développement, avec un « aujourd'hui » simulé.
- Fraîcheur par championnat, règle prudente : un match reporté sans nouvelle date bloque son championnat jusqu'à son résultat (ADR-0042, critère de révision).
- Un seul jour est calculé à la fois (règle d'exactitude) : une plage de dates coûte quelques secondes par jour à froid.
- Les identifiants de championnat de `--competition` sont internes ; l'API (étape 12) les liste.
