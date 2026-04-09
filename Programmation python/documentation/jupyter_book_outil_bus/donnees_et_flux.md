# Données et flux de traitement

## Données d'entrée principales

### Données GTFS

Les fichiers de référence sont :

- `stops.txt`
- `stop_times.txt`
- `trips.txt`
- `routes.txt`
- `shapes.txt`

Ils permettent respectivement de décrire :

- les arrêts ;
- les horaires ordonnés ;
- les trajets ;
- les lignes ;
- la géométrie théorique des parcours.

### Données altimétriques

Deux sources sont possibles :

- tuiles altimétriques locales ;
- service distant selon le mode `online`.

Ces données enrichissent la géométrie de ligne par une altitude locale point par point ou au moins aux extrémités du segment.

### Données historiques

Les fichiers `BD_Ligne*.xlsx` servent de références de validation. Ils fournissent typiquement :

- latitude ;
- longitude ;
- pente ;
- temps ;
- distance cumulée ;
- distance élémentaire.

## Reconstruction des segments

À partir d'un trajet `GTFS`, l'application construit une suite de segments entre arrêts consécutifs.

Chaque segment contient notamment :

- un nom ;
- une distance ;
- un temps de parcours ;
- une altitude de départ et d'arrivée ;
- une liste de `geo_points`.

## Construction des `geo_points`

Un segment peut comporter :

- le point de départ avec temps connu ;
- des points intermédiaires issus de `shapes.txt` ;
- le point d'arrivée avec temps connu.

Cette structure sert ensuite à :

- recalculer la distance réelle du segment ;
- calculer une pente moyenne pondérée ;
- détecter les changements de cap ;
- évaluer les ralentissements en virage ;
- estimer l'accélération lorsque l'information est suffisamment fiable.

## Point de vigilance sur les trajectoires peu segmentées

Lorsque le `GTFS` ne comporte que très peu d'arrêts sur une ligne, un trajet peut se résumer à un très petit nombre de segments.

Dans ce cas :

- la vitesse moyenne reste calculable ;
- la distance reste exploitable ;
- mais l'accélération moyenne reconstruite devient moins fiable.

Le modèle actuel applique donc une logique prudente :

- si les échantillons de vitesse sont insuffisants, l'accélération géométrique détaillée n'est pas utilisée ;
- le calcul retombe alors sur une estimation plus robuste de type `inter_segment`.
