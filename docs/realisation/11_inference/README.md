# Étape 11 : inférence (jalon J7)

Mode d'emploi de l'inférence : variables d'un match quelconque, modèles actif et de rejeu, matrice de disponibilité, prédiction, traçabilité. Décisions : **ADR-0040**, et **ADR-0045** pour l'ouverture du scellé (5.13). Le code vit dans `src/foot_predictor/inference/` ; il **importe** `features/` et `modeling/` sans jamais les modifier (règle de la phase A, gel `pre-scelle-h1` ; la porte `features/sources.py` a reçu l'option d'ouverture en 5.13).

## En bref

- **Même fonction que l'entraînement** : les variables d'un jour J viennent de `features.dataset.build_frame`, appelée sur la table des matchs tronquée au jour J, les matchs cibles à 0-0 sans statistiques ; un jour à la fois ; colonnes d'après-match retirées (`goals_for`, `goals_against`, `shots_source`). Contrôle réel : 622 lignes identiques au bit près au jeu du chargement en vigueur (`ds-2026-10-22-bf786ef1`, chargement n° 7).
- **Modèle de rejeu** de la saison S : le pli S (appris sur 2015-16 à S − 1, procédure de `experiments/scelle_h1.yaml`), mis en cache dans `models/rejeu/<S>/`. Contrôle réel : écart nul avec les prédictions de l'évaluation (7 156 matchs).
- **Modèle actif** (live) : celui du registre `ops.model_registry`, allégé au chargement (25 Mo → 576 Ko, prédictions identiques). Depuis 5.13 : le modèle final H1, `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle` (ADR-0044).
- **Disponibilité** : chaque variable requise est présente, manquante (raison) ou périmée (source en retard) ; une seule non présente ⇒ `unavailable`, aucune prédiction.
- **Traçabilité** : `ops.prediction` (migration 0008), idempotente ; live écrit avant le coup d'envoi seulement ; identifiant API du match recopié depuis la réponse (E-058), stable quand `match_id` ne l'est pas.
- **Scellé** (ADR-0045) : le test scellé H1 étant terminé, la table des matchs est **ouverte à l'inférence**, comme historique des variables du live. Le rejeu reste limité à 2021-22 à 2024-25 **jusqu'au test scellé de H2** ; le score réel et la cote d'un match scellé ne sont jamais servis.

## Commandes

```bash
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay            # une journée
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --json     # réponse complète
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --save     # + ops.prediction
uv run python -m foot_predictor.inference live --days 7 [--save]   # live (5.14) : rapport ; --save trace les disponibles
uv run python -m foot_predictor.inference models                 # modèle actif et modèles de rejeu en cache
uv run python -m foot_predictor.inference models --register      # inscription dans ops.model_registry
uv run python -m foot_predictor.inference models --activate <version>   # inscrit models/<version>/ et le rend actif
uv run python -m foot_predictor.inference check                  # contrôles réels (environ 2 min)
uv run python -m foot_predictor.inference check --only rows-scelle   # sur demande : période scellée, lecture journalisée
```

| Option | Rôle |
|---|---|
| `--mode replay\|live` | rejeu (modèle du pli de la saison, score réel affiché) ou live (modèle actif, matchs à venir) |
| `--competition <id>` | filtre sur l'identifiant **interne** du championnat (plusieurs fois possible) |
| `--match <id>` | un match (identifiant interne) |
| `--save [--force]` | écrit dans `ops.prediction` ; sans `--force`, une prédiction existante est gardée |

