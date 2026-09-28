# API-Football : quand payer, comment faire, comment me le dire

Guide de décision pour l'abonnement API-Football, qui est le point bloquant du projet (voir `RECAP_PROJET.md`, section 11).

> ✅ **Abonnement pris et quota confirmé (2026-09-22).** Plan **Pro, 7 500 requêtes/jour**, souscrit pour 1 mois. Le calcul de la section 2 confirme que le backfill complet (18 061 requêtes) tient en ~2,4 jours de quota, largement dans la durée de l'abonnement — **aucune priorisation ni troncature nécessaire**.

---

## 1. Ce que l'abonnement débloque

Sans lui, ces éléments restent vides ou impossibles à calculer :

- `staging.lineup` et `staging.player_match_stats` (aujourd'hui vides) ;
- `squad_avg_age` et `squad_stability_score_season` ;
- tout le module `market_value/` (clustering, MVS), qui n'a jamais tourné sur de vraies données.

État actuel de la base de dev (mis à jour le 2026-09-22 après le backfill 10 saisons) : **18 011 matchs, saisons 2015-2016 à 2024-2025** (Premier League 3 800, La Liga 3 800, Serie A 3 800, Bundesliga 3 060, Ligue 1 3 551), et `raw.api_football_fixture_detail` contient toujours **0 ligne**.

## 2. Combien de requêtes faut-il ?

Le scraper utilise `/fixtures?id=`, soit **1 requête par match terminé**, plus 1 requête par couple (championnat, saison) pour lister les matchs.

Chiffre exact mesuré en base dev le 2026-09-22 : **18 011 matchs joués** dans `staging.match` (0 ligne dans `staging.lineup`, 0 dans `raw.api_football_fixture_detail` — rien n'a encore été téléchargé), + 50 appels de listing (5 championnats × 10 saisons) = **≈ 18 061 requêtes** pour le backfill complet.

| Périmètre | Requêtes | Jours de quota Pro (7 500/jour) |
|---|---|---|
| 1 saison (2024-2025) | ≈ 1 757 | moins de 1 jour |
| 10 saisons, backfill complet (2015-2016 à 2024-2025) | ≈ 18 061 | ≈ 2,4 jours |

Le script est **idempotent et reprenable** : relancé le lendemain, il saute les matchs déjà en base (`_fixture_already_ingested`) sans consommer de quota.

**Conclusion** : avec le plan Pro (7 500/jour) et un abonnement d'1 mois, le backfill complet des 10 saisons tient très largement dans le quota (~2,4 jours sur ~30 disponibles). Pas de priorisation nécessaire.

## 3. Quand payer

**Les prérequis A, B et C sont cochés depuis le 2026-09-22** (section 4). Il ne reste qu'une condition pratique :

- tu es disponible ~3 jours pour relancer le script chaque jour (quota journalier).

Tu peux donc payer dès que cette disponibilité est trouvée.

## 4. Prérequis à faire AVANT de payer

**A. ✅ Fait le 2026-09-22.** `src/foot_predictor/ingestion/mappings/api_football_competitions.yaml` existe et contient les 5 identifiants, confirmés via un vrai appel à l'endpoint `/leagues` (plan gratuit, 1 seule requête, aucune donnée de match consommée) :

```yaml
E0:  {api_football_league_id: 39}    # Premier League, England
SP1: {api_football_league_id: 140}   # La Liga, Spain
D1:  {api_football_league_id: 78}    # Bundesliga, Germany
I1:  {api_football_league_id: 135}   # Serie A, Italy
F1:  {api_football_league_id: 61}    # Ligue 1, France
```

Bonus constaté lors de l'appel : les 5 championnats couvrent les compositions (`coverage.fixtures.lineups`) pour les saisons 2024, 2025 et 2026 côté API-Football.

**B. ✅ Fait le 2026-09-22.** Les 10 saisons (2015-2016 à 2024-2025) sont ingérées côté football-data **et** Understat pour les 5 championnats : 18 011 matchs en `staging.match`, `staging.team` à 160 équipes, 0 doublon. Détail complet, y compris deux bugs trouvés et corrigés au passage (mapping Ajaccio/AC Ajaccio, et un bug plus sérieux où `understat.py` ne persistait jamais le xG) : voir `docs/recaps/recap_backfill_10_saisons_et_bug_xg.md`.

⚠️ Cette correction (renommage d'équipes + `TeamSourceMapping`) ne vit que dans la base de **dev**. Elle devra être reproduite manuellement sur test et prod avant d'y relancer le même backfill.

**C. ✅ Réglé.** Les 10 saisons par défaut sont celles utilisées pour le backfill B — pas besoin de choix supplémentaire.

**D. Contrôles sans risque avec le plan gratuit :**
- `APP_ENV=dev PYTHONIOENCODING=utf-8 uv run python check_env.py` (sans l'encodage, l'affichage des emojis plante sous la console Windows) ;
- vérifier que `api_football_teams.yaml` couvre bien les 96 équipes canoniques (voir la leçon n°1 du RECAP : un mapping corrigé après coup ne répare pas les entités déjà créées).

## 5. Comment faire une fois abonné

1. **S'abonner** sur le site d'API-Football (plan payant avec quota ≥ 7 500/jour et historique complet), puis copier la clé.
2. **Fournir la clé** via la variable d'environnement `API_FOOTBALL_KEY`. Elle est lue par `os.environ` : **elle n'est pas lue dans les fichiers `.env.*`**. Dans un terminal bash :
   ```bash
   export API_FOOTBALL_KEY="ta_clé"
   ```
   Ne la colle jamais dans un fichier versionné, ni dans une conversation.
3. **Lancer le téléchargement** (jour 1) :
   ```bash
   APP_ENV=dev uv run python -m foot_predictor.ingestion.api_football_scraper
   ```
   Le quota étant plafonné à 7 500/jour, le script s'arrêtera en erreur en cours de route : c'est attendu. **Relance-le le lendemain** (le quota est remis à zéro à 00:00 UTC) et ainsi de suite jusqu'à ce qu'il n'y ait plus que des `already_ingested`.
4. **Ingérer en staging** (après le téléchargement) :
   ```bash
   APP_ENV=dev uv run python -m foot_predictor.ingestion.api_football
   ```
5. **Compléter avec Understat par joueur** : `understat_player_scraper.py` puis `understat_player.py` (xG / xA / npxG par joueur).
6. **Vérifier** : nombre de lignes de `staging.lineup` et `staging.player_match_stats`, et taux de lignes ignorées (le RECAP a déjà montré qu'un taux élevé cache un vrai problème de mapping).
7. **Résilier l'abonnement** une fois le backfill terminé, sauf si tu veux ensuite des mises à jour régulières. Les mises à jour quotidiennes (quelques dizaines de matchs) tiennent dans le quota gratuit : à vérifier au moment voulu.

## 6. Comment me le dire plus tard

Je ne garde pas la mémoire d'une conversation à l'autre. Pour reprendre au bon endroit, ouvre une nouvelle conversation dans ce projet et écris quelque chose comme :

> « J'ai pris l'abonnement API-Football (plan X, quota Y/jour). Lis `docs/API_FOOTBALL_ABONNEMENT.md` et `docs/RECAP_PROJET.md`, vérifie les prérequis de la section 4, puis lance le backfill. »

Ce message suffit : je relis ces documents, je vérifie l'état de la base (ce que j'ai fait pendant cette session) et je continue. Précise aussi :
- **le nombre de saisons voulu** (10 par défaut) ;
- **si la clé est déjà définie** dans ton terminal (`API_FOOTBALL_KEY`). Ne me la donne pas : dis-moi seulement qu'elle est en place.

Si tu me demandes de lancer le scraper moi-même, je le ferai seulement après ton feu vert explicite, puisqu'il consomme du quota payant.

## 7. Récapitulatif

| Question | Réponse |
|---|---|
| Quand payer ? | Prérequis A, B, C ✅ tous faits (2026-09-22) — dès que tu es disponible 3 jours de suite |
| Combien de temps l'abonnement ? | 1 mois suffit (backfill ≈ 3 jours pour 10 saisons) |
| Blocage indépendant du paiement | Aucun : les 3 prérequis techniques sont réglés |
| Piège à éviter | Télécharger des saisons absentes de `staging.match` : les lignes seraient ignorées |
| Où mettre la clé ? | Variable d'environnement `API_FOOTBALL_KEY`, pas de fichier `.env` |
| Comment reprendre avec moi ? | Message de la section 6 dans une nouvelle conversation |
