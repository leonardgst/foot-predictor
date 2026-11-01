# Étape 07 : exploration statistique (jalons J4 et J9)

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

## Partie 6 : `05_composition_h2.ipynb` (lot 6.6, 2026-11-01)

Même règle que les quatre premiers : **descriptif seulement**, aucune variable ni aucun paramètre choisi (la demi-vie de la cohésion, l'ordre des groupes et les variantes appartiennent à 6.7, ADR-0047). Il lit le jeu H2 `ds-2026-11-01-94e07897` par la porte (`load_dataset`), période de développement, top 5 de 2016-17 à 2024-25 (2015-16 sert de rodage à G5, 2016-17 à G4, D3). Exécution : 12 secondes.

| Question | Ce qu'on voit |
|---|---|
| Couverture | À partir de 2021-22, au plus 0,3 % de valeurs vides ; rodage visible en 2015-16 (G4 vide à 100 %) et 2016-17 |
| Début de saison (rapport H.4) | Variance du recouvrement plus forte aux journées 1 à 5 (écart type 2,0 contre 1,5 à 1,7), 2,3 nouveaux titulaires contre 0,5, 36 % de nouveaux entraîneurs contre 5 à 10 %. Les cohésions courtes montent avec la journée (h3 : 0,37 puis 0,47) ; `hinf` ne bouge presque pas (0,058 puis 0,068) : inerte sans décroissance, comme H.4 l'annonçait |
| Variantes de stabilité (H.3) | Cohésions voisines corrélées à 0,96 à 0,98 ; avec le recouvrement du dernier match : 0,71 (h3) à 0,11 (hinf). **L'annonce « plus de 0,9 entre paires et recouvrement » ne se vérifie pas** sans remise à zéro. Habituels absents / cohésion h5 : −0,85 |
| Confusion avec la force | `xi_quality` corrélée à 0,83 avec l'Elo (0,28 avec les buts) ; à Elo donné, 0,07. Toutes les autres : moins de 0,02 en valeur absolue. Les liens bruts viennent de la force des équipes |
| Qualité du XI entre championnats (D9) | Notes moyennes de 6,88 à 6,99 ; dans chaque pays la D2 est sous la première division. Pas de dérive d'une saison à l'autre |
| Entraîneur | Ancienneté et buts vont de pair, mais l'Elo aussi (1 507 contre 1 562). Censure à gauche de 2016-17 : 19,5 % de nouveaux (10 % ensuite), 0 % au plafond (47 à 52 % ensuite) |

Points à surveiller en 6.7 : la redondance habituels absents / cohésion, la quasi-identité de `xi_quality` avec l'Elo, l'inertie de `hinf`. Limites : corrélations linéaires, une seule exécution, aucun intervalle ; « à Elo donné » est une corrélation après retrait de la part linéaire de l'Elo, pas un gain de modèle.

## Limites

- Descriptif seulement : aucun modèle, aucune incertitude chiffrée (pas d'intervalle de confiance).
- Le repos n'est comparable qu'à partir de 2015-16 ; avant, seuls les championnats sont connus.
- L'xg_proxy de la Serie A est biaisé de 2018-19 à 2020-21 par une rupture de série des tirs de football-data (ADR-0029, ADR-0032).
- Les notebooks s'exécutent en une minute environ ; aucun n'écrit de fichier.
