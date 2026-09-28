# Objectifs du projet — foot-predictor

Ce document présente le cadrage initial du projet : ce qu'on cherche à construire (objectif fonctionnel) et, surtout, pourquoi on le construit (objectifs réels et pédagogiques).

---

## 1. Objectif général

L'objectif final est de **concevoir, développer et évaluer un modèle statistique** (éventuellement hybride statistique / IA) capable de **prédire le résultat d'un match de football avant qu'il ne soit joué**, à partir de données historiques, contextuelles et dynamiques.

Au-delà de cet objectif fonctionnel, le projet est avant tout un **projet pédagogique et exploratoire de data science appliquée**. Sa finalité principale est le développement de compétences avancées couvrant **l'ensemble du cycle de vie d'un projet data**.

### Produit visé

Une application qui liste les prochains matchs, avec un bouton **« Prédire »** à côté de chacun :

- le bouton est **grisé** tant que les données nécessaires ne sont pas disponibles (composition officielle non publiée) ;
- il se **dégrise** une fois toutes les données disponibles, puis affiche un tableau de variables de prédiction.

*(Décisions détaillées dans `RECAP_PROJET.md`.)*

---

## 2. Objectifs réels et pédagogiques

### 2.1 Approfondir la démarche complète d'un projet de data science

Reproduire une démarche **professionnelle et réaliste**, de la réflexion initiale jusqu'à une potentielle mise en production, en passant par :

- la conception du modèle de données ;
- l'ingénierie des variables ;
- la modélisation statistique ;
- l'évaluation des performances ;
- l'amélioration itérative du modèle.

L'idée est de **ne pas se limiter à la modélisation pure** et de traiter le projet comme un **système global**.

### 2.2 Explorer toutes les étapes clés d'un projet de data science

#### a) Définition du problème et cadrage métier

- Définir précisément ce que signifie « prédire le résultat d'un match » : 1N2, score exact, over/under, probabilités implicites, etc.
- Identifier les contraintes réalistes : données disponibles avant le match, biais, temporalité.
- Formaliser les métriques de succès : log-loss, Brier score, accuracy, ROI simulé, etc.

#### b) Conception du modèle de données

- Identifier les sources de données pertinentes :
  - résultats historiques ;
  - statistiques d'équipes et de joueurs ;
  - forme récente ;
  - facteur domicile / extérieur ;
  - calendrier, fatigue, blessures (si disponible) ;
  - cotes de bookmakers (éventuellement comme proxy).
- Structurer un schéma de données cohérent et évolutif.
- Gérer la temporalité : **uniquement des données valables avant le match**.

#### c) Collecte, ingestion et nettoyage des données

- Automatiser la collecte (API, scraping, datasets ouverts).
- Nettoyer et valider les données (valeurs manquantes, incohérences).
- Versionner les datasets.

#### d) Feature engineering

- Créer des variables dérivées pertinentes : rolling averages, formes récentes, indicateurs de force.
- Normaliser et encoder.
- Analyser l'importance des features.

#### e) Modélisation statistique

> ⚠️ **Section à compléter.** Le document source s'arrêtait ici, en plein milieu de cette partie.
>
> Piste actuellement envisagée d'après les récaps : modèle de type **Poisson / Dixon-Coles** pour prédire le score exact (à confirmer).

#### f) Évaluation, amélioration itérative et mise en production

> ⚠️ **Section à compléter.** Ces étapes sont annoncées dans l'objectif général (évaluation des performances, amélioration itérative, mise en production) mais n'étaient pas détaillées dans le document source.

---

## 3. Fil rouge : les principes qui guident toutes les décisions

- **Pédagogie d'abord** : on privilégie une démarche réaliste et complète plutôt qu'un raccourci qui ferait gagner du temps mais qui masquerait une étape du cycle de vie.
- **Pas de fuite de données (data leakage)** : chaque variable doit refléter uniquement l'information disponible **strictement avant** le match.
- **Légalité des sources** : uniquement des sources dont les conditions d'utilisation autorisent la collecte (voir l'abandon de Transfermarkt dans `RECAP_PROJET.md`).
- **Budget gratuit en priorité** : sources gratuites, scraping léger accepté uniquement s'il est légal.
