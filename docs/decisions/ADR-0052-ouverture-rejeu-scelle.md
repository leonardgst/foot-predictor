# ADR-0052 — Ouverture du rejeu des saisons scellées, garde du modèle H2 testé et évaluation du journal prospectif H1

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0011 (règle 2, rejeu et live), ADR-0012 (règles 4 et 5), ADR-0044 (garde H1), ADR-0045 (ouverture à l'inférence, rejeu fermé jusqu'au test H2), ADR-0047 (D6), ADR-0050 (test scellé H2), ADR-0051 (H2 en rejeu) ; cadrage de la partie 6, sous-étape 6.13 ; E.2 du rapport de cadrage ; `docs/resultats/test_scelle_h2.md`

## Contexte

- **Le test scellé H2 est fait** (6.12, rapport `scelle-h2-20261101T153604`, une seule fois) : le journal `reports/sealed_tests.md` porte sa ligne « évaluation terminée ». L'ADR-0045 avait fermé le rejeu des saisons scellées « jusqu'au test de H2 » et prévu « une nouvelle ADR, après ce test » pour l'ouvrir. Le gel `pre-scelle-h2` est levé (PR #110).
- **Ce que la fermeture protégeait** : le second test, qui réutilisait les matchs scellés. Cette raison a disparu ; aucun autre test n'est prévu sur ces matchs (ADR-0047).
- **État du code** : `inference.models.check_replay_season` refuse toute saison à partir de 2025-26 ; `predict_match` ne sert `actual_score` qu'avant le 1er juillet 2025 ; `features/sources.load_lineups` et `load_team_sheets` n'ont pas d'ouverture à l'inférence (H2 n'avait pas de live). Sans ces compositions, un rejeu H2 des matchs scellés est impossible.
- **Le modèle de rejeu des saisons scellées est celui du test** (ADR-0047, D6) : appris sur 2015-16 à 2024-25 par la procédure de `scelle_h1.yaml` (H1) et de `scelle_h2.yaml` (H2). `protocol.Fold(S)` apprend sur 2015-16 à S − 1 : le pli de 2025-26 est exactement ce modèle ; 2026-27 n'a pas de pli propre dans le jeu de développement.
- **Journal prospectif H1** : 89 prédictions live écrites avant le coup d'envoi (`ops.prediction`, 22 au 31 octobre, 7 jours de matchs, un seul modèle : `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`, appris jusqu'au 18 octobre). Leurs scores sont des matchs scellés, non lus jusqu'ici (ADR-0045). Aucun n'est dans `staging` (brut gelé le 22 octobre) : il faut les résultats de football-data. Le critère E.2 demande au moins 8 journées tracées.
- **Le gel ne protège plus le modèle H2 testé** : les chemins `modeling/` et `features/` peuvent changer ; la garde H1 (ADR-0044) ne couvre que H1.

## Options envisagées

**Ce que sert le rejeu des saisons scellées**

