# Prochaine étape : clustering de style + calcul du Market Value Score (MVS)

Ce document sert de point de départ pour une nouvelle conversation. Il résume
tout ce qu'il faut savoir pour attaquer le clustering sans avoir à relire tout
l'historique du projet. À joindre avec `recap_etape3_pipeline_et_mvs.md` et
`recap_decisions_projet.md` si besoin de contexte plus large.

**Statut** : conception uniquement, aucun code écrit pour cette partie.
Le schéma de base de données est déjà en place et testé (voir section 2).

---

## 1. Objectif

Calculer un **Market Value Score (MVS)** entre 0 et 100 par joueur, remplaçant
la valeur marchande Transfermarkt (abandonnée pour raisons légales — CGU et
robots.txt interdisent explicitement le scraping). Le MVS est un score à dire
d'expert (pondérations manuelles), pas un modèle supervisé calibré sur des
transferts réels — aucune donnée de transfert réelle légale n'est disponible.

```
MVS = 0.35 × Performance + 0.25 × Potentiel + 0.15 × Réputation
    + 0.10 × NiveauChampionnat + 0.10 × Disponibilité + 0.05 × Expérience
```

Ce document couvre uniquement la partie **Performance** (clustering + percentiles),
la plus complexe techniquement. Les 5 autres composantes sont plus simples
(calculs directs, pas de ML) et pourront être traitées après.

---

## 2. Données disponibles (déjà en base, schéma figé)

