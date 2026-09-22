# Modélisation mathématique du score exact

Ce document construit, progressivement et en détail, la formulation mathématique du problème
de prédiction : de la notation la plus générale (ŷ, y, X) jusqu'au contenu réel de la matrice
de features telle qu'elle existe (ou existera) dans `features.team_match_features`, puis jusqu'à
trois familles de modèles réalistes entre lesquelles choisir.

Pour le cadrage produit et les sources de données, voir `OBJECTIFS.md` et `RECAP_PROJET.md`
(sections 2, 3, 6.3, 8). Ce document ne les répète pas, il les traduit en équations.

---

## 1. Cadrage du problème

### 1.1 Ce qu'on prédit

Le produit veut, pour un match à venir, un **score exact** : (buts équipe A, buts équipe B).
On en dérive ensuite le 1N2 et des probabilités précises par simple lecture de la loi jointe
prédite — ce n'est **pas** une sortie séparée du modèle.

Un score est un couple d'entiers naturels : `(g_H, g_A) ∈ ℕ²` (buts domicile, buts extérieur).
Ceci a une conséquence immédiate sur le choix du modèle (section 3) : on ne prédit pas un réel
continu, on prédit un **comptage**, et un comptage **par équipe**, pas un score global — les deux
comptages ne sont probablement pas indépendants (un match fermé donne souvent un score bas des
deux côtés).

### 1.2 Unité d'observation

La table `staging.team_match` a une granularité `(match, équipe)`. C'est l'unité naturelle
d'observation pour l'apprentissage : chaque ligne dit "cette équipe, dans ce match précis (à
domicile ou à l'extérieur), a marqué tant de buts".

Notation :

- `m = 1, …, M` : indice de match.
- `H(m)` : équipe qui joue à domicile dans le match `m`.
- `A(m)` : équipe qui joue à l'extérieur dans le match `m`.
- Pour chaque match, on a donc **deux observations** : `(m, H(m))` et `(m, A(m))`.

On notera `i = (m, t)` une observation individuelle, où `t ∈ {H(m), A(m)}`.

### 1.3 La cible y

Pour chaque observation `i = (m, t)` :

```
y_i = buts marqués par l'équipe t dans le match m   (= team_match.goals_for)
```

Au niveau du match, la cible complète est le couple :

```
y_m = (y_m^H, y_m^A)   avec   y_m^H = y_{(m,H(m))}   et   y_m^A = y_{(m,A(m))}
```

C'est `y_m`, la paire jointe, qu'on cherche à modéliser — pas seulement chaque composante
séparément (voir section 4.3).

---

## 2. Construction détaillée de la matrice X

### 2.1 Principe : deux blocs de features par observation

Le nombre de buts qu'une équipe marque dépend :

1. **de sa propre force offensive et de son contexte** (forme, xG marqués, classement…) ;
2. **de la force défensive de l'adversaire** (xG encaissés par l'adversaire, classement de
   l'adversaire…) ;
3. **du lieu du match** (avantage du terrain) ;
4. **du championnat** (niveau de compétition).

Le vecteur de features d'une observation `i = (m, t)` n'est donc pas seulement "les stats de
`t`" : c'est la concaténation des stats de `t` **et** des stats de son adversaire dans ce match,
noté `opp(i)`.

### 2.2 Le vecteur "état d'une équipe avant un match", z

On définit d'abord `z_{t,m} ∈ ℝ^p`, le vecteur des variables propres à une équipe `t`, calculées
**strictement avant** la date du match `m` (ancrage `as_of_date = match_date`, principe déjà en
place dans le pipeline — voir `RECAP_PROJET.md` section 5 et 8). C'est exactement le contenu
d'une ligne de `features.team_match_features`, moins les identifiants :

