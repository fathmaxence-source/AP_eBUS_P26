# Introduction

Ce `Jupyter Book` constitue la base documentaire de l'outil d'aide à la décision pour l'analyse énergétique de lignes de bus électriques.

L'objectif de cette documentation est de fournir :

- une lecture scientifique du modèle de calcul ;
- une description claire des modules logiciels ;
- une traçabilité des données d'entrée et des hypothèses ;
- un support réutilisable dans un cahier des charges, un mémoire ou une note méthodologique.

## Périmètre actuel

La documentation couvre la version actuelle de l'outil, centrée sur :

- la lecture de données `GTFS` locales ou en ligne ;
- l'enrichissement altimétrique local ou distant ;
- la reconstruction géométrique du trajet ;
- le calcul énergétique segmentaire ;
- la comparaison de scénarios physiques simples ;
- la validation historique par fichiers `BD_Ligne*.xlsx`.

Les volets `photovoltaïque`, `CAPEX`, `OPEX` et dimensionnement économique détaillé ne sont pas inclus dans cette version documentaire.

## Organisation de la documentation

Cette documentation est structurée selon six axes :

1. guide de prise en main ;
2. architecture logicielle ;
3. données d'entrée et chaîne de traitement ;
4. modèle énergétique ;
5. équations de référence ;
6. validation, limites et points de vigilance.

## Références code

Les modules actuellement décrits dans ce livre sont principalement :

- `Programme AP.py` : point d'entrée ;
- `unified_gui.py` : interface graphique unifiée ;
- `analysis_runner.py` : orchestration de l'analyse ;
- `gtfs_services.py` : lecture et reconstruction GTFS ;
- `altimetry_services.py` : enrichissement altimétrique ;
- `energy_logic.py` : calcul énergétique ;
- `validation_services.py` : comparaison avec les références historiques ;
- `app_models.py` : structures de données.
