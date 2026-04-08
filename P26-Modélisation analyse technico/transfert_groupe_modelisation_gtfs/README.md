# Outil GTFS autonome pour le groupe modélisation

Ce dossier contient une version autonome centrée sur le **GTFS**.  
Il est prévu pour être transféré au groupe modélisation sans modifier l'outil principal.

## Contenu

- `gtfs_api_modelisation.py`
  Script principal autonome.
- `gtfs_core.py`
  Fonctions GTFS réutilisables.
- `network_io.py`
  Accès réseau minimal pour les requêtes GTFS en ligne.
- `Lancer GTFS API Modelisation.bat`
  Lanceur Windows.

## Fonctionnalités

Le script permet de :

- lister les réseaux GTFS locaux ;
- interroger les réseaux GTFS en ligne via l'API de `transport.data.gouv.fr` ;
- lister les lignes d'un réseau ;
- sélectionner une ligne, un `route_id`, un `trip_id` ou un `direction_id` ;
- reconstruire les segments d'un trajet ;
- afficher un aperçu synthétique du ou des trajets retenus ;
- exporter les segments en `CSV` ;
- exporter la structure complète en `JSON`.

## Dépendances

Le script utilise uniquement la bibliothèque standard Python.

## Exemples

### Lister les réseaux GTFS locaux

```powershell
python gtfs_api_modelisation.py --list-networks
```

### Lister les lignes d'un réseau local

```powershell
python gtfs_api_modelisation.py --network compiegne --list-lines
```

### Prévisualiser une ligne

```powershell
python gtfs_api_modelisation.py --network compiegne --line 1 --show-stops
```

### Exporter les segments en CSV et JSON

```powershell
python gtfs_api_modelisation.py --network compiegne --line 1 --export-csv segments_ligne1.csv --export-json ligne1.json
```

### Utiliser l'API GTFS en ligne

```powershell
python gtfs_api_modelisation.py --data-mode online --list-networks
python gtfs_api_modelisation.py --data-mode online --network bordeaux --list-lines
```

## Recherche locale par défaut

Si le dossier reste dans le projet actuel, le script cherche automatiquement les GTFS dans :

`..\donnees\gtfs`

Sinon, il utilise le dossier courant ou le dossier fourni via `--search-root`.

## Remarque

Ce programme n'utilise pas l'altimétrie, le calcul énergétique, la batterie embarquée ou la couche technico-économique.  
Il sert uniquement de **brique GTFS transférable** pour le groupe modélisation.