| Composante de z | Colonne source | Signification |
|---|---|---|
| `z_1` | `form_points_last10` | Points pris sur les 10 derniers matchs, même contexte dom./ext. |
| `z_2` | `goals_for_last10` | Buts marqués, moyenne sur 10 derniers matchs, même contexte |
| `z_3` | `goals_against_last10` | Buts encaissés, moyenne sur 10 derniers matchs, même contexte |
| `z_4` | `xg_for_last5` | xG produit, moyenne sur 5 derniers matchs, même contexte |
| `z_5` | `xg_against_last5` | xG concédé, moyenne sur 5 derniers matchs, même contexte |
| `z_6` | `standing_position` | Position au classement, snapshot avant le match |
| `z_7` | `standing_points` | Points au classement, snapshot avant le match |
| `z_8` | `standing_goal_diff` | Différence de buts au classement, snapshot avant le match |
| `z_9` | `squad_avg_age` | Âge moyen de l'effectif titulaire — **bloqué** (nécessite `lineup`, donc l'abonnement API-Football) |
| `z_10` | `squad_stability_score_season` | Score de cohésion du onze — **bloqué**, même raison |
| `z_11` (futur) | agrégat du MVS des titulaires | Remplace `squad_valuation_eur` — **non spécifié**, dépend de la section 10 du récap |

Soit `p = 11` (aujourd'hui, seuls `z_1…z_8` sont réellement calculables ; `z_9, z_10, z_11` sont
en attente). Rien n'empêche d'utiliser un premier modèle avec `p = 8` et d'enrichir plus tard —
c'est même recommandé (voir section 4).

Chaque `z_{t,m}` est un vecteur **daté** : ce n'est pas "les stats de l'équipe" dans l'absolu,
c'est son état juste avant ce match précis. Deux lignes `z_{t,m}` et `z_{t,m'}` pour la même
équipe à deux dates différentes seront différentes.

### 2.3 Le vecteur complet d'une observation, x

Pour l'observation `i = (m, t)`, avec `t' = opp(i)` l'adversaire :

```
x_i = [ 1, z_{t,m}, z_{t',m}, h_i, c_m ]   ∈  ℝ^{1 + 2p + 1 + (L-1)}
```

avec :

