# État du projet

**Dernière mise à jour** : 2026-09-27
**Jalon courant** : J1 — Collecteur v2 (rapport de cadrage, partie L). Critère de fin : détails du top 5 collectés **et contrôlés**.
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel des données le **19 octobre** (ADR-0005)

## Terminé

- Cadrage intégré (PR #5) : rapport `docs/cadrage/rapport_cadrage_2026-09-24.md`, ADR-0001 à 0006, `CLAUDE.md`, cet état, `docs/JOURNAL_ERREURS.md`.
- Collecteur v2 fusionné (PR #6) : `rawstore/`, `collect/api_football/`, `config/collecte_api_football.yaml`, ADR-0007, mode d'emploi `docs/realisation/03_collecte/README.md`.
- Inventaire de couverture fusionné (PR #7) : `docs/realisation/03_collecte/couverture.md`. Les 30 identifiants du YAML sont présents dans `/leagues`, avec le bon nom et le bon pays.
- Contrôle qualité du brut fusionné (PR #8) : `quality/raw_check.py`, résumé versionné dans `reports/data_quality/`, listes dans `details/` (non versionné). Mode d'emploi : `docs/realisation/05_controle_qualite/README.md`.
- Collecte P1 lancée le 2026-09-27 dans `C:/foot-predictor` (dossier de collecte, à ne pas toucher pendant qu'elle tourne).

## En cours

- **Collecte P1** : top 5 et D2 (2015-2026), coupes d'Europe et nationales, équipes, blessures, joueurs, entraîneurs, transferts. Suivi : commande `status`.
- **PR #9** (`feat/03-rafraichir-saison`) : commande `refresh --season 2026 [--palier P1]`, qui remet en file les listes de matchs, équipes et blessures de la saison en cours. Le `run` suivant crée les lots des seuls matchs devenus terminaux. Testée sans réseau, jamais lancée sur les vraies données. Mode d'emploi : `docs/realisation/03_collecte/README.md`, section « Saison en cours ».

## Bloqué

- Rien. Points de vigilance :
  - ne pas exécuter `ingestion/api_football.py` (raw vers staging) avant correction de l'identification des joueurs (rapport B.4, D1 et D3) ;
  - ne jamais lancer `docker compose down -v` ni supprimer `data/raw/` avant le gel ;
  - travailler le code dans une autre copie du dépôt (`C:/fp-travail`) tant que la collecte tourne dans `C:/foot-predictor` ; n'y lire `data/raw/` qu'en lecture seule.

## Décisions ouvertes

- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord.
- À trancher avant le 19 octobre : M7 à M12 (référentiel d'identifiants, cible et métrique, horizon, mode rejeu, protocole de validation, masse salariale et MVS).

## Prochaines actions

**Court terme**

- [x] Collecteur v2 écrit, relu, fusionné (ADR-0004, PR #6).
- [x] Clé API dans `.env.dev` (lue par `config.py`, facultative).
- [x] Inventaire de couverture (`coverage`) et identifiants du YAML vérifiés (PR #7).
- [x] `plan --palier P1` et lancement de la collecte P1 (2026-09-27).
- [x] Relire et fusionner la PR #8 (contrôle qualité du brut).
- [ ] Commande `refresh` de la saison en cours (prompt F). *Écrite et testée ; reste la relecture et la fusion de la PR, puis `git pull` dans `C:/foot-predictor` entre deux `run`.*
- [ ] `refresh --season 2026 --palier P1` vers le **10 octobre** (d'abord `--dry-run` pour le coût, puis `run`).
- [ ] À la fin de la collecte P1 : contrôle qualité de P1 (`raw_check --palier P1`). Il faut zéro BLOQUANT et chaque « à regarder » examiné avant de planifier P2 (ADR-0002).
- [ ] Vérifier une copie du brut, une fois la collecte arrêtée : `backup` vers un dossier temporaire.

**Moyen terme (d'ici le 19 octobre)**

- [ ] Paliers P2, P3, P4 et journal quotidien (9-16 oct.), chacun contrôlé avec `raw_check`.
- [ ] Fin de collecte et rattrapages (17-18 oct.).
- [ ] Gel le 19 oct. : dernier `refresh --season 2026` le matin, puis `run`, `raw_check` sur tous les paliers, `DATA_FREEZE.md`, export sur disque externe, test de restauration, tag `data-freeze-2026-10`.
- [ ] Trancher M7 à M12 (ADR-0008 et suivantes).

**Long terme**

- Restructuration de `docs/` (rapport K), référentiel reconstruit depuis le brut (J3), variables v2 (J4), protocole et références (J5), modèle MVP (J6), API (J7), interface et `v1.0.0` (J8) : voir rapport, partie L.

## Début de la prochaine session

Dans `C:/fp-travail` (la collecte tourne dans `C:/foot-predictor`) :

```bash
git status && git log --oneline -5
uv run pytest -m "not db" -q
```

Puis reprendre la première case non cochée ci-dessus.

Suivi de la collecte, dans `C:/foot-predictor` (aucune requête) :

```bash
uv run python -m foot_predictor.collect.api_football status
```

Contrôle qualité d'un palier, depuis `C:/fp-travail`. Il lit le brut en lecture seule et écrit le résumé dans `reports/data_quality/`, les listes dans `reports/data_quality/details/` :

```bash
uv run python -m foot_predictor.quality.raw_check --palier P1 --raw-dir C:/foot-predictor/data/raw
```
