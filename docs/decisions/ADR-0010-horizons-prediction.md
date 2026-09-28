# ADR-0010 — Deux horizons de prédiction : avant composition (MVP), avec composition (version intermédiaire)

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, E.1, E.2, F.1 (principe 3), F.5, H.7, I.1, I.3, décision M9 ; remplace la règle de `docs/RECAP_PROJET.md` §2 (bouton grisé tant que la composition officielle n'est pas publiée)

## Contexte

La règle écrite jusqu'ici, dans `RECAP_PROJET.md` §2 et non formalisée en ADR, était la suivante :

- le bouton « Prédire » est grisé tant que la composition officielle n'est pas publiée, soit environ une heure avant le coup d'envoi ;
- il n'y a pas de composition probable ;
- la disponibilité se réduit à un booléen.

Deux faits rendent cette règle intenable :

- **Après le 2026-10-22** (ADR-0005), l'offre gratuite d'API-FOOTBALL ne couvre plus la saison en cours. Les compositions des matchs à venir ne seront plus accessibles : avec la règle actuelle, aucun match réel ne pourrait être prédit.
- **La collecte permet d'évaluer l'apport des compositions en rejeu.** Les compositions historiques existent depuis 2010 (P1 et P2), les statistiques joueurs depuis 2015 (constats P1 et P2).

L'évaluation « avec composition » en rejeu repose sur une hypothèse : **le onze enregistré dans le détail du match est celui annoncé à T-60**. L'exception connue est le joueur remplacé pendant l'échauffement. Cette hypothèse ne peut être vérifiée qu'en enregistrant les compositions annoncées avant le coup d'envoi, donc seulement tant que l'abonnement est actif.

## Options envisagées

1. **Après composition seulement** (règle actuelle) : application inutilisable en live après le 22 octobre, sauf réabonnement.
2. **Deux horizons** : H1 « avant composition » pour le MVP, H2 « avec composition » en version intermédiaire, évalué en rejeu ; l'écart H1 contre H2 mesure l'apport de la composition.
3. **« Onze probable »** estimé à partir des matchs récents : source d'erreur supplémentaire, difficile à évaluer.

## Décision

Option 2.

| Horizon | Moment | Données permises | Version |
|---|---|---|---|
| **H1 — avant composition** | Jusqu'au coup d'envoi | Matchs **terminés avant le jour du match** ; calendrier connu à l'avance | MVP |
| **H2 — avec composition** | T-60 min | H1 + composition officielle du match et entraîneur inscrit sur la feuille de match | Version intermédiaire |

- **Déclaration de l'horizon.** Chaque variable déclare son horizon dans le registre des variables, et chaque modèle le sien dans sa carte d'identité. Un modèle H1 ne peut utiliser aucune variable H2.
- **Disponibilité.** Le booléen « composition publiée » est remplacé par une disponibilité **par variable et par horizon**, avec une raison et la date de la donnée source (rapport F.5).
- **Live après l'abonnement.** H2 est affiché « indisponible : compositions non fournies après la fin de l'abonnement », sauf réabonnement (décision M28, reportée).
- **« Onze probable »** : écarté pour le MVP et la version intermédiaire ; amélioration possible plus tard (rapport H.9).
- **Journal T-60 (palier P4) : conservé comme option facultative avant le gel du 19 octobre.**
  - Contenu : enregistrer les compositions annoncées avant le coup d'envoi pour quelques journées du top 5.
  - Usage unique : le comparer au détail des mêmes matchs collecté après coup, pour vérifier l'hypothèse du onze identique.
  - Jamais utilisé pour évaluer un modèle : l'échantillon est trop petit.
  - Il passe **après** P3, les `refresh` et les actions de l'ADR-0008.

## Conséquences

- **MVP.** Les variables des groupes G0 à G3 (rapport I.3) sont compatibles avec H1. Qualité du XI, stabilité et entraîneur (G4 à G6) sont réservés à H2. La disponibilité de G3 en live dépend de la décision M10.
- **Registres.** Le registre des variables (jalon J4) a une colonne « horizon ». La carte d'identité du modèle et la table `ops.prediction` ont un champ « horizon ».
- **API.** Les routes `availability` et `predictions` prennent l'horizon en paramètre (rapport F.6).
- **Journal T-60, s'il est fait.**
  - Un court module de collecte, aucun appel réseau dans les tests.
  - Une commande lancée à la main les jours de match, sur la réserve de quota. Il demande un accord explicite avant le premier appel réel (`CLAUDE.md`).
  - Un bilan chiffré : nombre de matchs, part des onze identiques.
- **Critère de révision.** Si le journal T-60 montre plus de 2 % de titulaires différents entre l'annonce et le détail, l'évaluation H2 en rejeu devra le signaler comme biais et, au besoin, traiter ces cas (seuil indicatif).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