Codes de sortie de `predict` : 0 (réponses rendues, disponibles ou non), 3 (date refusée : scellé, saison de rejeu fermée, live dans le passé). `models --activate` : 2 si `models/<version>/` n'existe pas (aucune base ouverte).

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
| `rows` : lignes d'inférence contre le jeu d'entraînement | `reports/inference/lignes_2026-09-30.md` | 17 jours, 622 lignes identiques au bit près (jeu `ba2b91f7`) |
| `replay` : modèles de rejeu contre l'évaluation | `reports/inference/rejeu_2026-09-30.md` | écart nul, 4 saisons, 7 156 matchs |
| `predictions` : journées de rejeu contre l'évaluation | `reports/inference/predictions_2026-09-30.md` | 8 journées, λ à 9e-16 près, log-loss identique |

**Jeu de chaque contrôle** (E-058) : `rows` rapproche les lignes par (`match_id`, `team_id`), identifiants internes qui changent quand le brut grandit. Il compare donc au jeu du **chargement en vigueur** (`ROWS_DATASET_VERSION` = `ds-2026-10-22-bf786ef1`, chargement n° 7), et le rapport vérifie que jeu et `staging` viennent du même chargement : sinon, « CHARGEMENTS DIFFÉRENTS » et échec. `replay` et `predictions` gardent `ba2b91f7`, le jeu de l'évaluation qu'ils reproduisent (identifiants du top 5 inchangés depuis 2015-16).

**Relance du 2026-10-22** (`reports/inference/lignes_2026-10-22.md`) : 17 jours, 622 lignes identiques au bit près, chargement n° 7 des deux côtés ; le 2020-12-15, en écart de clés avec l'ancien jeu (E-058), est identique.

## Ouverture du scellé à l'inférence (5.13, ADR-0045)

