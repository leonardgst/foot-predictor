# ADR-0045 — Ouverture du scellé à l'inférence seulement, après le test H1 ; rejeu des saisons scellées fermé jusqu'au test de H2

- **Statut** : acceptée
- **Date** : 2026-10-22
- **Référence** : ADR-0011 (règle 2, précisée ici), ADR-0012 (règles 4 et 5), ADR-0028 (porte unique), ADR-0040, ADR-0043, ADR-0044 ; partie 5, phase B, sous-étape 5.13

## Contexte

- **Le test scellé H1 est terminé** (ADR-0043) et le modèle final est entraîné (ADR-0044). Le journal `reports/sealed_tests.md` contient « évaluation terminée » pour `experiments/scelle_h1.yaml`.
- **L'inférence lit les matchs par la porte** `features/sources.load_matches`, qui coupe tout au 1er juillet 2025 (ADR-0028). `build_frame` refuse aussi un historique qui contient des matchs scellés. Or le live de 2026-27 a besoin de 2025-26 et du début de 2026-27 comme historique : sans eux, l'Elo et les moyennes glissantes seraient ceux de juin 2025.
- **L'ADR-0012** prévoit, règle 4, une seule exception au scellé : « leur usage comme historique pour calculer des variables à l'inférence, une fois le modèle figé ». Elle prévoit aussi, règle 5 (variante b), un **second test** sur les mêmes matchs, pour la version intermédiaire (H2, jalon J9) : il mesurera l'écart entre H2 et le modèle H1 figé.
- **L'ADR-0011, règle 2**, ouvre le rejeu « à toutes les saisons » après « le test final sur la saison scellée ». Le code de la phase A (`inference/models.check_replay_season`) l'a lu comme le test H1. Or un rejeu des saisons scellées affiche, match par match, scores et prédictions de matchs que le test de H2 réutilisera, pendant le développement de H2.
- **Journal** : chaque lecture du scellé par `sealed_test=True` y ajoute une ligne. L'inférence lirait l'historique à chaque démarrage de l'API ou commande `predict` : un fichier suivi par Git, modifié en permanence (voir E-061 pour l'effet sur les champs `dirty`).

## Options envisagées

1. **Ouverture à l'inférence seulement, comme historique ; rejeu des saisons scellées fermé jusqu'au test de H2 ; garde par le code, sans ligne de journal par lecture.** Le live fonctionne ; aucun score ni aucune cote d'un match scellé n'est servi ; le second test reste protégé. Il faut corriger le code de la phase A, qui ouvrait le rejeu.
2. **Ouverture complète dès maintenant** (rejeu des saisons scellées, score réel, cotes), selon la lecture actuelle du code. Démonstration plus riche, mais le développement de H2 se ferait en voyant les matchs de son test.
3. **Une ligne de journal par lecture de l'inférence.** Le plus traçable, mais le journal grossit sans fin et l'arbre Git n'est jamais propre.
4. **Ne rien ouvrir.** Le live serait faux (historique arrêté en juin 2025) ou toujours indisponible.

## Décision

Option 1, choisie par l'utilisateur le 2026-10-22 (rejeu fermé jusqu'à H2 ; garde par le code).

- **Porte** : `load_matches(..., opened_for_inference=True)` lève le filtre du scellé pour l'inférence.
  - Refus (`SealViolation`), **avant toute lecture**, tant que le journal ne contient pas « évaluation terminée » pour `experiments/scelle_h1.yaml` (`seal.check_opened_for_inference`).
  - Aucune ligne n'est ajoutée au journal. L'option est incompatible avec `sealed_test`.
  - **Réservée à `inference/`** : un test d'architecture refuse cet argument partout ailleurs (`features/`, `modeling/`, notebooks, autres modules).
  - `load_odds` n'a pas d'ouverture : les cotes des matchs scellés restent fermées pour tous.
- **Développement inchangé** : `features build` (sans `--sealed-test`), `evaluate`, les notebooks et `modeling/` gardent le filtre jusqu'au test de H2.
- **Inférence** :
  - `build_context` ouvre la table des matchs quand le test H1 est terminé (`InferenceContext.history_opened`) ;
  - lignes d'un jour : même fonction qu'à l'entraînement (ADR-0040). Pour un jour scellé et une table ouverte seulement, `build_frame` est appelé avec son option `sealed_test=True`, qui accepte l'historique scellé sans rien changer au calcul (c'est l'appel qui a construit le jeu du test et du modèle final). Avant le scellé, l'appel ne change pas ;
  - **live** : matchs à venir, avec l'historique complet. Les valeurs des variables affichées (Elo, moyennes glissantes) résument des matchs scellés : c'est l'usage permis par l'ADR-0012, règle 4 ;
  - **rejeu** : 2021-22 à 2024-25 seulement, **jusqu'au test scellé de H2**. Le score réel et la cote d'un match scellé ne sont jamais servis.
- **Règle 2 de l'ADR-0011, précisée** : le « test final sur la saison scellée » est le test de H2, le dernier prévu sur ces matchs. Le rejeu des saisons scellées s'ouvrira par une nouvelle ADR, après ce test.
- **Modèle actif** : le modèle final H1 (`scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`) est inscrit et activé dans `ops.model_registry` (commande `inference models --activate <version>`) ; il devient aussi la version par défaut du code.
- **Contrôle sur données réelles** (`inference check --only rows-scelle`, sur demande seulement) : sur des jours de la période scellée, les lignes de l'inférence doivent être identiques au bit près à celles du jeu scellé `ds-2026-10-22-94969da0`. La lecture du jeu scellé est journalisée ; le rapport ne publie que des dates, des décomptes et des noms de colonnes.

## Conséquences

- Fichiers : `seal.py`, `features/sources.py`, `inference/` (`context.py`, `rows.py`, `predict.py`, `models.py`, `check.py`, `__main__.py`), texte d'aide de l'interface ; tests de la porte, d'architecture, des lignes, de la prédiction et du rejeu. Aucun changement sous `modeling/` ni `experiments/` (garde du modèle H1, ADR-0044).
- Le live réel (football-data superposé, ADR-0042) se branche en 5.14 sur cette table ouverte. D'ici là, un match à venir est « périmé » : `staging` s'arrête au gel.
- **Ce que l'utilisateur voit des matchs scellés pendant le développement de H2** : seulement les variables du live, agrégées. Le test de H2 en tiendra compte dans sa propre ADR.
- On s'interdit : tout autre usage de `opened_for_inference`, toute ouverture de `load_odds`, tout rejeu des saisons scellées avant le test de H2.
- **Critère de révision** : un score, une cote ou une prédiction de rejeu d'un match scellé servi par l'API ou l'interface, ou un usage de l'option hors de `inference/`. Le constater dans une nouvelle ADR et restreindre la conclusion du test de H2 en conséquence (ADR-0012, critères de révision).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
