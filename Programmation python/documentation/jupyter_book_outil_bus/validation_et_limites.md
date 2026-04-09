# Validation et limites

## Validation historique

Le module `validation_services.py` permet de comparer le profil courant avec une référence historique de type `BD_Ligne*.xlsx`.

Les critères actuellement comparés incluent :

- la distance totale ;
- le nombre de points ;
- le nombre d'arrêts ;
- le pas moyen ;
- la pente absolue moyenne ;
- l'écart géographique au départ et à l'arrivée.

## Limites identifiées

### Données GTFS peu détaillées

Lorsque le trajet comporte peu d'arrêts, la reconstruction de certaines grandeurs devient moins robuste, notamment :

- l'accélération moyenne ;
- la variabilité réelle de vitesse ;
- la dynamique fine du véhicule.

### Altimétrie incomplète

Sans données altimétriques locales fiables :

- la pente est simplifiée ;
- la composante gravitaire est sous-estimée ou neutralisée ;
- la précision du bilan énergétique diminue.

### Modèle de virage simplifié

La composante virage :

- améliore la représentation des lignes urbaines ;
- mais ne remplace pas une modélisation véhicule complète fondée sur le rayon de courbure, l'adhérence et la stratégie de conduite.

## Recommandations d'usage

Le modèle est particulièrement pertinent pour :

- comparer des lignes ou des variantes de lignes ;
- produire des ordres de grandeur énergétiques ;
- préparer une étude de dimensionnement ;
- alimenter un dossier technique ou un cahier des charges.

Il doit être utilisé avec prudence pour :

- des calculs de consommation très fins à l'échelle opérationnelle ;
- l'estimation exacte d'une récupération d'énergie réelle ;
- une simulation temps réel de la traction.

## Prochaines extensions prévues

Les extensions identifiées mais non encore intégrées dans ce livre sont :

- volet photovoltaïque ;
- volet `CAPEX` ;
- volet `OPEX` ;
- scénarios techno-économiques détaillés ;
- export documentaire enrichi.