| Élément | Règle |
|---|---|
| Porte | `load_matches(opened_for_inference=True)` : refusée **avant toute lecture** tant que le journal n'a pas « évaluation terminée » pour `experiments/scelle_h1.yaml` ; aucune ligne de journal ; incompatible avec `sealed_test` |
| Qui | `inference/` seulement (test d'architecture) ; jeux de données, évaluation, modèles et notebooks restent fermés jusqu'au test de H2 ; `load_odds` n'a pas d'ouverture |
| Contexte | `build_context` ouvre la table quand le test H1 est terminé (`history_opened`) |
| Lignes d'un jour scellé | `build_frame` avec son option `sealed_test=True` (même calcul ; c'est l'appel du jeu scellé), seulement pour une table ouverte et un jour à partir du 1er juillet 2025 |
| Rejeu | 2021-22 à 2024-25 ; saisons scellées refusées jusqu'au test de H2 (code 3, API 403) |
| Live | matchs à venir, historique complet, modèle final ; variables affichées agrégées (ADR-0012, règle 4) |

**Résultats du 2026-10-22** (base de travail, chargement n° 7) :

| Contrôle | Rapport | Résultat |
|---|---|---|
| `rows-scelle` : lignes d'inférence (table ouverte) contre le jeu scellé `ds-2026-10-22-94969da0` | `reports/inference/lignes_scelle_2026-10-22.md` | 8 jours de 2025-26 et 2026-27, 434 lignes **identiques au bit près**, environ 6 s par jour |
| `predictions` avec le contexte ouvert | `reports/inference/predictions_2026-10-22.md` | identique au rapport du 2026-09-30, hors titre et durées : l'ouverture ne change pas le rejeu |
| `models --activate` | — | `ops.model_registry` : actif = modèle final (avant : `scelle-h1-m3_g0g2-20260930-3c92fc80`) |
| `predict --date 2025-08-16 --mode replay` | — | refusé, code 3 (« sous scellés pour le rejeu jusqu'au test scellé de H2 ») |
| `predict --date 2026-10-24 --mode live` | — | 89 matchs : 69 hors périmètre, 20 du top 5 `unavailable` (« variables d'historique périmées » : `staging` complet jusqu'au 2026-10-18) ; modèle final ; 0 score et 0 cote servis |

- Le contrôle `rows-scelle` a été lancé avec le code de la branche `feat/11-ouverture-scelle` avant son premier commit : la ligne du journal (13:23 UTC) porte le commit de base, `8358549`.
- Les matchs à venir restent indisponibles tant que football-data n'est pas superposé en live (5.14) : c'est la règle de fraîcheur, pas un défaut.

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

## Live réel (5.14)

Une fois la table ouverte (ADR-0045), `build_context` superpose football-data à la saison du jour (dossier des bruts externes du worktree, `data/raw/football_data/`). L'API, la commande `predict --mode live` et la commande `live` voient donc la même table.

```bash
# 1. collecte (plafonds écrits dans la PR ; un fichier de moins de 6 h n'est pas redemandé)
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1                # prochains matchs
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10   # résultats
# 2. disponibilité des prochains jours, rapport reports/inference/live_<date>.md
uv run python -m foot_predictor.inference live --days 7
# 3. traçage prospectif : les prédictions disponibles du top 5, avant le coup d'envoi
uv run python -m foot_predictor.inference live --days 7 --save
```

| Règle | Détail |
|---|---|
| Quand collecter | football-data met à jour le fichier des prochains matchs le **vendredi après-midi** (week-end) et le **mardi** (milieu de semaine) ; les résultats environ deux fois par semaine |
| Ce qui est tracé | les prédictions **disponibles** des matchs du top 5 (`ops.prediction`, mode `live`) ; jamais une réponse indisponible (E-062), qui bloquerait par idempotence la prédiction écrite plus tard |
| Référence de marché | cote avant clôture du fichier des prochains matchs, pour un match à venir (ADR-0042) ; jamais une variable |
| Part d'indisponibles | comparée au critère de l'ADR-0011 : plus d'un match du top 5 sur cinq |
| API | contexte reconstruit quand change le chargement, un fichier de football-data ou le jour ; `/data/freshness` donne la fraîcheur de chaque championnat du top 5 |

**Premier live, 2026-10-22** (rapport `reports/inference/live_2026-10-22.md`) :

- collecte : 11 requêtes (1 + 10), 11 fichiers stockés ; **0 ligne inutilisable** : les noms d'équipes de 2026-27, promus compris, sont dans le YAML ;
- superposition : 8 résultats depuis le gel ; tous les championnats complets jusqu'au 2026-10-22 ;
- le fichier des prochains matchs du jeudi ne contenait encore que les matchs des 20 et 21 octobre (déjà joués) : 0 date réelle à venir, 0 cote ; les matchs du week-end gardent leur date figée de l'API ;
- **56 matchs du top 5 sur 7 jours, 5 disponibles, 91 % indisponibles** (« variables d'historique périmées ») : seuls les matchs du lendemain ont tout leur historique. **Le critère de révision de l'ADR-0011 est atteint dès le premier jour** (décision ouverte) ;
- API et interface en live sur les vraies données : 5 matchs disponibles le 23 octobre, 20 « périmés » le 24 ; 403 pour un jour passé en live et pour un jour scellé en rejeu ;
- **5 prédictions live tracées** (matchs du 23 octobre), écrites à 14:11 UTC pour des coups d'envoi de 18:30 à 19:00 UTC, avec leur identifiant API et le modèle final : début du journal prospectif.

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

- Règle de fraîcheur par championnat : un match du jour J n'est prédit que si **tous** les matchs d'avant J de son championnat ont un résultat. Avec football-data (résultats deux fois par semaine), seuls les matchs du lendemain d'une mise à jour sont prédits (91 % d'indisponibles le 2026-10-22) : critère de révision de l'ADR-0011 atteint, règle à revoir (décision ouverte).
- Fraîcheur par championnat, règle prudente : un match reporté sans nouvelle date bloque son championnat jusqu'à son résultat (ADR-0042, critère de révision).
- Un seul jour est calculé à la fois (règle d'exactitude) : une plage de dates coûte quelques secondes par jour à froid.
- Les identifiants de championnat de `--competition` sont internes ; l'API (étape 12) les liste.
