# ADR-0053 — Planification du live : trois passages hebdomadaires, autorisation durable bornée

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0011 (règle 6, journal prospectif), ADR-0018 (verrou et tâches planifiées de la collecte), ADR-0042 (football-data en live), ADR-0046 (fraîcheur par équipe), ADR-0047 (D8 : « une planification de collecte demandera sa propre ADR »), ADR-0052 (journal prospectif) ; `CLAUDE.md` (collecte : verrou)

## Contexte

- **Le live est manuel.** Chaque passage demande à l'utilisateur son accord, puis trois commandes : télécharger football-data (`fixtures`, `season`), tracer les prédictions disponibles avant le coup d'envoi (`inference live --days 7 --save`), relever le journal (`inference prospective`). Les prédictions ne s'écrivent qu'**avant** le coup d'envoi (ADR-0011) : un passage manqué, c'est une journée perdue.
- **Le critère d'E.2 manque d'une journée** (7 sur 8) et ne se comble qu'avec un passage bien placé : les résultats de football-data doivent être publiés avant que les matchs du week-end suivant soient prédictibles (règle de fraîcheur, ADR-0046). Le 1er novembre 2026, tous les matchs des 6 et 7 novembre sont « indisponibles » pour cette raison.
- **Les tâches planifiées de la collecte API ont été supprimées au gel** (`CLAUDE.md`). Leur modèle existe encore : `scripts/taches_planifiees/creer_taches.py` décrit chaque tâche en XML (`StartWhenAvailable`, `WakeToRun`, session de l'utilisateur sans mot de passe stocké). L'ADR-0047 (D8) demande une ADR pour toute nouvelle planification de collecte.
- **L'utilisateur donne son accord durable** (2026-11-01) à une planification de ces trois commandes, avec ces choix : Planificateur de tâches Windows, collecte + tracé + relevé, mardi et vendredi plus un tracé le samedi matin.
- **Ce qu'une tâche planifiée ne peut pas faire** : demander un accord à chaque passage. L'accord doit donc être écrit une fois, avec ses plafonds.

## Options envisagées

1. **Rien de planifié, un script à lancer à la main.** Aucune autorisation durable ; mais on rate les passages que l'on oublie.
2. **Cron de Claude Code.** Ne tourne que tant que la session est ouverte ; rien de durable.
3. **Planificateur de tâches Windows, trois passages par semaine, plafonnés.** *Retenue (choix de l'utilisateur, 2026-11-01).*

Pour le rythme, deux alternatives ont été écartées : un passage quotidien (jusqu'à 77 requêtes par semaine vers un site gratuit qui ne publie que deux fois par semaine) et un cycle borné à ce week-end seulement.

## Décision

### Les passages

| Tâche | Jour, heure locale (Paris) | Étapes |
|---|---|---|
| `FootPredictor_live_mardi` | mardi 18:00 | collecte, tracé, relevé |
| `FootPredictor_live_vendredi` | vendredi 17:00 | collecte, tracé |
| `FootPredictor_live_samedi` | samedi 08:00 | tracé |

- **Le mardi** reprend les résultats du week-end et le fichier des prochains matchs ; **le vendredi** prend le fichier publié l'après-midi, avant les matchs du soir (coup d'envoi vers 20:30) ; **le samedi matin** retrace sans réseau les matchs encore à venir, avec les données du vendredi. Le tracé est idempotent : repasser n'écrit rien de plus.
- **Étapes** :
  - *collecte* : `collect.football_data.live fixtures --max-requests 1`, puis `season --season <saison courante> --max-requests 10` ;
  - *tracé* : `inference live --days 7 --save` ;
  - *relevé* : `inference prospective`.
- **Ordre et échecs** : une collecte qui échoue n'empêche pas le tracé (il lit les fichiers déjà là) ; un tracé qui échoue empêche le relevé.

### L'autorisation durable et ses plafonds

Elle vaut pour ces trois passages, et pour rien d'autre :

- **football-data seulement.** Aucune requête API-FOOTBALL, aucun `load`, aucune écriture dans le brut d'API-FOOTBALL (`data/raw/` d'API, tag `data-freeze-2026-10`), aucune lecture de valeur scellée hors de l'inférence ouverte (ADR-0045, ADR-0052).
- **Plafond de requêtes** : 11 par passage de collecte (1 + 10), donc 22 par semaine au plus ; le collecteur ne redemande pas un fichier de moins de 6 heures (`--min-age-hours`), à raison d'une requête par seconde.
- **Seulement les commandes ci-dessus**, composées en dur dans le code (liste fermée) ; le lanceur refuse toute autre commande, tout module `api_football` ou `ingestion`, et toute commande de collecte sans `--max-requests`.
- **Écrit** : les fichiers football-data du dossier brut externe du worktree (ADR-0024), `ops.prediction` (prédictions disponibles écrites avant le coup d'envoi), les rapports `reports/inference/` et le journal `data/planification/passages.log` (ignoré par Git).
- **Interrupteur** : le fichier `data/planification/STOP` suspend les passages sans supprimer les tâches ; `planification uninstall` les supprime. Aucune tâche ne se recrée seule.
- **Durée** : l'autorisation vaut jusqu'à la fin de la saison 2026-27 (30 juin 2027), puis tombe d'elle-même (le lanceur refuse après cette date) ; la renouveler demande une nouvelle ADR.

### Mise en œuvre

- **Module `foot_predictor.planification`** : `run <passage>`, `install`, `uninstall`, `status`. `install` crée ou remplace les trois tâches, décrites en XML comme celles de la partie 1 : `StartWhenAvailable` (un passage manqué, portable éteint, démarre à la remise sous tension ; **le lanceur l'ignore si l'on n'est plus le jour prévu**, ce que le journal note, sauf `--force`), `WakeToRun`, une `EndBoundary` au 30 juin 2027 (fin de l'autorisation), tâche exécutée sous la session de l'utilisateur (`InteractiveToken`, sans mot de passe stocké), tournant aussi sur batterie.
- **Conditions réelles de fonctionnement**, à connaître : le portable doit être allumé (ou réveillable), la session Windows ouverte (verrouillée suffit), Docker lancé pour que `ops.prediction` soit joignable. Sinon, le passage échoue en le disant dans le journal ; le suivant rattrape ce qui peut l'être.
- **Quel dépôt ?** Les tâches s'exécutent dans le **worktree** `C:/fp-travail` tel qu'il est extrait, car c'est lui qui porte le dossier des bruts externes du live, les modèles de rejeu et les jeux de données. Il faut donc qu'il reste sur un commit propre de `main` quand rien n'est en développement ; le journal note le commit de chaque passage.
- **Ce que l'utilisateur voit** : rien, sauf le journal et les rapports. Un passage est silencieux ; une erreur n'envoie pas de notification (hors périmètre).

## Conséquences

- **Fichiers** : `src/foot_predictor/planification.py`, `tests/test_planification.py`, README de l'étape 11, `CLAUDE.md` (la règle « une nouvelle tâche planifiée passe par une ADR » cite maintenant celle-ci), `ETAT_PROJET.md`. Aucune dépendance nouvelle.
- **On s'interdit** : d'étendre les passages à une autre commande sans une nouvelle ADR ; de planifier toute collecte API-FOOTBALL ; de réentraîner, recalibrer ou changer un modèle à partir d'un relevé planifié (règle de lecture de l'ADR-0052 inchangée) ; de tirer une conclusion de performance du journal avant 8 journées.
- **Critères de révision** :
  - une requête hors de football-data, ou une commande de collecte sans plafond, dans le journal ;
  - une prédiction écrite après le coup d'envoi ;
  - plus de 22 requêtes de collecte en une semaine ;
  - un passage qui modifie un fichier suivi par Git.

  Le constater dans une nouvelle ADR et suspendre les tâches (`STOP`).
- **Coût du risque** : un site gratuit sollicité 22 fois par semaine (au plus 11 par passage) ; les conditions d'utilisation de football-data (particulier, prédiction de championnat, ADR-0042) sont inchangées.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
