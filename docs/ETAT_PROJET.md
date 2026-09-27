# État du projet

**Dernière mise à jour** : 2026-09-27
**Jalon courant** : J1 — Collecteur v2 (rapport de cadrage, partie L)
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel des données le **19 octobre** (ADR-0005)

## Terminé

- Rapport de cadrage (`docs/cadrage/rapport_cadrage_2026-09-24.md`).
- ADR-0001 à 0006 acceptées : ancien backfill arrêté et recollecté par le v2, périmètre maximal par paliers, brut en fichiers, collecteur v2, calendrier de gel, sauvegarde unique au gel.
- Documentation de suivi en place : `CLAUDE.md`, cet état, `docs/JOURNAL_ERREURS.md`, `docs/decisions/`.
- Collecteur v2 écrit et testé sans réseau (branche `fix/03-collecteur-lots-ids`) : `rawstore/`, `collect/api_football/`, `config/collecte_api_football.yaml`, ADR-0007 (emplacement du code), mode d'emploi `docs/realisation/03_collecte/README.md`.

## En cours

- Collecteur v2 : PR ouverte depuis `fix/03-collecteur-lots-ids`, à relire et fusionner. Aucune requête réelle n'a encore été faite avec lui.

## Bloqué

- Rien. Points de vigilance :
  - ne pas exécuter `ingestion/api_football.py` (raw vers staging) avant correction de l'identification des joueurs (rapport B.4, D1 et D3) ;
  - ne jamais lancer `docker compose down -v` ni supprimer `data/raw/` avant le gel ;
  - lancer `coverage` **avant** `plan --palier P1` (sinon, les saisons inexistantes seront planifiées puis marquées `suspect`).

## Décisions ouvertes

- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord.
- À trancher avant le 19 octobre : M7 à M12 (référentiel d'identifiants, cible et métrique, horizon, mode rejeu, protocole de validation, masse salariale et MVS).

## Prochaines actions

**Court terme (d'ici le 1er octobre)**

- [ ] Collecteur v2 écrit, relu, fusionné (ADR-0004). *Écrit et testé ; reste la relecture et la fusion de la PR.*
- [x] Clé API dans `.env.dev` (lue par `config.py`, facultative).
- [ ] Inventaire de couverture (`coverage`) → `docs/realisation/03_collecte/couverture.md` ; vérifier les identifiants du YAML.
- [ ] `plan --palier P1`, `run --dry-run`, puis premier essai `run --max-requests 20`, fichiers vérifiés (`status`, `backup` vers un dossier temporaire).

**Moyen terme (d'ici le 19 octobre)**

- [ ] Palier P1 (2-8 oct.) ; outil de contrôle qualité du brut ; contrôles P1 (rapport G.9).
- [ ] Paliers P2, P3, P4 et journal quotidien (9-16 oct.).
- [ ] Fin de collecte et rattrapages (17-18 oct.).
- [ ] Gel le 19 oct. : `DATA_FREEZE.md`, export sur disque externe, test de restauration, tag `data-freeze-2026-10`.
- [ ] Trancher M7 à M12 (ADR 0008 et suivantes ; l'ADR-0007 porte sur l'emplacement du collecteur).

**Long terme**

- Restructuration de `docs/` (rapport K), référentiel reconstruit depuis le brut (J3), variables v2 (J4), protocole et références (J5), modèle MVP (J6), API (J7), interface et `v1.0.0` (J8) : voir rapport, partie L.

## Début de la prochaine session

```bash
git status && git log --oneline -5
uv run pytest -m "not db" -q
```

Puis reprendre la première case non cochée ci-dessus. Après la fusion de la PR du collecteur, la séquence exacte (coverage, plan, dry-run, essai de 20 requêtes) est dans `docs/realisation/03_collecte/README.md`, section « Première utilisation ».

Suivi quotidien de la collecte :

```bash
uv run python -m foot_predictor.collect.api_football status
uv run python -m foot_predictor.collect.api_football run
```
