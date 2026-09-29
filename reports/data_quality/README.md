# Rapports de qualité des données

Rapports Markdown produits par le contrôle du brut (rapport de cadrage, G.9) :

```powershell
uv run python -m foot_predictor.quality.raw_check --palier P1 --raw-dir C:/foot-predictor/data/raw
```

Chaque lancement écrit deux fichiers :

| Fichier | Contenu | Git |
|---|---|---|
| `raw_check_<palier>_<AAAA-MM-JJ>.md` | Résumé chiffré : verdict OK / À REGARDER / BLOQUANT, compteurs par contrôle et par championnat-saison. Aucun nom ni identifiant de joueur. | **versionné** |
| `details/raw_check_<palier>_<AAAA-MM-JJ>_details.md` | Listes détaillées : matchs, joueurs (noms, identifiants), fichiers, tâches en échec. | **ignoré** (`.gitignore`) |

Pourquoi deux fichiers : les données restent privées (ADR-0002), mais l'historique des verdicts doit être gardé. Le résumé ne contient donc que des nombres ; les listes nominatives restent sur le poste.

- `<palier>` vaut `tous` si la commande est lancée sans `--palier`, et `P1-P2-P3` pour plusieurs paliers contrôlés ensemble (doublons et collisions calculés sur l'ensemble).
- Relancer le même jour remplace les deux fichiers du jour ; Git garde l'historique des résumés.
- Ne pas modifier à la main : relancer la commande.

Mode d'emploi : `docs/realisation/05_controle_qualite/README.md`.
