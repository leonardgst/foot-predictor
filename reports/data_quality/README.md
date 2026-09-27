# Rapports de qualité des données

Rapports Markdown **versionnés** (rapport de cadrage, G.9), produits par :

```powershell
uv run python -m foot_predictor.quality.raw_check --palier P1 --raw-dir C:/foot-predictor/data/raw
```

- Nom : `raw_check_<palier>_<AAAA-MM-JJ>.md` (`tous` sans `--palier`). Un rapport par palier et par jour : relancer le même jour remplace le fichier, et Git garde l'historique.
- Contenu : un résumé (OK, À REGARDER, BLOQUANT), puis le détail par championnat-saison. Les listes d'anomalies sont tronquées (`--max-items`, 50 par défaut) pour que les rapports restent légers.
- Ne pas modifier à la main : relancer la commande.

Mode d'emploi : `docs/realisation/05_controle_qualite/README.md`.
