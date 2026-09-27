"""Collecte : sources externes -> fichiers bruts `data/raw/` (rapport F.3, étape [1]).

La collecte n'écrit que dans `data/raw/` et ne dépend ni de Postgres ni de
Docker. Le chargement du brut vers `staging` relève de `ingestion/`.
"""
