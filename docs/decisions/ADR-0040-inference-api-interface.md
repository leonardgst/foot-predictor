# ADR-0040 — Inférence, API et interface : architecture

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : rapport de cadrage, A.2, E.1, F.2, F.5 à F.8, I.8, décisions M10, M18, M21 ; ADR-0009, ADR-0010, ADR-0011, ADR-0012, ADR-0028, ADR-0030, ADR-0036, ADR-0039 ; décisions 1 à 16 de la partie 5

## Contexte

Le modèle MVP H1 est choisi (ADR-0039) et son code est figé jusqu'au test scellé : le tag `pre-scelle-h1` interdit tout changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `src/foot_predictor/seal.py`, `experiments/`, `tests/modeling`, `tests/features`. Il reste à construire ce qui entoure le modèle : calculer les variables d'un match quelconque, prédire avec une matrice de disponibilité, tracer les prédictions, les servir par une API, les montrer dans une interface. Deux dangers : un écart entre entraînement et inférence (une variable calculée autrement au moment de prédire), et une fuite du scellé par le rejeu.

## Options envisagées

1. **Réécrire le calcul des variables pour l'inférence** (requêtes « au jour J ») : rapide à l'exécution, mais une seconde implémentation qui peut diverger.
2. **Appeler la fonction de l'entraînement** (`features.dataset.build_frame`) sur l'historique tronqué au jour du match : une seule implémentation ; coût d'un calcul complet par jour, mis en cache.

Pour l'interface : accès direct à la base ou à la logique métier (simple, mais couplé), ou **passage exclusif par l'API** (rapport F.7).

## Décision

Option 2, et l'interface ne parle qu'à l'API.

**Paquets** (nouveaux, hors des chemins figés) :

| Paquet | Rôle | Dépendances permises |
|---|---|---|
| `inference/` | lignes d'un match quelconque, modèles actif et de rejeu, disponibilité, prédiction, traçabilité (`ops.prediction`), sources live | `features/`, `modeling/`, `db/` (importés, jamais modifiés) |
| `api/` | application FastAPI, schémas Pydantic, routes du rapport F.6 | `inference/` |
| `ui/` | application Streamlit, trois écrans | l'API par `httpx` seulement (ni la base, ni la logique métier) |
| `collect/football_data/` | nouveau fichier `live.py` (prochains matchs, saison courante), à côté du téléchargeur existant, non modifié | `collect/raw_bytes`, `rawstore/` (importés) |

**Variables d'un match quelconque** (décision 2) : `build_frame` est appelée sur la table des matchs de `load_matches` **tronquée au jour J** (`match_day` ≤ J), où les matchs cibles sont copiés avec le statut « joué » et des buts **fictifs**. C'est exact : l'Elo s'applique en fin de jour, les glissants et le calendrier ne lisent que les jours strictement antérieurs ; les buts du jour J ne touchent donc aucune variable du jour J. Les colonnes cibles (`goals_for`, `goals_against`) sont retirées avant usage. On calcule **un jour à la fois** (deux jours ensemble feraient fuir le résultat fictif du premier dans le second), avec un cache par (jour, version des données). Aucun remplissage : une variable incalculable reste vide.

**Modèle de rejeu** (décision 3, ADR-0011 règle 1) : pour une date de la saison S (2021-22 à 2024-25), le modèle est celui du **pli S**, appris sur 2015-16 à S − 1 selon la procédure de `experiments/scelle_h1.yaml` (`modeling.protocol.select_and_fit`), jamais le modèle appris jusqu'en 2024-25. Entraîné à la demande, mis en cache dans `models/rejeu/<S>/` avec sa carte. Ses prédictions doivent reproduire celles de l'évaluation (expérience d'ablation) : c'est la preuve que rejeu et évaluation sont le même objet.

**Modèle actif (live)** (décision 4) : désigné par `ops.model_registry` ; aujourd'hui `scelle-h1-m3_g0g2-20260930-3c92fc80`. Allégé au chargement (`remove_data` de `statsmodels`), prédictions identiques au bit près.

**Disponibilité** (décision 6, rapport F.5, ADR-0011 règle 5) : chaque variable requise est **présente**, **manquante** (avec la raison) ou **périmée** (la source ne contient pas encore tous les matchs antérieurs au jour du match ; raison et date de la dernière mise à jour). Une seule variable non présente ⇒ `unavailable`, **aucune prédiction**, raisons listées. Hors périmètre du modèle (D2, coupes, autres championnats) : statut dédié, jamais de prédiction. H2 : « non disponible avant la partie 6 ».

**Traçabilité** (décision 7) : migration 0008 additive, `ops.prediction` et `ops.model_registry` ; modes `replay` et `live` séparés ; prédiction live écrite **avant le coup d'envoi** seulement ; création idempotente.

**API** (décision 8) : FastAPI, uvicorn, liaison **127.0.0.1** ; pas d'authentification ni de CORS (usage local) ; entrées validées par Pydantic ; aucun chemin de fichier fourni par le client ; aucun secret ni URL de base dans une réponse ; erreurs explicites (409 indisponible, 403 saison non ouverte, 501 H2, 404).

**Scellé** : en phase A, le rejeu ne s'ouvre que sur 2021-22 à 2024-25, et toute date de référence à partir du 1er juillet 2025 est refusée tant que le journal ne contient pas l'évaluation terminée de `experiments/scelle_h1.yaml` (`modeling.sealed.already_evaluated`). Le live réel attend la phase B.

**Vérifications sur données réelles** : l'égalité au bit près avec le jeu `ds-2026-09-30-ba2b91f7` et la reproduction du rejeu demandent les données locales (absentes en CI) : elles passent par une commande (`python -m foot_predictor.inference check`) qui écrit son rapport dans `reports/inference/` ; les tests automatisés, eux, portent sur des données synthétiques.

## Conséquences

- Dépendances : groupes `api` (`fastapi`, `uvicorn`, `httpx`) et `ui` (`streamlit`), commentés dans `pyproject.toml`.
- **Repoussé** : Compose à trois services et réseau Docker interne (partie 6, rapport F.8) ; horizon H2 (partie 6) ; planification du rafraîchissement live (partie 6).
- Coût : un calcul complet des variables (quelques secondes) par jour demandé, amorti par le cache ; à mesurer (sous-étape 5.1).
- **Critère de révision** : un écart entre une ligne d'inférence et la ligne du jeu d'entraînement pour le même match, ou des temps de réponse trop longs pour l'interface (plus de quelques secondes à chaud) ; dans ce cas, revoir le calcul par jour (calcul incrémental) dans une nouvelle ADR, toujours sans seconde implémentation des variables.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