- `1` : le terme d'interception (biais).
- `z_{t,m}` : le vecteur "propre" de l'équipe `t` (attaque potentielle).
- `z_{t',m}` : le vecteur "propre" de l'adversaire `t'` (défense qu'il faudra percer).
- `h_i ∈ {0,1}` : indicatrice terrain (`1` si `t` joue à domicile dans `m`, `0` sinon). C'est
  la traduction mathématique de l'avantage du terrain, connu pour être un effet fort et
  systématique en football.
- `c_m` : encodage one-hot du championnat du match `m` sur `L = 5` championnats
  (Premier League, La Liga, Bundesliga, Serie A, Ligue 1), soit `L - 1 = 4` colonnes binaires
  (une modalité de référence absorbée dans l'intercept) — capture le niveau moyen de buts par
  championnat.

Concrètement, pour le match `m` opposant `H(m)` à `A(m)` :

```
x_{(m,H(m))} = [1, z_{H(m),m}, z_{A(m),m}, 1, c_m]   -- prédit y_m^H
x_{(m,A(m))} = [1, z_{A(m),m}, z_{H(m),m}, 0, c_m]   -- prédit y_m^A
```

Remarquez que le même match produit deux lignes, avec les deux blocs `z` inversés selon le
côté prédit. C'est cette construction qui transforme la table `team_match_features` (une ligne
par équipe-match) en la matrice `X` utilisée par le modèle (une ligne par équipe-match, mais
avec les colonnes de l'adversaire jointes).

### 2.4 La matrice X

Sur l'ensemble des matchs disponibles, on empile toutes les observations :

```
X = [ x_1 ; x_2 ; … ; x_N ]   ∈  ℝ^{N × d},   N = 2M,   d = 1 + 2p + 1 + (L-1)
y = [ y_1 ; y_2 ; … ; y_N ]   ∈  ℕ^N
```

`N = 2M` parce que chaque match donne deux observations (une par équipe). C'est cette paire
`(X, y)` — et non un `X` unique par match avec une cible bivariée — qui sert de base commune à
tous les modèles ci-dessous ; les modèles diffèrent dans la façon dont ils relient `X` à `y`
et dans la façon dont ils réintroduisent le couplage entre `y_m^H` et `y_m^A` (perdu par cet
empilement en format long).

---

## 3. Modèle 0 — la régression linéaire naïve (point de départ pédagogique)

C'est le point de départ demandé : le plus simple possible.

```
ŷ_i = x_i^T β = β_0 + β_1 x_{i,1} + … + β_d x_{i,d}
```

Estimation par moindres carrés ordinaires :

```
β̂ = argmin_β  Σ_i (y_i − x_i^T β)²   =   (XᵀX)⁻¹ Xᵀy
```

**Pourquoi ce modèle ne convient pas ici**, et pourquoi il faut le dépasser dès l'étape
suivante :

1. `ŷ_i` peut être négatif (impossible physiquement, `y_i` est un compte de buts ≥ 0).
2. Il suppose que l'erreur `y_i − ŷ_i` est de variance constante et gaussienne, alors que la
   variance du nombre de buts croît avec le nombre de buts attendu (propriété des comptages).
3. Il traite `y_m^H` et `y_m^A` comme deux régressions totalement indépendantes : aucune loi
   jointe, donc **aucune probabilité de score exact** ne peut en être dérivée directement
   (seulement deux valeurs ponctuelles, pas une distribution). Or c'est justement la sortie
   attendue par le produit (« probabilités précises »).

Modèle 0 sert de vérification de plomberie (le pipeline features → modèle fonctionne, les
signes des coefficients sont cohérents), pas de candidat final.

---

## 4. Modèle 1 — régression de Poisson (la bonne famille pour un comptage)

### 4.1 Formulation

On modélise chaque `y_i` comme un tirage d'une loi de Poisson dont le paramètre `λ_i`
(nombre de buts moyen attendu) dépend de `x_i` :

```
y_i | x_i  ~  Poisson(λ_i)
λ_i = exp(x_i^T β)          (fonction de lien "log")
```

Le lien logarithmique garantit `λ_i > 0` quel que soit `β` — ça résout le problème n°1 du
modèle 0. La loi de Poisson a par construction `Var(y_i) = λ_i` : la variance croît avec la
moyenne — ça résout le problème n°2.

### 4.2 Estimation

Par maximum de vraisemblance. Densité de Poisson : `P(y_i | λ_i) = λ_i^{y_i} e^{-λ_i} / y_i!`.
Log-vraisemblance à maximiser sur `β` :

```
ℓ(β) = Σ_i [ y_i · x_i^T β − exp(x_i^T β) − log(y_i!) ]
```

Pas de forme fermée (contrairement aux MCO), résolu par Newton-Raphson / IRLS — c'est ce
qu'implémentent nativement `statsmodels.GLM(family=Poisson())` ou
`sklearn.linear_model.PoissonRegressor`.

### 4.3 Ce qu'il manque encore : le couplage entre les deux buts d'un même match

En ajustant Modèle 1 sur les `N = 2M` lignes empilées, on obtient un unique `β̂`, et donc, pour
un match `m` :

```
λ̂_m^H = exp(x_{(m,H(m))}^T β̂)
λ̂_m^A = exp(x_{(m,A(m))}^T β̂)
```

Si on suppose `y_m^H` et `y_m^A` **indépendants** conditionnellement à `X`, la probabilité d'un
score exact `(a, b)` s'obtient directement :

```
P(y_m^H = a, y_m^A = b) = Poisson(a; λ̂_m^H) × Poisson(b; λ̂_m^A)
```

C'est déjà un modèle complet et utilisable : à ce stade, on a une vraie distribution jointe sur
les scores, donc un score exact le plus probable et des probabilités 1N2 dérivées. C'est le
premier des 3 choix réalistes (section 5.1).

**Limite connue et documentée dans la littérature football (Dixon & Coles, 1997)** :
l'hypothèse d'indépendance sous-estime systématiquement la fréquence réelle de certains scores
bas (0-0, 1-1, 1-0, 0-1) — les matchs fermés ont une corrélation négative entre les deux
comptages que l'indépendance ne capture pas. C'est le problème que règle le modèle suivant.

---

## 5. Trois choix réalistes

Les trois options ci-dessous partagent la même matrice `X` (section 2) et la même famille de
distribution de base (Poisson pour un comptage de buts). Elles diffèrent sur *comment* elles
relient `X` à `λ`, et sur comment elles gèrent la corrélation entre `y_m^H` et `y_m^A`.

### 5.1 Option A — Poisson bivarié indépendant (extension directe du Modèle 1)

C'est très exactement le Modèle 1 ci-dessus, gardé tel quel comme solution de référence :

```
λ_m^H = exp(x_{(m,H(m))}^T β)
λ_m^A = exp(x_{(m,A(m))}^T β)
P(y_m^H = a, y_m^A = b) = Poisson(a; λ_m^H) · Poisson(b; λ_m^A)
```

- **Avantages** : le plus simple à implémenter et à valider (une seule régression de Poisson,
  bibliothèques standard) ; s'appuie directement sur la matrice `X` déjà conçue ;
  interprétable coefficient par coefficient.
- **Limites** : sous-estime les scores bas corrélés (0-0, 1-1) — biais documenté et mesurable ;
  aucune force d'équipe "intrinsèque" hors des features observées (si `X` est incomplet, le
  modèle n'a rien pour compenser).
- **Effort avec le pipeline actuel** : faible. Fonctionne dès aujourd'hui avec `p = 8`
  (sans attendre `squad_avg_age`, `squad_stability_score_season` ni le MVS).

### 5.2 Option B — Dixon-Coles (Poisson bivarié avec correction basse-score)

Le modèle de référence académique et professionnel pour le score exact au football. Il combine
deux idées : (i) des **forces d'équipe latentes** estimées sur l'historique (attaque/défense),
en plus ou à la place de nos features observées, et (ii) une **correction de corrélation** pour
les scores bas.

```
λ_m^H = exp(α_{H(m)} − β_{A(m)} + γ + x_m^T δ)
λ_m^A = exp(α_{A(m)} − β_{H(m)} + x_m^T δ)

