"""Stockage du brut en fichiers (ADR-0003).

- `store` : enveloppe `.json.gz`, écriture atomique, jamais d'écrasement ;
- `manifest` : journal des requêtes `data/raw/_manifest/<source>.jsonl` ;
- `backup` : copie de `data/raw/` et vérification des sha256 (ADR-0006).

Ce paquet ne connaît aucune source en particulier : les champs propres à une
API (quota, identifiants de matchs...) lui sont passés par l'appelant.
"""
