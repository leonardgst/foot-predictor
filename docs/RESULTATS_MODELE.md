# Résultats : Modèle A (Poisson indépendant) vs Modèle B (Dixon-Coles hybride)

Ce document consigne les métriques réelles obtenues en exécutant
`src/foot_predictor/modeling/run_comparison.py` sur la base `dev` (résultats
bruts dans `docs/model_results.json`), et la décision qui en découle. Les
équations implémentées sont celles de `docs/MODELE_MATHEMATIQUE.md` (sections
4, 5.1, 5.2) ; ce document ne les répète pas, il rapporte ce qu'elles donnent
sur nos données.

---

## 1. Jeu de données et split

- Source : `features.team_match_features` (recalculée en entier le 2026-09-22
  suite au backfill des 10 saisons, football-data + Understat — API-Football
  reste en cours de collecte au moment de cette expérience et ne fournit pas
  encore `squad_avg_age`/`squad_stability_score_season`, donc **p = 8**
  (z1-z8 uniquement, cf. `modeling/features_config.py`).
- 34 796 lignes construites (≈ 17 398 matchs), dont **1 226 lignes écartées**
  pour valeur de feature manquante (essentiellement les tout premiers matchs
  d'une équipe dans une compétition, fenêtres glissantes pas encore
  alimentées) et **0 match écarté** pour absence totale de features d'un côté.
- **Split chronologique** (jamais aléatoire, cf. `modeling/split.py`) :
  coupure au **1er août 2024**. Train = 9 saisons (2015-2016 à 2023-2024),
  31 396 lignes. Test = saison 2024-2025, 3 400 lignes (1 700 matchs).

## 2. Modèle A — Poisson indépendant

### Coefficients (GLM Poisson, statsmodels)

Signes cohérents attendus et vérifiés :

| Feature | Coefficient | p-value | Lecture |
|---|---|---|---|
| `own_xg_for_last5` | **+0.157** | ~0 | Plus l'équipe produit de xG récemment, plus elle marque — signe attendu, effet le plus fort du modèle |
| `opp_xg_against_last5` | **+0.112** | ~0 | Plus l'adversaire encaisse de xG récemment (défense faible), plus l'équipe marque — signe attendu |
| `is_home` | +0.080 | ~0 | Avantage du terrain confirmé et significatif |
| `own_standing_goal_diff` | +0.007 | ~0 | Meilleure différence de buts au classement → plus de buts marqués |
| `opp_standing_goal_diff` | −0.007 | ~0 | Adversaire mieux classé (meilleure diff. de buts) → moins de buts marqués |

Quelques coefficients ont un signe moins intuitif en lecture isolée
(`own_xg_against_last5` = −0.033, `own_goals_against_last10` = +0.042,
`opp_xg_for_last5` = −0.031) : les 16 features z1-z8 (propres + adverses) sont
corrélées entre elles (une équipe qui encaisse beaucoup de xG est aussi
souvent une équipe qui en produit peu, qui est mal classée, etc.), ce qui
brouille la lecture coefficient par coefficient sur les variables les plus
redondantes avec le classement. Les deux signaux les plus directement
interprétables (`xg_for_last5` propre, `xg_against_last5` adverse) ont
exactement le signe attendu et sont les plus significatifs — le pipeline
features → modèle fonctionne correctement (objectif du Modèle 0/1, section 3-4
du document mathématique).

### Métriques (test set, 1 700 matchs)

| Métrique | Valeur |
|---|---|
| Log-loss (score exact) | **2.9330** |
| Brier score (1N2) | **0.5915** |

### Biais scores bas — vérifié sur données réelles, pas supposé

Le document (section 4.3) documente un biais connu de la littérature :
l'indépendance sous-estimerait les scores bas (0-0, 1-1). **Sur nos données,
ce biais est marginal, voire absent** :

| Score | Probabilité moyenne prédite | Fréquence observée | Écart |
|---|---|---|---|
| 0-0 | 5.85 % | 5.76 % | Modèle A **sur-estime** légèrement |
| 1-0 | 8.85 % | 9.24 % | sous-estime de 0.4 pt |
| 0-1 | 7.47 % | 7.24 % | sur-estime de 0.2 pt |
| 1-1 | 10.70 % | 12.00 % | sous-estime de 1.3 pt |

Le seul écart notable est 1-1 (sous-estimé de 1.3 point). L'hypothèse la plus
probable : nos features (forme, xG, classement) capturent déjà une bonne
partie du signal "match fermé" que le Dixon-Coles original (sans aucune
covariable) devait entièrement déléguer à la correction `τ`.

### Calibration (probabilité de victoire à domicile)

Dans l'ensemble bien calibré, avec une légère **sur-confiance** dans les
tranches médianes-hautes : ex. tranche de probabilité prédite 30-40 %,
prédiction moyenne 35.0 % pour une fréquence observée de 29.7 % (écart de
5.3 points) ; tranche 70-80 %, prédiction moyenne 74.2 % pour une fréquence
observée de 68.5 % (écart de 5.7 points). Détail complet dans
`docs/model_results.json`.

## 3. Modèle B — Dixon-Coles hybride

### Choix d'implémentation à noter

Le document indexe le terme de features par match (`x_m`) plutôt que par
observation, ce qui est ambigu vu que les deux équations (λ_home, λ_away)
partagent en théorie la même matrice X que le Modèle A (section 2, qui elle
est spécifique à la perspective domicile/extérieur). Choix retenu ici (documenté
en tête de `modeling/dixon_coles.py`) : réutiliser les mêmes blocs `own_*`/`opp_*`
que le Modèle A, perspective par perspective, **sans** la colonne `is_home`
(remplacée par le paramètre dédié `γ`).

### Hyperparamètre ξ (décroissance temporelle)

Sélectionné par validation temporelle **interne au train set** (fit sur 8
saisons, validation sur la 9e, jamais sur le vrai test set) :

| ξ (1/jour) | Log-loss validation |
|---|---|
| **0.000** | **2.9479** (retenu) |
| 0.001 | 2.9491 |
| 0.002 | 2.9498 |
| 0.005 | 2.9525 |
| 0.010 | 2.9620 |

Aucune décroissance temporelle ne s'est révélée utile sur la grille testée :
pondérer moins les saisons anciennes dégrade systématiquement le log-loss de
validation. **ξ = 0** retenu (poids uniforme sur les 9 saisons de train).
Interprétation prudente : avec seulement 9 saisons d'historique, l'effet
"forme d'équipe qui évolue" est peut-être déjà capté par `standing_*` et
`form_points_last10` (recalculés à chaque match), rendant la décroissance
temporelle sur `α`/`β` redondante.

### Paramètres estimés

- `γ` (avantage terrain) = **0.194** (cohérent avec le coefficient `is_home`
  du Modèle A, 0.080 — le partage entre l'indicatrice et l'avantage terrain
  latent explique l'écart de magnitude, les deux ne sont pas directement
  comparables).
- `ρ` (corrélation basse-score) = **−0.039**, faible en magnitude.
- 156 équipes estimées sur le train set. **136 occurrences** (sur ~3 400
  apparitions équipe-match du test set) où l'équipe du test n'avait pas été
  vue à l'entraînement (promotions) → force latente par défaut (`α = β = 0`)
  pour ces occurrences, documenté comme limite.

### Métriques (mêmes 1 700 matchs test)

| Métrique | Modèle A | Modèle B | Gain (A − B) |
|---|---|---|---|
| Log-loss (score exact) | 2.9330 | **2.9384** | **−0.0054** (B moins bon) |
| Brier score (1N2) | 0.5915 | **0.5946** | **−0.0031** (B moins bon) |

## 4. Comparaison A vs B — décision

**Le Modèle B n'apporte pas de gain mesurable sur ce test set : il est
légèrement moins bon que le Modèle A sur les deux métriques.** Ce n'est pas
le résultat attendu de la littérature (Dixon-Coles bat en général un Poisson
indépendant), donc à signaler explicitement plutôt qu'à masquer :

**Hypothèses sur ce résultat** (à valider si le sujet est repris plus tard) :

1. Le biais scores-bas que `τ` est censé corriger est déjà marginal dans nos
   données (section 2 ci-dessus) — la correction a donc peu de biais à
   corriger, et son coût (paramètres supplémentaires, ρ estimé sur un signal
   faible) peut légèrement dégrader la généralisation.
2. Le Dixon-Coles original (1997) n'avait **aucune** covariable : `α`/`β`
   portaient tout le signal de force d'équipe. Ici, `standing_*`, `form_*` et
   `xg_*` portent déjà une grande partie de ce signal — `α`/`β` ajoutent donc
   ~310 paramètres pour capturer un résidu de signal plus restreint, avec un
   risque de sur-ajustement sur 9 saisons de train.
3. 136 occurrences d'équipes non vues à l'entraînement (promotions) forcent un
   repli `α = β = 0` qui dégrade spécifiquement les prédictions sur ces
   équipes en test.
4. Le choix d'implémentation de `x^T δ` (section 3) diffère peut-être de
   l'intention du document — une version alternative (ex. `δ` réduit aux seuls
   one-hot championnat, laissant `α`/`β` porter tout le signal d'équipe) n'a
   pas été testée ici et pourrait donner un résultat différent.

### Décision retenue

**On garde le Modèle A (Poisson indépendant) comme référence pour la suite**,
faute de gain démontré du Modèle B sur ce jeu de données. Le code du Modèle B
est conservé (implémentation pédagogique complète, testée — voir
`tests/modeling/test_dixon_coles.py`) mais n'est pas mis en production tel
quel. Pistes pour revisiter cette décision plus tard :

- Reproduire l'expérience une fois `squad_avg_age`, `squad_stability_score_season`
  (z9-z10) et l'agrégat MVS (z11) disponibles (API-Football) : `α`/`β` pourraient
  capter un signal que z1-z8 ne couvrent pas.
- Tester la variante "δ réduit" mentionnée en (4).
- Réévaluer une fois plusieurs saisons supplémentaires accumulées (l'historique
  actuel, 9 saisons de train, est peut-être encore court pour que l'estimation
  MLE de 156 × 2 forces d'équipe converge de façon stable).

## 5. Recalibration post-hoc de la probabilité 1N2 (Platt scaling / isotonic regression)

La section 2 documente une légère sur-confiance du Modèle A dans les tranches
médianes-hautes de probabilité de victoire à domicile (30-40 % et 70-80 %
notamment). Cette section évalue si une recalibration post-hoc standard
(Platt scaling, isotonic regression) corrige ça de façon mesurable, avec le
même protocole anti-fuite que la section 3 (fenêtre de sélection interne au
train set, jamais le test set) : implémentation dans
`src/foot_predictor/modeling/calibration.py`, script d'exécution
`src/foot_predictor/modeling/run_calibration_analysis.py`, résultats bruts
dans `docs/model_results.json` (clé `calibration_experiment`).

### Protocole

1. Reproduction exacte du Modèle A de la section 2 : `build_dataset` →
   `chronological_split(CUTOFF_DATE)` → `fit_poisson_model` sur tout le train
   set (31 396 lignes) — c'est ce modèle qui sert aux prédictions finales sur
   le test set, jamais un modèle réduit.
2. Fenêtre de calibration découpée **à l'intérieur du train set**, même
   logique que `_select_xi` (section 3) : `val_cutoff = CUTOFF_DATE − 365
   jours` (2 août 2023). Un Poisson **réduit** est ajusté sur les 27 994
   lignes avant `val_cutoff`, puis utilisé pour prédire la fenêtre
   `[val_cutoff, CUTOFF_DATE)` (3 402 lignes, 1 701 matchs). Platt scaling
   (`sklearn.linear_model.LogisticRegression`) et isotonic regression
   (`sklearn.isotonic.IsotonicRegression`) sont ajustés sur les paires
   (probabilité prédite, issue réelle 0/1) de cette seule fenêtre.
3. Les calibrateurs ainsi ajustés sont appliqués aux prédictions du Modèle A
   **du train complet** (étape 1) sur le vrai test set (1 700 matchs), jamais
   utilisé pour ajuster quoi que ce soit en amont.

**Simplification méthodologique documentée** : Platt scaling et isotonic
regression recalibrent nativement un scalaire `P(classe)` contre
`1 − P(classe)`, ce qui ne préserve pas `P(domicile) + P(nul) + P(extérieur)
= 1` pour les 3 issues du marché 1N2. L'approche retenue ici est one-vs-rest
(un calibrateur indépendant par issue, chacune vue comme "cette classe
est-elle la bonne ?") suivie d'une renormalisation des 3 probabilités
recalibrées pour qu'elles resomment à 1 (`calibrate_ovr_and_renormalize` dans
`calibration.py`) — une approximation ; une méthode de calibration
multi-classe rigoureuse (calibration de Dirichlet par exemple) serait plus
correcte mais est hors scope de cette passe.

### Résultats (test set, 1 700 matchs)

| Variante | Brier score (1N2) | Écart vs Modèle A brut |
|---|---|---|
| Modèle A brut (avant recalibration) | **0.5915** | — |
| + Platt scaling | 0.5913 | **+0.0002** (amélioration marginale) |
| + Isotonic regression | 0.5925 | **−0.0010** (dégradation) |

Calibration de la probabilité de victoire à domicile, sur les deux tranches
déjà signalées en section 2 (le tableau complet, 10 tranches, est dans
`docs/model_results.json` sous `calibration_experiment`) :

| Tranche | Avant (prédit / observé / écart, n) | + Platt (prédit / observé / écart, n) | + Isotonic (prédit / observé / écart, n) |
|---|---|---|---|
| 30-40 % | 35.0 % / 29.7 % / **5.3 pt** (n=357) | 34.8 % / 31.9 % / **2.8 pt** (n=307) | 34.2 % / 36.2 % / **−2.0 pt** (n=378) |
| 70-80 % | 74.2 % / 68.5 % / **5.7 pt** (n=111) | 72.1 % / 86.7 % / **−14.6 pt** (n=30) | 74.9 % / 70.6 % / **4.3 pt** (n=214) |

Écart absolu moyen de calibration sur les 10 tranches, pondéré par l'effectif
de chaque tranche (métrique globale, moins sensible au bruit des tranches à
faible n que les deux lignes ci-dessus) :

| Variante | Écart moyen pondéré (points) |
|---|---|
| Avant recalibration | 2.8 |
| + Platt scaling | 2.6 |
| + Isotonic regression | 4.1 |

**Observation méthodologique à noter** : recalibrer déplace des matchs d'une
tranche à l'autre (les bornes de `pd.cut` sont fixes, mais les probabilités
recalibrées ne le sont pas) — l'effectif de la tranche 70-80 % passe par
exemple de 111 (avant) à 30 (après Platt) à 214 (après isotonic). Les
comparaisons tranche-par-tranche portent donc en partie sur des sous-échantillons
différents, ce qui limite leur lecture individuelle (la tranche Platt
70-80 %, n=30, est bruitée) ; le Brier score global et l'écart pondéré
ci-dessus restent les métriques les plus fiables pour trancher.

### Décision retenue

**Le gain n'est pas suffisant pour justifier d'ajouter une étape de
recalibration au service d'inférence, du moins avec ce protocole (fenêtre de
calibration d'un an, ~1 700 matchs) :**

- **Platt scaling** apporte un gain de Brier de +0.0002 (0.5915 → 0.5913) et
  un gain d'écart pondéré de 0.2 point (2.8 → 2.6) — dans les deux cas, un
  ordre de grandeur difficile à distinguer du bruit statistique sur 1 700
  matchs de test. Il vide par ailleurs presque totalement les tranches de
  probabilité au-dessus de 80 % (effectif combiné 148 → 30), ce qui traduit
  une compression générale des probabilités plutôt qu'une correction ciblée
  de la sur-confiance mi-haute identifiée en section 2.
- **Isotonic regression** dégrade le Brier score (0.5915 → 0.5925) et l'écart
  pondéré (2.8 → 4.1 points) sur le test set. Hypothèse la plus probable :
  sur-ajustement de la fonction en escalier de la régression isotone sur une
  fenêtre de calibration réduite (~1 700 matchs, one-vs-rest donc chaque
  calibrateur ne voit qu'un sous-signal binaire) — particulièrement visible
  sur les tranches à faible effectif (ex. tranche 90-100 %, n=3, écart de 33
  points après isotonic).

Aucune des deux méthodes ne produit un gain net, robuste et généralisable sur
ce test set. **On ne recalibre pas le Modèle A pour l'instant** ; le code
(`modeling/calibration.py`, testé indépendamment de la base sur données
synthétiques dans `tests/modeling/test_calibration.py`) est conservé et
réutilisable si le sujet est repris avec une fenêtre de calibration plus
large (plusieurs saisons) ou une méthode multi-classe plus rigoureuse
(Dirichlet calibration).

**Backlog** : si cette décision est révisée plus tard (fenêtre de calibration
élargie, gain confirmé), le point d'intégration est
`src/foot_predictor/modeling/predict_service.py` — non modifié par ce travail,
laissé pour un chantier séparé.

---

*Généré à partir de `docs/model_results.json` (horodatage de l'exécution :
voir le champ `generated_at`). Relancer
`APP_ENV=dev uv run python -m foot_predictor.modeling.run_comparison` pour
reproduire les sections 1-4, et
`APP_ENV=dev uv run python -m foot_predictor.modeling.run_calibration_analysis`
pour reproduire la section 5.*
