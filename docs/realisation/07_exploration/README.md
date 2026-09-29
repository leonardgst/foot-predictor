# Étape 07 : exploration statistique (jalon J4)

Quatre notebooks **descriptifs** dans `notebooks/` (ADR-0034). Ils décrivent les données et les variables du jeu versionné ; ils ne choisissent **aucune** variable ni **aucun** paramètre : la sélection appartient au protocole de la partie 4 (validation glissante, ablation, ADR-0012). **Corrélation n'est pas apport** : un lien descriptif peut venir d'une autre variable (la force des équipes, surtout), et seul un gain mesuré dans les plis, à variables données, justifie une variable.

## Lancer les notebooks

```bash
uv sync --all-groups                      # groupe « explo » : ipykernel, matplotlib, nbclient, nbformat
uv run python -m foot_predictor.features build   # s'il n'existe encore aucun jeu dans data/datasets/
# puis ouvrir notebooks/*.ipynb dans VS Code (noyau : .venv du projet)
```

- Les notebooks lisent les données **par la porte seulement** (`foot_predictor.features.sources` : `load_dataset`, `load_matches`) : période de développement, matchs antérieurs au 1er juillet 2025 (scellé, ADR-0012 et ADR-0028). Un test d'architecture refuse tout autre import du projet, et tout accès SQL.
- Ils sont versionnés **sans sorties** : le hook `nbstripout` les efface au commit. Les chiffres ci-dessous viennent d'une exécution du 2026-09-29 sur `ds-2026-09-29-83d28f3b`.

## Résumé des conclusions

| Notebook | Question | Ce qu'on voit |
|---|---|---|
| `01_cible.ipynb` | Comment se distribue le nombre de buts ? | Total moyen de 2,0 à 3,3 buts selon le championnat et la saison. Avantage du terrain en baisse (+0,51 but en 2000-01, +0,17 en 2024-25, creux de +0,15 en 2020-21). Rapport variance / moyenne du total entre 0,99 et 1,06 : Poisson correct en marginal ; 0-0 un peu plus fréquent que prévu. Huis clos : écart domicile − extérieur de 0,19 contre 0,29 |
| `02_elo.ipynb` | L'Elo est-il calibré, et lié aux buts ? | Espérance bien ordonnée mais trop extrême en probabilité brute. Le total croît avec l'écart absolu (2,54 buts quand l'écart est faible, 3,03 au-delà de 200 points). Corrélation de 0,957 d'une saison à l'autre |
| `03_glissants_xg_proxy.ipynb` | Glissants et xg_proxy ? | Corrélation avec les buts de l'équipe de 0,27 à 0,29 selon la demi-vie (Elo : 0,33). xg_proxy contre xG d'API-FOOTBALL : 0,685. Ancienneté maximale presque jamais atteinte (0,27 % de lignes vides) |
| `04_calendrier.ipynb` | Repos et charge ? | Repos fiable depuis 2015-16 (100 % depuis 2018-19). Repos court et match européen récent vont avec *plus* de buts, parce que ce sont des équipes plus fortes (Elo 1 666 contre 1 534) : confusion, à trancher par ablation |

## Limites

- Descriptif seulement : aucun modèle, aucune incertitude chiffrée (pas d'intervalle de confiance).
- Le repos n'est comparable qu'à partir de 2015-16 ; avant, seuls les championnats sont connus.
- L'xg_proxy de la Serie A est biaisé de 2018-19 à 2020-21 par une rupture de série des tirs de football-data (ADR-0029, ADR-0032).
- Les notebooks s'exécutent en une minute environ ; aucun n'écrit de fichier.
