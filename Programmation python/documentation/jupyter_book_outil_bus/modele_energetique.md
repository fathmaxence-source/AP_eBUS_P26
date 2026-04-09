# Modèle énergétique

## Hypothèse générale

Le modèle énergétique estime, pour chaque segment, la puissance totale nécessaire au déplacement du véhicule, puis en déduit l'énergie consommée sur la durée du segment.

## Composantes physiques

Le calcul de puissance inclut les contributions suivantes :

- composante gravitaire liée à la pente ;
- résistance au roulement ;
- traînée aérodynamique ;
- composante inertielle liée à l'accélération ;
- puissance auxiliaire ;
- pénalité énergétique liée aux virages.

## Calcul segmentaire

Pour un segment donné, l'algorithme procède ainsi :

1. calcul de la vitesse moyenne ;
2. estimation de la pente moyenne ;
3. estimation de l'accélération moyenne ;
4. estimation des virages et du ralentissement associé ;
5. calcul de la puissance totale ;
6. intégration sur la durée du segment.

## Traitement des virages

Le modèle ne simule pas explicitement le rayon de courbure réel du véhicule. Il applique une approximation géométrique :

- détection des changements de cap à partir des points GPS ;
- évaluation d'un angle de virage ;
- réduction locale de la vitesse ;
- calcul d'une pénalité énergétique spécifique.

Cette composante permet de mieux représenter les parcours urbains sinueux qu'un modèle strictement rectiligne.

## Traitement de l'accélération

L'accélération peut provenir de deux sources :

- `geo_profile` : lorsque la reconstruction géométrique fournit des échantillons de vitesse réellement exploitables ;
- `inter_segment` : lorsque l'on déduit l'évolution de vitesse d'un segment à l'autre.

Le modèle actuel évite désormais d'utiliser une accélération géométrique artificielle lorsque les données sont trop pauvres, en particulier sur les trajets comportant très peu d'arrêts.

## Indicateurs produits

Le bilan final comprend :

- l'énergie totale ;
- la distance totale ;
- la consommation spécifique ;
- le nombre de virages détectés ;
- le nombre de virages marqués ;
- le surcoût énergétique lié aux virages.

## Scénarios comparés

Trois scénarios physiques sont actuellement calculés :

- `Complet`
- `Sans relief`
- `Sans virages`

Ils permettent d'isoler l'impact relatif :

- du relief ;
- de la pénalité de virage ;
- de la combinaison des deux.
