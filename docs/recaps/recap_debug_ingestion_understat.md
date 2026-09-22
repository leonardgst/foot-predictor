# Récap — Debug de l'ingestion Understat (568 → 0 lignes ignorées)

Ce document complète `recap_etape3_pipeline_et_mvs.md`. Il couvre une session de
diagnostic et de correction menée sur le pipeline d'ingestion `raw -> staging`,
suite à un taux de lignes ignorées anormalement élevé lors du lancement de
`understat.py`.

**Contexte** : à ce stade, les scripts d'ingestion API-Football n'ont pas encore
été lancés (abonnement payant pas encore pris, et le plan gratuit ne couvre que
les 2 derniers jours — sans matchs des championnats suivis). Tout ce qui suit
ne concerne donc que football-data.co.uk et Understat (niveau équipe).

**Statut à la fin de cette session** : bug corrigé, 0 ligne ignorée sur
1752 lignes de xG équipe traitées par `understat.py`. Fix commité (voir section 6).

---

## 1. Symptôme initial

```bash
$ APP_ENV=dev uv run python -m foot_predictor.ingestion.understat
1184 lignes de xG traitées, 568 ignorées (match/team_match introuvable).
```

Soit environ 32% des lignes ignorées — taux jugé anormalement élevé pour mériter
un diagnostic avant de poursuivre le pipeline (impact direct sur les features xG,
donc en aval sur le MVS et la prédiction).

---

## 2. Hypothèses explorées et écartées

| # | Hypothèse | Verdict | Comment vérifié |
|---|---|---|---|
| 1 | Noms d'équipe Understat avec underscore (`Manchester_United`) non normalisés avant lookup dans le mapping YAML, créant des équipes dupliquées | ❌ Écartée | `SELECT ... WHERE name LIKE '%\_%'` sur `staging.team` : aucune ligne |
| 2 | Écart de couverture de saison/compétition entre football-data et Understat (un match scrapé par l'un mais pas encore par l'autre) | ❌ Écartée | Comptage `staging.match` par compétition : 306/380/306/380/380, identique aux volumes annoncés par Understat |
| 3 | Décalage de date (fuseau horaire) entre les deux sources | ✅ Confirmée, mais marginale | 2 cas sur 1752 seulement (voir section 5) |
| 4 | Équipes dupliquées suite à une correction tardive du mapping `football_data_teams.yaml`, jamais reconciliée en base | ✅ **Cause principale** | Script de diagnostic dédié (section 3) : 19 doublons trouvés |

Le fix de normalisation underscore (hypothèse 1) a quand même été appliqué par
précaution dans `common.py` — inoffensif, mais ce n'était pas la vraie cause.

---

## 3. Cause racine identifiée : mapping corrigé après coup, entités jamais reconciliées

### Mécanisme

Dans `common.py`, `get_or_create_team()` fonctionne ainsi :
1. Cherche d'abord dans `TeamSourceMapping (source_name, source_ref)`. Si trouvé
   → renvoie l'id directement, **sans jamais reconsulter le fichier YAML**.
2. Sinon seulement, consulte `teams_mapping.get(source_ref)` pour trouver le nom
   canonique, crée/retrouve l'équipe, et enregistre le mapping pour la prochaine fois.

Conséquence : si `football_data_teams.yaml` ne contenait pas encore une entrée
au moment du tout premier run de `football_data.py` (ex. `Ath Bilbao` portait le
commentaire `# à confirmer : vérifie le code exact dans le CSV SP1`, signe que
cette entrée a été ajoutée/corrigée après coup), alors :

1. Premier run `football_data.py` : lookup échoue → fallback sur le nom brut
   (`"Ath Bilbao"`) → équipe créée avec ce nom brut → `TeamSourceMapping`
   enregistré **définitivement** vers cet id.
2. Le YAML est corrigé par la suite.
3. Relancer `football_data.py` ne change plus rien pour ce club : l'étape 1
   ci-dessus trouve directement le mapping existant, sans jamais revalider
   contre le YAML corrigé.
4. `understat.py`, lui, n'avait encore aucun mapping enregistré pour ce club
   → applique son propre YAML (déjà correct) → crée une **deuxième** équipe,
   sous le nom canonique cette fois.
5. Les deux id ne se recoupent jamais → tous les matchs de ce club échouent à
   la résolution cross-source (`resolve_match_cross_source` cherche par
   `home_team_id`/`away_team_id`, qui ne correspondent jamais entre les deux
   sources pour ce club).

### Diagnostic — script de détection des doublons

Script one-off (lecture seule) comparant, pour chaque entrée du mapping
`football_data_teams.yaml`, si le nom brut et le nom canonique existent tous
les deux comme `staging.team` distincts, avec un comptage de références
(`Match`, `TeamMatch`) de chaque côté pour identifier sans ambiguïté lequel
porte les données.

### Résultat : 19 doublons trouvés, tous avec le même profil (nom brut = 34-38
matchs/team_match, nom canonique = 0)

| Championnat | Clubs concernés |
|---|---|
| La Liga (7) | Atletico Madrid, Athletic Club, Celta Vigo, Rayo Vallecano, Real Betis, Real Sociedad, Real Valladolid |
| Bundesliga (9) | Bayer Leverkusen, Borussia Dortmund, Borussia Monchengladbach, Eintracht Frankfurt, FSV Mainz 05, VfB Stuttgart, 1899 Hoffenheim, VfL Bochum, VfL Wolfsburg |
| Serie A (2) | Parma Calcio 1913, Hellas Verona |
| Ligue 1 (1) | Stade Brestois 29 |
| Premier League | Aucun doublon — mapping correct dès le premier run |

---

## 4. Correction appliquée — fusion des doublons

