# Organisation du dossier

Ce dossier a été réorganisé pour séparer plus clairement :

- le code applicatif principal ;
- les données d'entrée ;
- la documentation technique ;
- les exports produits par l'outil ;
- l'environnement historique conservé pour compatibilité.

## Accès rapides

- Lancer l'outil : [AP2026.bat](C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\AP2026.bat)
- Construire la documentation : [Construire Jupyter Book.bat](C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\Construire Jupyter Book.bat)
- Ouvrir la documentation : [Ouvrir Documentation Jupyter.bat](C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\Ouvrir Documentation Jupyter.bat)

## Arborescence utile

- `Programme AP.py`
  Point d'entrée principal de l'outil.

- `unified_gui.py`, `ui_helpers.py`, `analysis_runner.py`, `energy_logic.py`, `gtfs_services.py`, `altimetry_services.py`, `reporting_services.py`
  Modules applicatifs principaux.

- `assets/Images`
  Logos et visuels utilisés par l'interface.

- `donnees/gtfs`
  Jeux de données GTFS locaux.

- `donnees/altimetrie`
  Jeux de données altimétriques locaux.

- `documentation/jupyter_book_outil_bus`
  Documentation scientifique et technique Jupyter Book.

- `documentation/.jb_node`
  Runtime Node.js local utilisé par Jupyter Book.

- `documentation/diagrammes`
  Diagrammes et schémas du projet.

- `documentation/archives_tests_jb`
  Archives techniques liées aux essais de mise en place de Jupyter Book.

- `documentation/outils_techniques`
  Outils annexes archivés, non utilisés dans le flux principal courant.

- `exports`
  Rapports et fichiers générés par l'outil.

- `Codes AP2025`
  Projet précédent conservé en référence, ainsi que le Python embarqué utilisé par les lanceurs.

## Remarques pratiques

- Les données sont désormais rangées sous `donnees`, mais l'application les retrouve automatiquement depuis le dossier du projet.
- Les images de l'accueil sont désormais rangées sous `assets/Images`.
- Les scripts de documentation pointent maintenant vers `documentation/...` au lieu de l'ancienne racine.
- Les lanceurs `.bat` à la racine sont conservés pour un usage simple.