1. **Prédictions + score réel, sans cotes.** Comme pour 2021-22 à 2024-25, moins les cotes. La cote avant clôture des matchs scellés a déjà été publiée en agrégat par le test (H1 et H2) ; `load_odds` reste fermée (ADR-0045). *Retenue (choix de l'utilisateur, 2026-11-01).*
2. Prédictions + score réel + cotes. Ouvre `load_odds` au scellé : plus de code, un nouveau risque de fuite à tester.
3. Prédictions seulement. Le rejeu perd son intérêt (comparer à la réalité).

**Garde du modèle H2 testé**

1. **Une garde chiffrée, comme celle de H1.** *Retenue.*
2. Seulement la règle « aucun modèle modifié ensuite ».

**Évaluation du journal prospectif**

1. **Une commande, un premier relevé maintenant** (une collecte football-data, accord de l'utilisateur), à renouveler quand les 8 journées d'E.2 sont atteintes. *Retenue.*
2. Coder la commande et évaluer plus tard.

## Décision

### 1. Ouverture du rejeu des saisons scellées (H1 et H2)

- **Condition codée sur le journal, pas sur une constante** : les saisons 2025-26 et 2026-27 s'ouvrent au rejeu **si et seulement si** `reports/sealed_tests.md` porte « évaluation terminée » pour `experiments/scelle_h2.yaml` (`seal.sealed_test_finished`). Sans ligne, le comportement de l'ADR-0045 est inchangé (refus).
- **Modèle** : celui du test. La saison 2026-27 emploie le modèle du pli de 2025 (`min(S, 2025)` pour l'apprentissage et le cache) ; la carte porte `replay_season` = 2025, le pli d'apprentissage. Aucun modèle n'est appris avec un match scellé : le jeu d'apprentissage reste celui de développement.
- **Ce qui est servi** : la prédiction, le score réel à 90 minutes des matchs joués, le log-loss de la journée. **Les cotes restent fermées** : `market_reference` reste vide pour tout match à partir du 1er juillet 2025 en rejeu ; `load_odds` n'est pas ouverte.
- **Compositions (H2)** : `load_lineups` et `load_team_sheets` reçoivent `opened_for_inference`, réservé à `inference/` (test d'architecture étendu) et **refusé tant que le test scellé H2 n'est pas terminé au journal**. Aucune ligne de journal par lecture, comme pour `load_matches` (ADR-0045).
- **Inchangé** : `features build` sans `--sealed-test`, `evaluate`, notebooks, `modeling/` gardent le filtre du scellé ; le live reste en 2026-27 sans score ni cote d'un match joué ; un jour du rejeu à venir n'a pas de score.

### 2. Garde du modèle H2 testé (comme la garde H1 de l'ADR-0044)

Une PR qui touche `modeling/models/` ou `features/` montre que **le rejeu des saisons scellées reproduit les prédictions des tests** :

- `uv run python -m foot_predictor.inference check --only sealed_replay` : sur des jours de 2025-26 et de 2026-27 (premiers, milieux, derniers jours, jours chargés), les prédictions de rejeu de `M3_G0G2` (H1) et de `M3_H2` (H2) sont **identiques** (λ et loi du total, au plus 1e-12 près) à celles des rapports `scelle-h1-20261022T120542` et `scelle-h2-20261101T153604`, retrouvés par `match_id` ;
- les empreintes sha256 des fichiers de prédictions, relevées ici, identifient les rapports : H1 `14b103d3292cef4b3055034b8aea88a368f0b37b99fd77e66c9c1f2cdd560e44` ; H2 `7eab862d1c548adb5b96ff3dd80a03f89d6f1c44496049dfc5c68f748f0d9421` ;
- en plus, `inference check --only replay` (jours de développement) reproduit toujours le rejeu H1 et H2.

Le contrôle lit les fichiers `data/experiments/<id>/predictions.parquet` (ignorés par Git, copie facultative sur `D:`). S'ils manquent, il le dit et ne passe pas. La garde est une règle de `CLAUDE.md`.

### 3. Évaluation du journal prospectif H1

Commande `uv run python -m foot_predictor.inference prospective [--output ...]` : les prédictions `live`, horizon H1, statut `available`, de `ops.prediction`, contre les résultats réels.

- **Résultats** : ceux de football-data, superposés en mémoire (ADR-0042), jamais écrits dans `staging`. Un match est apparié par son identifiant API (colonne `api_fixture_id` de la prédiction), puis par sa clé de football-data. Un match sans résultat est compté « pas joué ou résultat absent », jamais deviné.
- **Population** : les prédictions écrites **avant** le coup d'envoi (`created_at < kickoff_utc`) ; celles qui ne le sont pas sont comptées et écartées. Une **journée** est un jour de match avec au moins une prédiction tracée ; E.2 demande au moins 8.
- **Mesures** (protocole de l'ADR-0037, 10 000 rééchantillonnages, graine 20260930, blocs = jours) : log-loss du total, RPS, Brier de P(T > 2,5), couverture observée de [q10 ; q90] contre l'annoncée, pente et ordonnée de calibration (descriptives, n petit).
- **Référence** : B1 de fenêtre 3 (celle du test), recalculée sur l'historique ouvert à l'inférence jusqu'au jour de chaque match (moyenne par championnat et côté des trois dernières saisons, `season_year` > dernière − 3). Écart apparié `B1 − modèle` avec son intervalle par blocs de jours. Le marché n'est pas une référence ici (cote avant clôture non conservée dans `ops.prediction`).
- **Règle de lecture, fixée avant tout résultat** : un relevé **descriptif**, sans règle de décision ; l'écart à B1 n'a de valeur qu'avec son intervalle ; aucun modèle n'est changé, réentraîné ou recalibré à partir de ce relevé ; un relevé est refait à chaque nouvelle collecte, tous conservés. Avant 8 journées, aucune conclusion de performance n'est publiée, seulement les décomptes. Le critère E.2 porte sur le **traçage**, pas sur la performance.
- **Collecte** (accord de l'utilisateur, 2026-11-01) : `collect.football_data.live fixtures --max-requests 1` puis `season --season 2026 --max-requests 10`. Aucune requête API-FOOTBALL.

## Conséquences

- **Fichiers** :
  - `seal.py` : constante `H2_SEALED_EXPERIMENT`, `check_opened_for_h2_inference` ;
  - `features/sources.py` : `opened_for_inference` pour les compositions et feuilles de match ;
  - `inference/` : `models.py`, `predict.py`, `context.py`, `check.py`, `__main__.py`, nouveau `prospective.py` ;
  - `api/`, `ui/` : textes et refus de dates mis à jour ;
  - tests : porte, architecture, rejeu des saisons scellées, évaluation prospective, `CLAUDE.md` ;
  - documentation : README de l'étape 11, état, retour du lot.
- **Garde H1** : aucun modèle ni aucune variable ne change. Les prédictions du modèle final H1 (`scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`) ne bougent pas ; `check --only replay` reproduit le rejeu de développement.
- **On s'interdit** : d'ouvrir `load_odds` au scellé ; de réentraîner ou de recalibrer un modèle à partir du rejeu des saisons scellées ou du journal prospectif ; de tirer une conclusion de performance du journal avant 8 journées ; de servir un score avant la ligne du journal du test H2.
- **Critère de révision** : une prédiction de rejeu d'un match scellé qui diffère de celle du test (garde du §2), une cote d'un match scellé servie, ou une composition scellée lue hors de `inference/`. Le constater dans une nouvelle ADR.
- **Ce qui reste ouvert** : le live H2 (réabonnement, hors périmètre, ADR-0010) ; l'ADR n'ajoute aucune dépendance.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