Script one-off (avec mode `DRY_RUN` par défaut) : pour chaque paire détectée,
identifie l'id qui porte les données (`keep_id`) et celui qui est vide
(`drop_id`), reroute les `TeamSourceMapping` du `drop_id` vers le `keep_id`,
supprime l'équipe vide, puis renomme l'équipe conservée avec le nom canonique.

Le script inclut un garde-fou : si les **deux** côtés d'une paire ont des
données (`raw_refs > 0 and canon_refs > 0`), il logue un conflit réel et
**ne fusionne pas automatiquement** — aucun cas de ce type rencontré ici,
mais le garde-fou reste en place pour une prochaine source.

Exécuté en dry-run puis en réel : **19 fusions appliquées et commitées**
sans conflit détecté.

---

## 5. Reste après fusion : 2 cas de décalage de date (±1 jour)

Après la fusion des 19 doublons, un nouveau run de `understat.py` (avec
instrumentation diagnostic temporaire) est passé de 568 à 2 lignes ignorées :

| Match | Date Understat | Date en staging |
|---|---|---|
| St. Pauli - Holstein Kiel | 2024-11-30 | 2024-11-29 |
| Genoa - Atalanta | 2025-05-18 | 2025-05-17 |

Hypothèse retenue : décalage de fuseau horaire selon que la source encode
l'horodatage en UTC ou en heure locale avant de tronquer à la date — plausible
pour des matchs à coup d'envoi tardif (fin novembre = heure d'hiver UTC+1,
mi-mai = UTC+2).

### Fix appliqué

`resolve_match_cross_source()` (`common.py`) : la comparaison stricte de date
(`cast(Match.match_date, Date) == match_date.date()`) est remplacée par une
tolérance de ±1 jour (`.between(date_min, date_max)`).

⚠️ Point de vigilance noté pour plus tard : cette tolérance élargie pourrait
poser problème si une même paire d'équipes se rencontre deux fois à moins de
2 jours d'écart (ex. championnat + coupe nationale la même semaine) — non
problématique aujourd'hui (seuls les championnats sont suivis), à surveiller
si les coupes nationales sont ajoutées au périmètre.

**Résultat final** :
```bash
$ APP_ENV=dev uv run python -m foot_predictor.ingestion.understat
1752 lignes de xG traitées, 0 ignorées (match/team_match introuvable).
```

---

## 6. Fichiers modifiés

- **`src/foot_predictor/ingestion/common.py`**
  - Normalisation underscore → espace pour les `source_ref` Understat avant
    tout lookup (précaution, cause écartée mais fix inoffensif conservé)
  - `resolve_match_cross_source()` : tolérance de date élargie à ±1 jour
- **`src/foot_predictor/ingestion/understat.py`**
  - Normalisation des noms d'équipe avant résolution
  - Instrumentation diagnostic temporaire (détail des lignes ignorées) —
    à retirer ou garder derrière un flag selon préférence
- **`src/foot_predictor/ingestion/understat_player.py`**
  - Même normalisation appliquée (même vulnérabilité que `understat.py`,
    puisqu'il partage `get_or_create_team`)

## Scripts one-off (diagnostic/fusion), conservés dans `scripts/one_off/`

- `check_raw.py` — liste les valeurs brutes `home_team`/`away_team` réellement
  stockées en base pour une division donnée (comparaison caractère par
  caractère avec le YAML)
- `check_duplicates.py` — détecte toutes les paires (nom brut / nom canonique)
  existant comme `staging.team` distincts, avec comptage de références
- `fusion.py` — fusionne les doublons détectés (mode dry-run par défaut)

Conservés pour référence : le même mécanisme (mapping corrigé après coup,
entité jamais reconciliée) pourra resurgir avec le mapping API-Football,
une fois son ingestion lancée.

---

## 7. Point de vigilance pour la suite (à ajouter aux leçons apprises du projet)

**Corriger un fichier de mapping YAML ne suffit jamais, à lui seul, à réparer
une entité déjà créée en base.** La logique `get_or_create_*` de `common.py`
priorise systématiquement le `*_source_mapping` déjà enregistré sur le
contenu du YAML. Toute correction de mapping après coup doit s'accompagner
d'une vérification (voire d'un script de fusion façon `fusion.py`) pour les
entités concernées déjà résolues avant la correction.

À garder en tête en particulier pour :
- Les futures corrections de `api_football_teams.yaml` une fois l'ingestion
  API-Football lancée
- Toute correction de `football_data_competitions.yaml` (même logique de
  mapping-first pour les compétitions)

---

## 8. Prochaines étapes (inchangées, rappel)

Toujours en attente, aucun impact de cette session dessus :
- [ ] Abonnement API-Football à prendre pour lancer l'ingestion compositions
  + `player_match_stats` (bloque `lineup`, `player_match_stats`, tout le
  module `market_value/`, et les colonnes `squad_avg_age`/
  `squad_stability_score_season` de `features.team_match_features`)
- [ ] Choix du modèle statistique final pour le score exact (Poisson / Dixon-Coles)
- [ ] Stratégie de test automatisé (`tests/` toujours vide)
- [ ] Consommation de `raw.api_football_injuries` (capturée mais pas ingérée)
- [ ] Stratégie précise de scraping planifié (cron/fréquence)

Nouveau point ajouté suite à cette session :
- [ ] Décider si l'instrumentation diagnostic ajoutée à `understat.py` est
  gardée en permanence (utile pour un futur run sur de nouvelles saisons) ou
  retirée maintenant que le bug est corrigé

---

*Document généré à partir de l'échange avec Claude — à intégrer à la suite de
`recap_etape3_pipeline_et_mvs.md`.*
