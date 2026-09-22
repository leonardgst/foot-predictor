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

---

*Généré à partir de `docs/model_results.json` (horodatage de l'exécution :
voir le champ `generated_at`). Relancer
`APP_ENV=dev uv run python -m foot_predictor.modeling.run_comparison` pour
reproduire.*
