# Étape 11 : inférence (jalon J7)

Mode d'emploi de l'inférence : variables d'un match quelconque, modèles actif et de rejeu, matrice de disponibilité, prédiction, traçabilité. Décisions : **ADR-0040**, **ADR-0045** pour l'ouverture du scellé (5.13), **ADR-0051** pour l'horizon H2 en rejeu (6.10). Le code vit dans `src/foot_predictor/inference/` ; il **importe** `features/` et `modeling/` sans jamais les modifier (règle de la phase A, gel `pre-scelle-h1` ; la porte `features/sources.py` a reçu l'option d'ouverture en 5.13).

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
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --horizon H2   # avec la composition (6.10)
uv run python -m foot_predictor.inference predict --date 2024-05-19 --mode replay --save     # + ops.prediction
uv run python -m foot_predictor.inference live --days 7 [--save]   # live (5.14) : rapport ; --save trace les disponibles
uv run python -m foot_predictor.inference models                 # modèle actif et modèles de rejeu en cache
uv run python -m foot_predictor.inference models --register      # inscription dans ops.model_registry
uv run python -m foot_predictor.inference models --activate <version>   # inscrit models/<version>/ et le rend actif
uv run python -m foot_predictor.inference check                  # contrôles réels (environ 2 min)
uv run python -m foot_predictor.inference check --only rows-h2       # sur demande (6.10) : lignes H2 (environ 6 min)
uv run python -m foot_predictor.inference check --only replay-h2     # sur demande : modèles de rejeu H2 (quelques secondes)
uv run python -m foot_predictor.inference check --only predictions-h2   # sur demande : journées de rejeu H2 (environ 4 min)
uv run python -m foot_predictor.inference check --only rows-scelle   # sur demande : période scellée, lecture journalisée
```

| Option | Rôle |
|---|---|
| `--horizon H1\|H2` | H1 (défaut) ; H2 ajoute la composition annoncée, en rejeu seulement (en live : `h2_unavailable`) |
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
| Fraîcheur (ADR-0046) | **par équipe, approchée** : un match A–B du jour J est périmé si son championnat n'est complet que jusqu'à C < J − 1 **et** si A ou B a un match de championnat entre C et J ; sinon il est prédit (Elo exact, glissants approchés : leur a priori μ manque les derniers résultats du championnat) |
| Part d'indisponibles | comparée au critère de l'ADR-0011 : plus d'un match du top 5 sur cinq |
| API | contexte reconstruit quand change le chargement, un fichier de football-data ou le jour ; `/data/freshness` donne la fraîcheur de chaque championnat du top 5 |

**Premier live, 2026-10-22** (rapport `reports/inference/live_2026-10-22.md`) :

- collecte : 11 requêtes (1 + 10), 11 fichiers stockés ; **0 ligne inutilisable** : les noms d'équipes de 2026-27, promus compris, sont dans le YAML ;
- superposition : 8 résultats depuis le gel ; tous les championnats complets jusqu'au 2026-10-22 ;
- le fichier des prochains matchs du jeudi ne contenait encore que les matchs des 20 et 21 octobre (déjà joués) : 0 date réelle à venir, 0 cote ; les matchs du week-end gardent leur date figée de l'API ;
- **56 matchs du top 5 sur 7 jours, 5 disponibles, 91 % indisponibles** (« variables d'historique périmées ») : seuls les matchs du lendemain ont tout leur historique. **Le critère de révision de l'ADR-0011 est atteint dès le premier jour** (décision ouverte) ;
- API et interface en live sur les vraies données : 5 matchs disponibles le 23 octobre, 20 « périmés » le 24 ; 403 pour un jour passé en live et pour un jour scellé en rejeu ;
- **5 prédictions live tracées** (matchs du 23 octobre), écrites à 14:11 UTC pour des coups d'envoi de 18:30 à 19:00 UTC, avec leur identifiant API et le modèle final : début du journal prospectif.

**Fraîcheur par équipe, même jour** (ADR-0046, mêmes fichiers, aucune nouvelle requête) :

- mesure préalable sur 2023-24 (collecte simulée le jeudi, 1 455 matchs de week-end) : 1 455 prévisibles contre 1 avec la règle par championnat ; écart maximal 0,0011 sur λ et 0,0004 sur P(T > 2,5) ; tolérance fixée ensuite à 0,005 et 0,002 ;
- répétition (`reports/inference/live_repetition_2026-10-22.md`, gel simulé au 2024-02-15, « aujourd'hui » 2024-03-09) : sur les sept jours suivants, 24 matchs déclarés disponibles par équipe (0 par championnat), **Elo identique pour les 24**, écart maximal 0,0005 sur λ et 0,00015 sur P(T > 2,5) : **conforme** ;
- live : **48 matchs du top 5 sur 56 disponibles, 14 % d'indisponibles** (sous le critère d'un sur cinq) : toute la journée du 23 au 26 octobre ; les 8 matchs des 27 et 28 octobre restent périmés, leurs équipes jouant le week-end (raison nommée) ;
- **48 prédictions live tracées** (43 nouvelles, les 5 de vendredi gardées), toutes avant le coup d'envoi, avec leur identifiant API ; `data_complete_until` = 2026-10-22 pour toutes.

**Deuxième live, 2026-10-31** (samedi, 5.15 ; rapport `reports/inference/live_2026-10-31.md`, détail dans l'étape 14, section 3) :

- collecte à 13:03 UTC : 11 requêtes (1 + 10), 11 fichiers ; 127 résultats superposés depuis le gel, 101 dates réelles ; 0 ligne inutilisable ;
- championnats du top 5 complets jusqu'au 29 ou 30 octobre ;
- **48 matchs du top 5 sur 7 jours, 43 disponibles, 10 % d'indisponibles** : tout le week-end du 31 octobre au 2 novembre est prévisible ; les 5 matchs du 6 novembre restent « périmés » (leurs équipes jouent ce week-end) ;
- **41 prédictions live tracées**, toutes avant le coup d'envoi ; 2 refusées, leurs matchs ayant commencé à 12:30 et 13:00 UTC : collecter plus tôt le samedi (le fichier des prochains matchs paraît le vendredi après-midi) ;
- `ops.prediction` : 89 lignes live au total.

## Horizon H2 en rejeu (6.10, ADR-0051)

H2 = le modèle H1 plus la qualité du onze annoncé (G5) : **M3 sur G0 + G1 + G2 + G5** (ADR-0050). Il n'existe qu'en **rejeu** : après la fin de l'abonnement, aucune composition n'arrive plus (ADR-0010).

- **Modèle de rejeu H2 de la saison S** : le pli S, appris sur 2015-16 à S − 1 par la ligne `M3_H2` de `experiments/scelle_h2.yaml` (rodage de G5 : apprentissage dès 2016-17), sur le jeu `ds-2026-11-01-e0defb32`. Cache : `models/rejeu/h2/<S>/`, version `rejeu-<S>-m3_h2`. Contrôle réel : prédictions **identiques** à celles de l'expérience `structures-h2` (7 135 matchs, écart nul).
- **Variables** : `build_frame_h2` appelée sur la table des matchs, les compositions et les feuilles de match tronquées au jour J (un jour à la fois). Compositions lues par la porte (`load_lineups`, `load_team_sheets`) à la **première demande H2** seulement (environ 2 millions de lignes, 17 s). Pour le match cible, on garde le onze annoncé, le poste et l'entraîneur ; on retire minutes, note, remplaçant, capitaine (défense en profondeur : G4 à G6 ne lisent déjà que des jours strictement antérieurs).
- **Disponibilité** : mêmes règles que H1. Raisons propres à G5 : onze incomplet ou absent de la feuille de match, titulaire sans poste ni note antérieure, moins de 10 matchs d'historique du club, date de naissance manquante. Jamais de valeur de remplacement.
- **Live** : `h2_unavailable` avec la raison (compositions plus fournies, ADR-0010), sans modèle ni lecture des compositions ; un match hors périmètre ou exclu garde son statut de H1. API : 200 sur `/matches` et `/availability`, 409 sur `POST /predictions`.
- **Scellé** : le rejeu H2 d'une saison scellée est refusé comme celui de H1, jusqu'au test scellé de H2 (ADR-0045). Les compositions passent par la porte, scellé filtré en SQL, sans ouverture à l'inférence.

| Contrôle H2 (sur demande) | Rapport | Résultat du 2026-11-01 |
|---|---|---|
| `rows-h2` : lignes d'inférence contre le jeu H2 `e0defb32` | `reports/inference/lignes_h2_2026-11-01.md` | 17 jours, 622 lignes identiques au bit près (92 colonnes), chargement n° 7 des deux côtés ; 15 à 23 s par jour |
| `replay-h2` : modèles de rejeu contre `structures-h2` (`M3_H2`) | `reports/inference/rejeu_h2_2026-11-01.md` | écart nul, 4 saisons, 7 135 matchs (demi-vies 240, 120, 240, 240) |
| `predictions-h2` : journées de rejeu contre `structures-h2` | `reports/inference/predictions_h2_2026-11-01.md` | 8 journées, λ à 9e-16 près, log-loss identique |

**Garde H1** : `check --only replay` (H1) reproduit toujours le rejeu, avec les mêmes modèles ; aucun fichier de `modeling/`, `features/`, `seal.py` ni `experiments/` n'a changé (`git diff --stat pre-scelle-h2` vide).

**Ce que le test ne détecte pas** : une mutation qui désactive le retrait des colonnes d'après-match du match cible n'est détectée que par le test unitaire de `lineups_for_day`, pas par le test « ce que le match produit ne change rien », parce que G5 ne lit que des notes antérieures. Le retrait est une protection de plus, pas la seule.

## Temps mesurés (portable, 2026-09-30)

| Opération | Temps |
|---|---|
| Table des matchs (`load_matches`) | 3,2 s |
| Lignes d'un jour, à froid | 3,4 à 5,3 s |
| Lignes d'un jour, à chaud (cache) | < 1 ms |
| Modèle de rejeu d'une saison (entraînement et cache) | 0,6 à 1,7 s |
| `predict` d'une journée de 77 matchs, commande complète à froid | 8,3 s |
| Journée de rejeu, contexte chargé | 2 à 3 s |
| **H2** : lignes d'un jour, à froid (3 tables tronquées, `build_frame_h2`) | 15 à 23 s |
| **H2** : compositions et feuilles de match (première demande) | 17 s |
| **H2** : modèle de rejeu d'une saison | environ 1 s |
| **H2** : journée de rejeu complète, contexte chargé, à froid | 17 à 39 s |

## Limites connues

- Fraîcheur par équipe (ADR-0046) : les glissants d'un match prédit alors que son championnat n'est pas complet sont **approchés** (a priori μ du championnat), dans la tolérance vérifiée par la répétition ; une prédiction faite ainsi se reconnaît à `data_complete_until` < J − 1. Un match dont une équipe a joué depuis la dernière mise à jour attend la suivante.
- Fraîcheur par championnat, règle prudente : un match reporté sans nouvelle date bloque son championnat jusqu'à son résultat (ADR-0042, critère de révision).
- Un seul jour est calculé à la fois (règle d'exactitude) : une plage de dates coûte quelques secondes par jour à froid pour H1, une vingtaine pour H2.
- H2 : sans aucune apparition de joueur identifiée dans l'historique, `compute_xi_quality` (chemin gelé de `features/`) échoue au lieu de rendre des valeurs vides ; non atteignable sur les données réelles du rejeu, et une base sans composition donne un 503 explicite (ADR-0051).
- H2 : le gain mesuré est minuscule (ADR-0048) ; l'écart H2 − H1 d'un match n'est pas une preuve que H2 avait raison.
- Les identifiants de championnat de `--competition` sont internes ; l'API (étape 12) les liste.
