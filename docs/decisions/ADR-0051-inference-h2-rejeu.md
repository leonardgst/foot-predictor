# ADR-0051 — Inférence de l'horizon H2 en rejeu : modèle du pli, composition à T-60, live « indisponible »

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0010 (horizons), ADR-0011 (rejeu et live), ADR-0040 (même fonction), ADR-0045 (ouverture du scellé), ADR-0047 (D6, périmètre de l'inférence H2), ADR-0048, ADR-0049, ADR-0050 (modèle H2, procédure de `M3_H2`) ; cadrage de la partie 6, sections 5 et 8 (6.10) ; `docs/resultats/h2_ablations.md`, `docs/resultats/h2_structures.md`

## Contexte

- **Le modèle H2 est choisi et figé** : M3 sur G0 + G1 + G2 + G5 (ADR-0050). Le gel `pre-scelle-h2` interdit tout changement de `modeling/`, `features/`, `seal.py` et `experiments/` jusqu'au test scellé (6.12) : 6.10 et 6.11 ne touchent que `inference/`, `api/`, `ui/`, les tests et la documentation.
- **H2 est un horizon de rejeu** (ADR-0010, ADR-0047) : après la fin de l'abonnement, aucune composition n'arrive plus ; le live H2 n'existe pas.
- **Ce qui existait** : `horizon=H2` répondait `h2_unavailable` partout, et l'API répondait 501.
- **Ce qui est demandé** (cadrage, 6.10) : H2 en rejeu dans l'API et l'interface, H1 et H2 côte à côte, une page « apport des variables ».
- **Le gain de H2 est minuscule** : +0,00078 de log-loss du total [+0,00003 ; +0,00151] (ADR-0048). L'interface doit le dire, sans laisser croire qu'un écart sur un match prouve quoi que ce soit.
- **Règle de l'ADR-0040** : l'inférence n'a aucune formule de variable propre ; elle appelle la fonction de l'entraînement sur l'historique tronqué au jour du match.

## Options envisagées

1. **H2 par la même fonction et le même modèle du pli, cache séparé, live « indisponible » en réponse normale.** `build_frame_h2` sur l'historique tronqué, compositions lues par la porte, modèle du pli appris par la procédure de `M3_H2`. Conséquence : aucune formule neuve ; un seul chemin de calcul pour l'entraînement et l'inférence.
2. **Un calcul H2 propre à l'inférence** (variables recalculées plus vite, sans `build_frame_h2`). Écartée : c'est exactement ce que l'ADR-0040 interdit, et un écart entre entraînement et inférence est un défaut.
3. **Garder le 501 pour le live H2.** Écartée : 501 dit « non implémenté », alors que H2 est volontairement indisponible en live, pour une raison que l'utilisateur doit lire (ADR-0010). Une réponse 200 avec un statut et sa raison suit le contrat des autres statuts.
4. **Un modèle H2 actif en live**, appris avec les matchs scellés. Écartée par l'ADR-0047 (D6) : sans compositions, il ne servirait à rien.
5. **Page d'apport avec attribution par variable et par match** (valeurs de Shapley). Écartée : le modèle est un Poisson log-linéaire, dont les coefficients se lisent directement, et le gain mesuré est minuscule ; une attribution fine donnerait l'illusion d'un effet que la validation ne distingue pas de zéro.
6. **Recopier les chiffres de l'apport dans l'interface.** Écartée : les chiffres de `docs/resultats/` sont générés (CLAUDE.md). La page les lit dans les rapports d'expériences, par l'API.

## Décision

Option 1, avec ces précisions.

### Modèle de rejeu H2

- **Procédure** : le pli S est appris sur 2015-16 à S − 1 par `protocol.select_and_fit`, avec la ligne `M3_H2` de `experiments/scelle_h2.yaml` (demi-vie de G2 choisie par validation interne). Le début d'apprentissage de G5 (2016-17, rodage D3) est transmis comme l'évaluation le fait.
- **Jeu** : `ds-2026-11-01-e0defb32`, celui de l'évaluation qui a retenu le modèle.
- **Cache** : `models/rejeu/h2/<S>/`, version `rejeu-<S>-m3_h2`, carte `horizon: H2` avec ses propres limites. Le cache et les cartes de H1 ne changent pas.
- **Saisons** : 2021-22 à 2024-25. Le rejeu des saisons scellées reste fermé jusqu'au test scellé de H2 (ADR-0045).

### Variables

- **Même fonction** : `features.dataset.build_frame_h2` sur la table des matchs, les compositions et les feuilles de match tronquées au jour J, un jour à la fois. Les compositions viennent de la porte (`load_lineups`, `load_team_sheets`), qui filtre le scellé en SQL ; elles ne sont **pas** ouvertes à l'inférence.
- **Match cible** : on garde ce que l'on sait à T-60 (titulaires, poste annoncé, entraîneur, formation) et on retire ce que le match produit (minutes, note, remplaçant, capitaine, poste des statistiques). Les groupes G4 à G6 ne lisent déjà que des jours strictement antérieurs : ce retrait est une **défense en profondeur**, pas la seule barrière (une mutation qui le désactive n'est détectée que par le test unitaire de `lineups_for_day`, pas par le test d'invariance du résultat).
- **Lecture à la demande** : les compositions (environ 2 millions de lignes, 17 secondes) ne sont lues qu'à la première demande H2.

### Disponibilité

- **Rejeu** : mêmes règles que H1 (une variable requise non présente ⇒ `unavailable`, jamais de valeur de remplacement), avec des raisons propres à G5 : onze incomplet ou absent, titulaire sans poste ni note antérieure, moins de 10 matchs d'historique, date de naissance manquante.
- **Live** : statut `h2_unavailable`, raison « les compositions ne sont plus fournies depuis la fin de l'abonnement (ADR-0010) », ni modèle, ni variable, ni lecture des compositions.

### API

- **`horizon`** est ajouté à `GET /matches` (H1 par défaut).
- Le **501 disparaît**. Live H2 : 200 sur `/matches` et `/availability` avec `h2_unavailable` et sa raison ; 409 sur `POST /predictions` comme pour tout match indisponible. `model_version` devient facultatif (vide sans modèle).
- **`GET /models/h2/contribution`** : chemin de décision de 6.7, diagnostics, structures de 6.8 et gain de G5 par tranche de journées, lus dans les rapports `ablations-h2-20261101T123436` et `structures-h2-20261101T134102`. 503 si un rapport manque.

### Interface

- **Détail** : H1 à gauche, H2 à droite (loi du total, E[T], λ, intervalle, P(T > 2,5)) ; en dessous, l'écart H2 − H1 et la qualité du onze lue par H2, avec la mise en garde sur la taille du gain. En live, H2 affiche sa raison.
- **Apport des variables** : étape par étape, gain et intervalle, plis gagnés, verdict ; diagnostics ; structures ; gain de G5 par tranche de journées ; mises en garde.
- Le bouton « Prédiction » trace H1 et H2 dans `ops.prediction` (idempotent), comme il traçait H1.

### Contrôles sur données réelles

`inference check --only rows-h2 | replay-h2 | predictions-h2`, sur demande : lignes H2 contre `e0defb32`, modèles de rejeu et journées contre l'expérience `structures-h2` (modèle `M3_H2`). Même tolérance que pour H1 (10⁻⁹).

## Conséquences

- **Fichiers** : nouveau `inference/h2_contribution.py` ; modifiés `inference/{models,rows,predict,availability,context,check,__main__}.py`, `api/{app,schemas}.py`, `ui/{app,client,views}.py` et leurs tests. Aucune nouvelle dépendance, aucun `load`, aucun appel à API-FOOTBALL.
- **Garde H1** : aucun modèle ni aucune variable H1 ne change. Les chemins gelés sont intacts (`git diff --stat pre-scelle-h2` vide). `inference check --only replay` reproduit le rejeu H1.
- **Coût** : environ 18 secondes par jour de rejeu H2 (le premier appel d'un jour), puis le cache de lignes sert la journée.
- **Limite connue d'un chemin gelé** : `compute_xi_quality` (`features/`, gelé) échoue par une `MergeError` de pandas quand aucune apparition identifiée n'existe dans l'historique (des compositions sans identifiant de joueur, ou un tout premier jour). Ce n'est pas atteignable sur les données réelles du rejeu (2021-22 et après, onze identifiés depuis 2010), et l'inférence répond 503 si la porte ne lit aucune composition. Une correction passerait par une nouvelle ADR après le test scellé (gel).
- **On s'interdit** : de servir H2 en live ; de servir un jour de rejeu scellé avant l'ADR d'ouverture (6.13).
- **Critères de révision** :
  - si le test scellé H2 (6.12) montre H2 significativement moins bon, le rejeu garde H1 (ADR-0047) : la page d'apport et le côte à côte sont à revoir dans l'ADR d'ouverture ;
  - si `check --only rows-h2` diffère du jeu H2 après un nouveau `load`, un nouveau jeu H2 est à construire (E-058).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