P(y_m^H = a, y_m^A = b) = τ_{λ,μ}(a,b) · Poisson(a; λ_m^H) · Poisson(b; λ_m^A)
```

où :

- `α_t` : force d'attaque de l'équipe `t` (paramètre estimé, un par équipe).
- `β_t` : faiblesse défensive de l'équipe `t` (paramètre estimé, un par équipe).
- `γ` : avantage du terrain (un seul paramètre global, ou par championnat).
- `x_m^T δ` : nos features (section 2) ajoutées **en plus** des forces latentes `α, β` — c'est
  l'extension moderne du Dixon-Coles original (1997), qui à la base n'utilisait que
  l'historique des scores, sans xG ni forme récente.
- `τ_{λ,μ}(a,b)` : fonction de correction, non triviale seulement pour `(a,b) ∈ {(0,0),(1,0),
  (0,1),(1,1)}`, paramétrée par `ρ` (estimé conjointement), qui ajuste la probabilité de ces
  scores précis à la hausse ou à la baisse selon le signe de `ρ`.
- Estimation par maximum de vraisemblance pondéré dans le temps : chaque match `m'` reçoit un
  poids `Φ(m') = exp(−ξ · Δt_{m'})` qui décroît avec l'ancienneté (`Δt` = temps écoulé depuis
  ce match), pour que les matchs récents comptent plus que les anciens dans l'estimation de
  `α, β, γ, δ, ρ`.

- **Avantages** : corrige le biais documenté de l'option A sur les scores bas ; les paramètres
  `α_t, β_t` donnent une lecture directe et interprétable de la force de chaque équipe ;
  standard de l'industrie, donc validable contre la littérature.
