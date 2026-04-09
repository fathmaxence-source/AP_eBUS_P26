# Jupyter Book de l'outil bus électrique

Ce dossier contient la documentation structurée `Jupyter Book` du projet.

## Emplacement

Le livre est stocké ici :

`C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\documentation\jupyter_book_outil_bus`

Il reste donc bien dans le dossier `Programmation python`, mais dans un sous-dossier dédié pour séparer clairement :

- le code applicatif ;
- la documentation scientifique ;
- les fichiers de construction du livre.

## Fichiers principaux

- `myst.yml` : configuration active du livre pour `Jupyter Book` 2 ;
- `introduction.md` : page d'accueil du livre ;
- `guide_utilisation.md`
- `architecture_logicielle.md`
- `donnees_et_flux.md`
- `modele_energetique.md`
- `equations_reference.md`
- `validation_et_limites.md`

Les anciens fichiers de configuration du format classique sont conservés à titre de référence historique :

- `legacy_jb1_config.yml`
- `legacy_jb1_toc.yml`

Ils ne constituent plus la configuration active.

## Construction du livre

Un lanceur `.bat` est fourni à la racine du projet :

`Construire Jupyter Book.bat`

Ce script utilise :

- le Python embarqué du projet ;
- le `Node.js` local préparé pour `Jupyter Book` ;
- le script [build_jupyter_book.py](C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\documentation\build_jupyter_book.py).

Il permet de construire le livre sans dépendre du `PATH` global de la machine.

## Commande Python équivalente

La construction peut aussi être lancée directement avec :

```powershell
& "C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\Codes AP2025\Outil\Outil\WPy64-31180\python-3.11.8.amd64\python.exe" "C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\documentation\build_jupyter_book.py" build --html
```

## Sortie générée

Le site HTML généré est écrit dans :

`C:\Users\Lorenzo\Desktop\AP Bus élec\Programmation python\documentation\jupyter_book_outil_bus\_build\html`
