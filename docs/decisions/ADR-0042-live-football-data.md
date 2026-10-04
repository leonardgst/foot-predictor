# ADR-0042 — Live : football-data superposé en mémoire au calendrier API figé

- **Statut** : acceptée
- **Date** : 2026-10-04
- **Référence** : rapport de cadrage, C.3, F.5, G.11 ; ADR-0008 (règle 2), ADR-0011 (règles 3 et 5), ADR-0012, ADR-0023, ADR-0024, ADR-0036, ADR-0040, ADR-0041 ; décision 13 de la partie 5

## Contexte

Après le gel du 19 octobre, `staging` ne reçoit plus rien d'API-FOOTBALL : le calendrier 2026-27 y reste avec ses identifiants justes mais des dates figées, sans résultats. Le live (horizon H1) doit le compléter par football-data, seule source gratuite et légale de résultats et de prochains matchs pour le top 5 et les D2 (ADR-0011, règle 3), sans changer `load` ni le référentiel (décision 13).

**Conditions d'utilisation relues le 2026-10-04** (pages lues avec `curl` et le `User-Agent` du projet, une requête par seconde) :

| Page | Constat (citation) |
|---|---|
| `data.php` | « its use is intended for private individuals only, NOT commerical or data training products using automated bots/scrapers/AI » ; « All data provided by Football-Data are made available for the purposes of league match prediction only. » Inchangé depuis l'ADR-0023. |
| `matches.php` | fichier des prochains matchs « with the match dates, times and betting odds » ; cotes relevées le vendredi après-midi (week-end) et le mardi (milieu de semaine). |
| `robots.txt` | `User-agent: *` sans restriction ; robots d'IA bloqués (GPTBot, ClaudeBot, Claude-Web, Anthropic-AI, CCBot…). C'est pourquoi aucune page n'a été lue par un outil web d'IA : seulement par `curl` et le collecteur du projet. |

Le projet reste l'usage décrit : un particulier, la prédiction de matchs de championnat, sans usage commercial ni produit d'entraînement. Point d'interprétation déjà signalé par l'ADR-0023, toujours à relire par l'utilisateur.

**Format relevé** sur le vrai fichier des prochains matchs (une seule requête, le 2026-10-04, 13 669 octets, stocké selon l'ADR-0024) : BOM UTF-8, fins de ligne CRLF, 94 colonnes (`Div`, `Date`, `Time`, `HomeTeam`, `AwayTeam`, `Referee`, cotes 1N2, plus/moins 2,5 dont `Avg>2.5` et `B365>2.5`, handicap asiatique), `Date` en jj/mm/aaaa, `Time` en HH:MM, **aucune colonne de résultat** ; il couvre les jours qui viennent (ici du 2 au 5 octobre, déjà passés en partie) et toutes les divisions du site. Ses noms d'équipes sont ceux des CSV historiques (22 sur 22 dans le YAML pour la seule division suivie présente ce jour-là). **Heure** : heure de Londres (GMT l'hiver, BST l'été), constatée sur 1 749 matchs de 2024-25 sur 1 752 contre l'heure UTC de l'API ; le site ne l'écrit pas. Le site redirige désormais `www.football-data.co.uk` vers `football-data.co.uk`.

## Options envisagées

1. **Écrire le live dans `staging`** (nouveau chargement) : une seule table, mais `load` et le référentiel changent, une seconde voie d'écriture dans la base, et la reconstruction depuis le brut se complique.
2. **Superposer en mémoire** une copie de la table des matchs de la porte `features/sources.py`, au moment de prédire : `staging` intact, rien de nouveau dans la base, même fonction de variables.

## Décision

Option 2.

- **Collecte** (`collect/football_data/live.py`, nouveau fichier, le téléchargeur historique est inchangé) : `fixtures` (fichier des prochains matchs, `football_data/fixtures/fixtures__<horodatage>.csv`) et `season` (CSV de la saison courante, nouvelle version à côté) ; octet pour octet, une requête par seconde, `User-Agent` du projet, `--max-requests` obligatoire, verrou, journal, aucun écrasement ; un fichier de moins de 6 heures n'est pas redemandé ; `season` **refuse** les saisons à partir de 2025-26 tant que le test scellé n'est pas terminé.
- **Appariement** (`inference/live_sources.py`) : par (championnat, saison, équipe à domicile, équipe à l'extérieur), **sans la date**, sur les matchs de **saison régulière** du calendrier API (les barrages, dans la même compétition-saison, répètent des affiches : constaté en D2 italienne, anglaise et espagnole). Noms par `football_data_team_ids.yaml`. Un nom absent du YAML ou une affiche ambiguë n'est **jamais deviné** : ligne comptée, matchs candidats indisponibles avec la raison.
- **Superposition** : un match déjà joué dans `staging` garde les valeurs de l'API ; sinon, résultats (buts, tirs et tirs cadrés de football-data, pris tels quels, ADR-0041) et date réelle ; pour un match à venir, date et heure réelles (la version la plus récente du fichier des prochains matchs fait foi) et la probabilité implicite avant clôture comme référence de marché (ADR-0036), jamais comme variable.
- **Fraîcheur par championnat** (ADR-0011, règle 5) : complet jusqu'à la veille du premier match encore sans résultat (date réelle si connue, sinon date figée), ou de la première ligne de résultat inutilisable. Un match du jour J dont un match antérieur de son championnat manque est « périmé » : pas de prédiction. Règle prudente : un report sans nouvelle date bloque son championnat jusqu'à son résultat.
- **Version des données** : `load_run-<n>+fd-<empreinte des fichiers lus>` ; un nouveau fichier invalide le cache des lignes.

## Conséquences

- **Répétition sur la période de développement** (`python -m foot_predictor.inference check --only live`, gel simulé au 2024-02-15, « aujourd'hui » simulé 2024-03-09, CSV historiques coupés à ce jour) : 335 résultats rétablis sur 335, **0 score différent de l'API**, 0 ligne inutilisable ; lignes du 9 mars 2024 **identiques pour les buts et l'Elo** ; seules les variables de tirs (`xgp_*`) diffèrent, comme attendu ; 20 matchs du top 5 sur 20 disponibles.
- **Phase A** : aucune donnée réelle de 2025-26 ni 2026-27 lue. Les CSV 2026-27 téléchargés en partie 2 (2026-09-29) sont sur le disque et chargés dans `staging`, filtrés par la porte : ils ne sont ni lus ni résumés ici. Le branchement sur l'API et l'interface en mode live, et la commande `live`, viennent en phase B (sous-étape 5.14).
- Les coupes ne sont pas couvertes par football-data, mais aucune variable du modèle n'en dépend (Elo et glissants : championnats seulement, ADR-0031) ; la variable de repos (G3) n'est pas dans le modèle (ADR-0039).
- **Critères de révision** : plus d'un match du top 5 sur cinq indisponible sur les premières semaines de live (ADR-0011) ; un nom d'équipe nouveau (promu) absent du YAML ; un changement du format ou des conditions de football-data ; des reports qui bloquent durablement un championnat (règle de fraîcheur à affiner, par équipe plutôt que par championnat).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
