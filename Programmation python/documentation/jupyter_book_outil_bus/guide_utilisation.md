# Guide d'utilisation

## Finalité

L'outil permet d'estimer la consommation énergétique d'un trajet de bus à partir d'un réseau `GTFS`, d'une géométrie de ligne, d'un relief éventuel et d'un modèle physique paramétrable.

## Modes d'entrée

Deux modes de données sont disponibles :

- `local` : lecture des dossiers `GTFS` présents dans le répertoire de travail et des tuiles altimétriques locales ;
- `online` : récupération des jeux `GTFS` via une source distante et recours à un service d'altimétrie en ligne.

## Parcours utilisateur

L'interface actuelle repose sur une fenêtre principale unique comportant trois vues internes :

1. `Accueil`
2. `Sélection`
3. `Résultats`

Le flux utilisateur standard est le suivant :

1. choisir le mode de données ;
2. sélectionner le réseau `GTFS` ;
3. sélectionner la ligne ;
4. préciser éventuellement une direction ;
5. définir le nombre maximal de segments ;
6. activer ou non l'altimétrie ;
7. choisir les paramètres du bus ;
8. lancer l'analyse ;
9. consulter le bilan, les segments et les scénarios comparés.

## Paramètres du bus

L'utilisateur peut :

- conserver les valeurs par défaut ;
- ou définir un jeu personnalisé de paramètres physiques.

Les paramètres disponibles sont :

- masse du bus ;
- gravité ;
- densité de l'air ;
- coefficient de roulement ;
- surface frontale ;
- coefficient de traînée ;
- puissance auxiliaire.

## Résultats fournis

L'outil retourne notamment :

- la distance totale ;
- l'énergie totale ;
- la consommation spécifique ;
- le détail segment par segment ;
- des indicateurs sur les virages ;
- une comparaison de scénarios ;
- une validation historique éventuelle.