Table pivot : **`staging.player_match_stats`** — une ligne par (match, joueur).
Colonnes réellement disponibles (ne pas en supposer d'autres) :

```
match_id, player_id, team_id
minutes, rating, position_bucket        -- position_bucket ∈ {'Goalkeeper','Defender','Midfielder','Attacker'}
goals, assists, shots, shots_on_target
key_passes, pass_accuracy_pct
tackles, interceptions, duels_total, duels_won
dribbles_attempts, dribbles_success, dribbled_past
fouls_drawn, fouls_committed, yellow_cards, red_cards
xg, xa, npxg                             -- peuvent être NULL si Understat n'a pas encore été ingéré pour ce match
```

**Important** : `position_bucket` vient d'API-Football, qui ne donne que 4
catégories brutes (pas de distinction Ailier/Latéral/Défenseur central en
amont). C'est un choix de conception déjà tranché : voir section 4.

Pas disponibles (à ne pas essayer d'utiliser, chercher un proxy sinon) :
`touches in box`, `progressive carries`, `progressive passes received` —
ce sont des statistiques Opta/StatsBomb, qu'on n'a pas.

Autres tables utiles :
- `staging.player` (`birth_date` pour l'âge → composante Potentiel)
- `staging.team_match` / `staging.match` (contexte match, date)
- `features.team_match_features.standing_position` (niveau du club → Réputation)

---

## 3. Périmètre V1 : joueurs de champ uniquement

**Les gardiens sont explicitement hors périmètre pour cette étape** (décision
actée). Filtrer `position_bucket != 'Goalkeeper'` dès le départ. Un modèle
séparé pour les gardiens sera traité en V2 (vecteur de style totalement
différent : arrêts, buts encaissés vs attendus).

---

## 4. Groupes de poste et détection des sous-styles

### Décision actée (différente du document initial de cadrage)
Le document de conception initial prévoyait 8 groupes de poste manuels
(Défenseur Central, Latéral, Milieu Défensif, Milieu Central, Milieu Offensif,
Ailier, Attaquant...). **Ce n'est pas réalisable avec les données dont on
dispose** : API-Football ne donne que 4 catégories brutes.

**Décision** : partir des 3 groupes de champ disponibles
(`Defender`, `Midfielder`, `Attacker`), et laisser le **clustering** détecter
automatiquement les sous-styles à l'intérieur de chaque groupe (ex. un
"Ailier créateur" et un "Ailier finisseur" seront deux clusters distincts au
sein du groupe `Attacker` ou `Midfielder` selon leur profil réel, sans qu'on
ait besoin de les étiqueter en amont). C'est cohérent avec la philosophie
initiale ("les profils doivent être détectés automatiquement") — juste sans
présupposer 8 groupes qu'on ne peut pas obtenir depuis les données.

Donc : **3 clusterings indépendants**, un par groupe (`Defender`,
`Midfielder`, `Attacker`), jamais de comparaison entre groupes.

---

## 5. Fenêtre temporelle et anti-fuite (règle stricte du projet)

- **Fenêtre glissante des 50 derniers matchs joués par le joueur** (décision
  actée), pas un cumul saison.
- Chaque calcul est ancré à une **date de référence `as_of_date`** : pour
  calculer le score valable à une date donnée, on n'utilise QUE les lignes de
  `player_match_stats` dont `match.match_date < as_of_date` (jointure avec
  `staging.match`). Ne jamais utiliser un match futur par rapport à
  `as_of_date`, même si sa date est dans la fenêtre des 50 derniers matchs
  chronologiquement mal calculée — c'est la même règle anti-leakage que pour
  le reste du projet (`recap_decisions_projet.md`, section 6).
- Garde-fou à prévoir : si un joueur a moins de ~10-15 matchs disponibles
  avant `as_of_date`, le clustering/percentile sera bruité. Prévoir soit un
  seuil minimum (pas de score avant N matchs), soit une pondération réduite
  documentée.

---

## 6. Pipeline de calcul (étape Performance)

### Étape 1 — Extraction par 90 minutes
Pour chaque joueur, chaque groupe de poste, sur la fenêtre des 50 derniers
matchs avant `as_of_date` : convertir les stats comptées en valeurs **par 90
minutes jouées** (`valeur × 90 / minutes`, en excluant les lignes à `minutes`
très faible qui produiraient un ratio bruité — définir un seuil minimum, ex.
`minutes >= 20` par match pris en compte).

Variables par 90 minutes disponibles pour le vecteur de style (adapté du
document initial, réduit à ce qui est réellement calculable) :
```
goals_per90, assists_per90, shots_per90, shots_on_target_per90
key_passes_per90, xg_per90, xa_per90, npxg_per90
tackles_per90, interceptions_per90
duels_won_pct (= duels_won / duels_total, pas par 90 — déjà un ratio)
dribbles_success_per90, dribbled_past_per90
fouls_drawn_per90, fouls_committed_per90
pass_accuracy_pct (déjà un pourcentage, pas par 90)
```

Ne PAS inclure dans le vecteur de style : âge, minutes jouées, valeur
marchande (n'existe plus), nombre de matchs — cohérent avec le document
initial (le clustering doit porter sur le style de jeu, pas des variables de
volume/contexte).

### Étape 2 — Normalisation
`StandardScaler` (moyenne 0, écart-type 1), appliqué indépendamment pour
chaque groupe de poste (Defender/Midfielder/Attacker), jamais sur l'ensemble
mélangé.

### Étape 3 — Clustering
Un clustering indépendant par groupe de poste. Algorithme préféré :
**HDBSCAN** (gère le bruit sans forcer chaque joueur dans un cluster ;
alternative : GMM ou KMeans si HDBSCAN est instable sur notre volume de
données, à trancher empiriquement selon le nombre de joueurs disponibles par
groupe une fois les données réelles chargées).

Point de vigilance à valider une fois les vraies données chargées : le volume
de joueurs par groupe de poste (5 championnats, un sous-ensemble de la saison
en cours) pourrait être insuffisant pour un clustering stable au démarrage —
prévoir un seuil minimum d'échantillon avant de faire confiance aux clusters.

### Étape 4 — Nommage des clusters
Après observation des statistiques moyennes de chaque cluster (pas automatique,
assigné après coup — cf. document initial).

### Étape 5 — Percentiles
Une fois le cluster attribué, comparer chaque statistique du joueur **aux
autres joueurs du même groupe de poste ET du même cluster**, sur la même
fenêtre temporelle. Résultat : chaque statistique devient un percentile 0-100.

### Étape 6 — Pondération par cluster
Pondérations manuelles, définies par cluster (pas apprises), cohérent avec le
document initial (ex. pour un cluster "créateur" : xA/90 pondéré plus fort
que pour un cluster "finisseur"). Les pondérations précises par cluster
restent à définir une fois les clusters réels observés — ne pas les figer
avant d'avoir vu les données.

### Étape 7 — Score Performance
`Performance = Σ (percentile × poids)`, résultat entre 0 et 100.

---

## 7. Sortie attendue

Table déjà créée en base (`features.player_style_profile`) :
```
player_id, as_of_date, position_bucket, cluster_id, cluster_label,
matches_in_window (<= 50), computed_at
```

Le score Performance lui-même atterrit dans
`features.player_market_value_score.performance_score` (table déjà créée,
colonnes `potential_score`/`reputation_score`/`league_score`/
`availability_score`/`experience_score`/`mvs_total` à calculer dans une étape
ultérieure, hors périmètre de ce document).

---

## 8. Architecture de code proposée (à adapter/discuter en début de conversation)

```
src/foot_predictor/market_value/
├── __init__.py
├── data/
│   └── load_player_match_stats.py   -- requête staging.player_match_stats + jointure match_date, filtre as_of_date
├── preprocessing/
│   ├── per90.py                      -- conversion par 90 minutes, filtre minutes minimum
│   └── normalize.py                  -- StandardScaler par groupe de poste
├── clustering/
│   ├── build_clusters.py             -- HDBSCAN/GMM/KMeans par groupe de poste
│   └── assign_cluster.py
├── performance/
│   ├── percentiles.py
│   ├── weights.py                    -- pondérations manuelles par cluster
│   └── performance_score.py
└── tests/
```

(Modules `components/` pour Potentiel/Réputation/Niveau championnat/
Disponibilité/Expérience : à ajouter dans une étape ultérieure, pas
maintenant.)

---

## 9. Ce qui reste à trancher en début de conversation

- Seuil minimum de matchs avant de calculer un score (bruit sur petits échantillons)
- Seuil minimum de minutes par match pour inclure une ligne dans le calcul per-90
- Choix définitif de l'algorithme de clustering (dépend du volume réel de données)
- Pondérations précises par cluster (dépendent des clusters réellement observés)

---

*Document préparé pour démarrer une nouvelle conversation sur le clustering du Market Value Score — projet foot-predictor.*
