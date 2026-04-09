# Architecture logicielle

## Vue d'ensemble

L'application repose sur une architecture modulaire Python, organisée autour d'un noyau de calcul et d'une interface graphique unifiée.

## Modules principaux

### Point d'entrée

`Programme AP.py` :

- analyse les arguments de lancement ;
- distingue les usages graphiques et console ;
- délègue le calcul à l'orchestrateur ;
- lance l'interface unifiée lorsque le mode graphique est retenu.

### Interface graphique

`unified_gui.py` :

- construit une fenêtre principale unique ;
- gère la navigation entre `Accueil`, `Sélection` et `Résultats` ;
- mémorise l'état courant de sélection ;
- déclenche l'analyse puis affiche les sorties.

`ui_helpers.py` :

- regroupe les composants visuels réutilisables ;
- gère la mise en forme des résumés ;
- centralise certaines aides contextuelles ;
- conserve des utilitaires de style et de présentation.

### Orchestration métier

`analysis_runner.py` :

- construit la source altimétrique adaptée au mode de données ;
- appelle le constructeur de segments à partir du `GTFS` ;
- instancie les paramètres du bus ;
- exécute le calcul énergétique ;
- injecte la validation historique éventuelle.

### Couche données transport

`gtfs_services.py` :

- découvre les réseaux `GTFS` ;
- télécharge et met en cache les jeux distants si besoin ;
- lit `stops.txt`, `stop_times.txt`, `trips.txt`, `routes.txt`, `shapes.txt` ;
- reconstruit les segments entre arrêts ;
- gère les sélections de ligne, de trajet et de direction.

### Couche altimétrie

`altimetry_services.py` :

- charge les tuiles altimétriques locales ;
- échantillonne l'altitude sur la géométrie du trajet ;
- peut utiliser une source en ligne selon le mode retenu.

### Couche calcul

`energy_logic.py` :

- calcule vitesse, pente, accélération, virages et énergie ;
- prépare les segments enrichis ;
- calcule le bilan énergétique total ;
- produit les scénarios comparés.

### Structures de données

`app_models.py` :

- définit les paramètres du bus ;
- structure les points géographiques ;
- structure les jeux altimétriques.

### Validation

`validation_services.py` :

- découvre les références historiques `BD_Ligne*.xlsx` ;
- lit les profils de validation ;
- compare le trajet courant au profil historique.

## Chaîne de traitement

La chaîne de traitement logicielle peut être résumée ainsi :

```{admonition} Flux de traitement
:class: note
GTFS -> reconstruction des segments -> enrichissement géométrique et altimétrique -> calcul énergétique -> scénarios comparés -> validation historique -> restitution
```
