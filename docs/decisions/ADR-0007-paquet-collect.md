# ADR-0007 — Le collecteur v2 vit dans `collect/api_football/`, pas dans `ingestion/api_football/`

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, F.3 et F.9 ; ADR-0004 ; PR du collecteur v2 (branche `fix/03-collecteur-lots-ids`)

## Contexte

Le rapport (F.9) place le futur code API-FOOTBALL dans un paquet `ingestion/api_football/` (`client.py`, `collect.py`, `load.py`). Or `src/foot_predictor/ingestion/api_football.py` existe déjà : c'est le chargement raw vers staging, qu'il est interdit d'exécuter avant la correction de l'identification des joueurs (rapport B.4, D1 et D3 ; ADR-0001).

Quand un dossier-paquet et un module portent le même nom dans le même dossier, Python importe le paquet **sans avertissement**. Créer `ingestion/api_football/` aurait donc :

- rendu l'ancien module inaccessible, sans le modifier ni le supprimer ;
- changé le sens de `python -m foot_predictor.ingestion.api_football`, que `docs/API_FOOTBALL_ABONNEMENT.md` décrit encore comme le chargement vers staging.

## Options envisagées

1. **`ingestion/api_football/`** comme dans le rapport F.9 : l'ancien module est masqué jusqu'à la refonte du chargement (M7). Ambiguïté dangereuse avec la règle « ne jamais exécuter `api_football.py` ».
2. **`collect/api_football/`** : un paquet `collect/` pour l'étape « source vers brut » (rapport F.3, `fp collect`), à côté de `rawstore/` ; `ingestion/` reste l'étape « brut vers staging » (`fp load`).

## Décision

Option 2. Le collecteur se lance avec `python -m foot_predictor.collect.api_football <commande>`.

## Conséquences

- Aucun conflit de nom : l'ancien code d'`ingestion/` reste intact et accessible.
- Deux couches nettes dans le code : `collect/` écrit dans `data/raw/` sans dépendre de Postgres ; `ingestion/` lira `data/raw/` pour alimenter staging.
- Les anciens `api_football_scraper.py` et `injuries_scraper.py` portent un commentaire « obsolète, remplacé par collect/api_football/ (ADR-0004) ».
- À la refonte du chargement (M7), `ingestion/api_football.py` pourra devenir `ingestion/api_football/load.py` sans conflit.
- Critère de révision : si la séparation `collect/` et `ingestion/` complique le futur chargement plus qu'elle ne clarifie, regrouper au moment de la PR de nettoyage.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