- **Limites** : plus complexe à estimer (optimisation numérique sur `2×(nb équipes) + 3 + dim(δ)`
  paramètres simultanément, pas un simple GLM prêt à l'emploi) ; le choix de `ξ` (vitesse de
  décroissance du poids temporel) est un hyperparamètre à calibrer.
- **Effort avec le pipeline actuel** : moyen. Réutilise `X` tel quel pour `δ`, mais demande
  d'écrire l'optimisation (ou d'utiliser une bibliothèque type `penaltyblog` /
  implémentation maison scipy.optimize) plutôt qu'un simple appel `GLM`.

### 5.3 Option C — Gradient boosting à objectif Poisson (approche par apprentissage)

Remplacer la forme log-linéaire `exp(x^T β)` par une fonction non paramétrique apprise par
arbres de décision (XGBoost / LightGBM / CatBoost, objectif `count:poisson` ou `tweedie`) :

```
λ_m^H = f_H(x_{(m,H(m))})        f_H appris par gradient boosting, perte = −log-vraisemblance Poisson
λ_m^A = f_A(x_{(m,A(m))})        f_A appris séparément, même principe
```

La loi de score exact s'obtient comme en 5.1 (produit de deux Poisson), éventuellement corrigée
a posteriori par une estimation empirique de la corrélation résiduelle entre buts domicile et
extérieur (par exemple une copule gaussienne ajustée sur les résidus, ou une version des
`τ_{λ,μ}` du Dixon-Coles appliquée aux `λ̂` produits par les arbres).

- **Avantages** : capture des interactions et non-linéarités entre features sans les spécifier
  à la main (ex. l'effet de la forme récente peut dépendre du niveau de classement, sans avoir
  à écrire ce terme d'interaction) ; s'accommode naturellement de features supplémentaires au
  fil du temps (MVS, âge, stabilité) sans reformulation du modèle.
- **Limites** : perd l'interprétabilité fine des coefficients de forces d'équipe ; risque de
  sur-apprentissage plus élevé avec un historique encore modeste (quelques saisons × 5
  championnats) — nécessite une validation croisée temporelle soignée (jamais entraîner sur le
  futur d'un match de test) ; la corrélation basse-score n'est pas native au modèle, elle
  doit être rajoutée en post-traitement.
- **Effort avec le pipeline actuel** : moyen à élevé. Techniquement immédiat (bibliothèques
  standard), mais la validation (découpage temporel, choix d'hyperparamètres, gestion de la
  corrélation) demande plus de travail de méthodologie que les options A et B.

### 5.4 Tableau de synthèse

| | A. Poisson indépendant | B. Dixon-Coles | C. Gradient boosting Poisson |
|---|---|---|---|
| Corrélation buts dom./ext. | ❌ non modélisée | ✅ via `τ` | ⚠️ à ajouter en post-traitement |
| Force d'équipe intrinsèque | ❌ seulement via X | ✅ `α_t`, `β_t` estimés | ❌ seulement via X |
| Interprétabilité | Haute (coefficients) | Haute (α, β, γ, δ interprétables) | Faible (boîte noire) |
| Effort d'implémentation | Faible | Moyen | Moyen à élevé |
| Utilisable dès aujourd'hui (p=8) | ✅ | ✅ | ✅ |
| Maturité / validation en football | Basique | Référence académique établie | Dépend de la rigueur de validation |

---

## 6. Prochaine étape

Ce document ne tranche rien : il pose les équations pour que le choix entre A, B et C se fasse
en connaissance de cause. À discuter ensemble : le niveau d'effort qu'on veut mettre dès la V1,
et si on part sur une option "simple d'abord, on complexifie ensuite" (A → B) ou si on vise
directement B ou C.

*Document à archiver dans `docs/` aux côtés de `RECAP_PROJET.md` une fois le choix acté, avec
mise à jour de la section retenue et suppression des options écartées (ou conservation en
annexe "alternatives envisagées").*
