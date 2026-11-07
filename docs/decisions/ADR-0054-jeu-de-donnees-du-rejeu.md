# ADR-0054 — Jeu de données du rejeu H1 : un CSV complété à chaque passage

- **Statut** : acceptée
- **Date** : 2026-11-07
- **Référence** : ADR-0040 (inférence = même fonction), ADR-0045 et ADR-0052 (historique scellé et rejeu ouverts à `inference/`), ADR-0053 (planification du live, liste fermée de commandes), E-058 (identifiants internes instables) ; PR #115 (`rejeu-stats`)

## Contexte

- **`rejeu-stats` répond à une question, pas à toutes.** Il rejoue les 9 359 matchs depuis 2021-22 (environ 40 minutes) et n'en garde que des agrégats dans le rapport ; les lignes match par match restent dans un Parquet daté, sans les variables que le modèle a lues. Pour explorer ces données dans un notebook (refaire les tableaux, regarder les erreurs, croiser avec les variables), l'utilisateur veut un jeu de données stable qui grandit seul à chaque résultat nouveau (2026-11-07).
- **Le rejeu est déterministe.** Un match déjà rejoué donne la même ligne tant que le modèle de sa saison et son historique ne changent pas : seuls les matchs nouveaux demandent un calcul.
- **Les passages ne lancent qu'une liste fermée de commandes** (ADR-0053 : « on s'interdit d'étendre les passages à une autre commande sans une nouvelle ADR »). Une étape qui complète le jeu après chaque collecte de résultats est une telle extension.
- **Les `match_id` changent quand le brut grandit** (E-058) : ils ne peuvent pas servir de clé dans un fichier qui dure.

## Options envisagées

1. **Un Parquet par lancement de `rejeu-stats`** (l'existant). Ni les variables lues, ni mise à jour : chaque lancement refait 40 minutes.
2. **Une table `ops` dans Postgres.** Durable et requêtable, mais demande une migration, et le notebook devrait passer par la base : plus lourd que le besoin.
3. **Un fichier CSV (ou XLSX) complété à la main.** On oublierait de le lancer ; un notebook lirait un fichier en retard.
4. **Un CSV unique, complété par une commande incrémentale, lancée par les passages qui collectent des résultats.** *Retenue.*

Pour le format, un CSV plutôt qu'un XLSX : un notebook le lit directement, il s'agrandit sans dépendance nouvelle (pas d'`openpyxl`), et les flottants s'y relisent exactement (`float_precision="round_trip"`). Un XLSX se fabrique à partir de lui si Excel est utile.

## Décision

### Le fichier

`data/inference/jeu_rejeu_h1.csv` (et son `.meta.json` : date de mise à jour, version des données, modèle de chaque saison). **Une ligne par match** du top 5 joué depuis 2021-22 et rejoué en H1 (modèle du pli de la saison, modèle du test scellé pour 2025-26 et 2026-27, score réel, aucune cote). Colonnes :

- identité : jour, coup d'envoi, saison, championnat, journée, équipes, version du modèle et des données ;
- **variables lues par le modèle** : `home_<variable>` (ligne qui sert à prédire le λ du domicile) et `away_<variable>` ; `is_home` et `api_league_id` ne sont pas répétés. Chaque modèle de saison lit 11 variables par côté ; la demi-vie des moyennes glissantes (`_h120` ou `_h240`) dépend du pli (120 jours en 2022-23, 240 jours dans les autres), donc **une colonne reste vide pour une saison dont le modèle ne la lit pas** ;
- **prédictions finales** : λ des deux équipes, `p0` à `p10` (loi du total, `p10` = 10 buts ou plus), intervalle [q10 ; q90] et sa couverture annoncée, λ de B1 ;
- score réel, puis mesures de chaque match (celles de `rejeu_stats`), avancement dans la saison et `traced_live` (le match a aussi été prédit en live avant son coup d'envoi).

Le fichier contient des scores de matchs scellés : il reste dans `data/` (ignoré par Git, CLAUDE.md), jamais commité.

### La mise à jour

`python -m foot_predictor.inference jeu-rejeu` compare les matchs joués du périmètre aux lignes du fichier, **ne rejoue que les jours des matchs absents**, remplace une ligne de même clé (jour, championnat, équipe à domicile, équipe à l'extérieur), recalcule les colonnes dérivées sur tout le fichier et réécrit le CSV (fichier temporaire puis remplacement : jamais à moitié écrit). Garde-fous :

- **Un modèle qui change dans une saison arrête la commande** (`ModelChanged`) : on ne mélange pas deux modèles ; `--rebuild` refait tout.
- **Plafond de jours** (`--max-days`, 45 par défaut) : un passage planifié ne se met pas, par erreur, à refaire les 40 minutes du rejeu (le délai d'une étape est de 30 minutes). Le premier lancement se fait à la main avec `--max-days 0`.
- Aucune requête réseau, aucune écriture dans `ops.prediction` ni dans le brut ; la base est lue (table des matchs et journal prospectif, pour `traced_live`).

### Les passages

Nouvelle étape **jeu** : `inference jeu-rejeu`, ajoutée après les étapes existantes des deux passages qui collectent des résultats.

| Tâche | Étapes |
|---|---|
| `FootPredictor_live_mardi` | collecte, tracé, relevé, **jeu** |
| `FootPredictor_live_vendredi` | collecte, tracé, **jeu** |
| `FootPredictor_live_samedi` | tracé (inchangé : aucun résultat nouveau sans réseau) |

L'étape ne dépend pas du tracé ; un échec est journalisé comme les autres et n'arrête rien. Le reste de l'ADR-0053 (plafonds de requêtes, interrupteur `STOP`, fin au 30 juin 2027, worktree `C:/fp-travail`) est inchangé : **cette ADR ajoute une commande à la liste fermée et rien d'autre**.

## Conséquences

- **Fichiers** : `src/foot_predictor/inference/jeu_rejeu.py`, `inference/__main__.py` (sous-commande), `planification.py` (étape et liste fermée), `tests/inference/test_jeu_rejeu.py`, `tests/test_planification.py`, README de l'étape 11, `CLAUDE.md`, `ETAT_PROJET.md`. Aucune dépendance nouvelle ; `modeling/` et `features/` ne sont pas touchés (gardes H1 et H2 inchangées).
- **Ce que le fichier n'est pas** : une preuve de performance. Les saisons 2021-22 à 2024-25 ont servi à choisir les modèles et les réglages ; seules 2025-26 et 2026-27 sont vierges (colonne `period`). Même règle de lecture que `rejeu-stats` : descriptif, aucun modèle changé à partir de lui.
- **Les tâches existantes gardent leur ancienne description** dans le Planificateur (le texte est cosmétique ; les étapes viennent du code à chaque passage). Réinstaller (`planification install --apply`) la met à jour, sans urgence.
- **Critères de révision** :
  - un passage qui dépasse le délai de 30 minutes à cause de `jeu-rejeu` ;
  - un `ModelChanged` répété qui bloque le fichier sans que le modèle ait changé ;
  - une ligne du fichier qui diffère du rejeu de `rejeu-stats` pour le même match (les deux doivent donner les mêmes prédictions).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
