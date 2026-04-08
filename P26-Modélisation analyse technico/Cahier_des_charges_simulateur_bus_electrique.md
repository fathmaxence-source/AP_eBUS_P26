# Cahier des charges
## Simulateur énergétique de bus électriques à partir de données GTFS

### Version
- Version du document : 1.0
- Date : 8 avril 2026
- Référence projet : `P26-Modélisation analyse technico`

## 1. Introduction
Le présent cahier des charges définit, dans un langage scientifique et technique, les spécifications fonctionnelles et non fonctionnelles du simulateur énergétique de bus électriques actuellement implémenté dans le projet. La structure rédactionnelle retenue est inspirée du cahier des charges de référence fourni pour le projet LCA-PAC, et adaptée au périmètre propre du code de modélisation de transport collectif.

L’outil a pour finalité de reconstruire un service journalier de bus à partir d’un jeu de données GTFS, de calculer la puissance de traction et l’évolution de l’état de charge de la batterie, puis de produire des indicateurs exportables et des représentations graphiques permettant l’analyse comparative de plusieurs scénarios de recharge et de plusieurs modèles de bus électriques.

## 2. Objet du système
L’objet du système est de fournir un environnement de simulation numérique permettant :

1. de charger un réseau GTFS local ou distant ;
2. de sélectionner une ligne de transport et un ensemble représentatif de trajets GTFS ;
3. de reconstruire un cycle d’exploitation d’un bus unique sur une journée ;
4. de modéliser la consommation énergétique du véhicule ;
5. de modéliser l’évolution du SoC de la batterie ;
6. de modéliser la recharge nocturne au dépôt et, selon le scénario, la recharge en ligne ;
7. de comparer l’impact du choix du modèle de bus et du scénario de charge ;
8. d’exporter des résultats détaillés et synthétiques à des fins d’analyse scientifique et d’aide à la décision.

## 3. Périmètre
### 3.1 Périmètre fonctionnel actuel
Le périmètre opérationnel actuel comprend :

1. la simulation d’un seul bus à la fois ;
2. la simulation d’une seule ligne à la fois ;
3. l’exploitation de données GTFS obtenues via API ou via un dossier local ;
4. la comparaison de trois scénarios de recharge ;
5. la comparaison de trois modèles de bus électriques ;
6. la prise en compte d’un trajet dépôt-premier arrêt et dernier arrêt-dépôt selon une hypothèse simplifiée ;
7. la production de sorties tabulaires et graphiques.

### 3.2 Hors périmètre actuel
Les éléments suivants sont explicitement hors périmètre :

1. l’affectation simultanée d’une flotte multi-bus avec interactions de charge ;
2. l’optimisation d’horaires ou de planification de service ;
3. la prise en compte de perturbations d’exploitation en temps réel ;
4. la modélisation détaillée de la topographie réelle de ligne avec profil de pente local ;
5. la gestion thermique avancée de la batterie ;
6. la modélisation des échanges avec réseau, photovoltaïque et stockage stationnaire dans le flux principal actuel.

## 4. Finalités scientifiques et techniques
Le simulateur doit répondre aux finalités suivantes :

1. quantifier la consommation énergétique segment par segment entre arrêts successifs ;
2. quantifier l’évolution temporelle du SoC sur l’ensemble du service ;
3. évaluer l’effet du modèle de bus sur la consommation, le SoC minimal et la recharge de fin de service ;
4. évaluer l’effet du scénario de charge sur la disponibilité énergétique du véhicule ;
5. fournir des résultats transparents, traçables et exportables pour analyse ou vérification externe.

## 5. Chaîne de calcul
La chaîne de calcul du système est définie par les étapes suivantes :

1. découverte ou chargement du feed GTFS ;
2. sélection d’une ligne, d’un `route_id`, d’un `trip_id` ou d’une direction ;
3. reconstruction des segments inter-arrêts à partir des `stop_times` ;
4. génération d’un service journalier par répétition de cycles ;
5. insertion d’un trajet dépôt-premier arrêt et d’un trajet dernier arrêt-dépôt selon l’hypothèse de service ;
6. calcul de la puissance de traction et de la puissance auxiliaire ;
7. application éventuelle d’une puissance de recharge en ligne selon le scénario ;
8. intégration énergétique pour obtenir le SoC ;
9. calcul de la recharge nocturne au dépôt ;
10. production des profils temporels complets, des tableaux segmentaires et des graphiques.

## 6. Données d’entrée
### 6.1 Données GTFS
Le système doit exploiter au minimum les fichiers GTFS suivants :

1. `stops.txt`
2. `stop_times.txt`
3. `trips.txt`

Les fichiers optionnels suivants peuvent être exploités lorsque disponibles :

1. `routes.txt`
2. `shapes.txt`
3. `agency.txt`

### 6.2 Paramètres utilisateur
Les paramètres actuellement pilotables sont :

1. `scenario ∈ {1, 2, 3}`
2. `bus-model ∈ {heuliez_gx337_elec, mercedes_ecitaro, solaris_urbino_12_electric}`
3. `gtfs-path` pour l’exploitation d’un feed local
4. `network_name`
5. `line_selector`
6. `direction_id`
7. `cycle_count`
8. `service_date`

### 6.3 Hypothèses de dépôt
Le modèle actuel prend en compte, par défaut, les hypothèses suivantes :

1. trajet dépôt-premier arrêt : `4 km`
2. trajet dernier arrêt-dépôt : `4 km`
3. vitesse de trajet dépôt : `12 m/s`

## 7. Modèles physiques et hypothèses scientifiques
### 7.1 Reconstruction des segments GTFS
Pour deux arrêts successifs, le temps de parcours est calculé à partir de la différence entre l’heure d’arrivée de l’arrêt aval et l’heure de départ de l’arrêt amont.

La distance inter-arrêts est définie :

1. par `shape_dist_traveled` lorsque cette information existe dans le GTFS ;
2. par distance géodésique de Haversine en secours lorsque `shape_dist_traveled` est absent.

### 7.2 Puissance de traction
La puissance de traction est calculée à partir du modèle :

```text
P_trac = V × ( M g sin(alpha) + M g C_r cos(alpha) + 0.5 rho V^2 S C_d + M a )
```

La puissance consommée totale est :

```text
P = P_trac + P_aux
```

avec :

1. `V` : vitesse moyenne du segment ;
2. `M` : masse de référence du véhicule ;
3. `g` : accélération de la pesanteur ;
4. `alpha` : pente locale ;
5. `C_r` : coefficient de résistance au roulement ;
6. `rho` : densité de l’air ;
7. `S` : surface frontale ;
8. `C_d` : coefficient de traînée ;
9. `a` : accélération moyenne ;
10. `P_aux` : puissance auxiliaire.

### 7.3 État de charge
L’évolution de l’état de charge est calculée par intégration énergétique discrète :

```text
Delta E_decharge = P × Delta t
Delta E_charge = P_charge × Delta t
Delta SoC = (-Delta E_decharge + Delta E_charge) / E_bat
```

Le SoC est initialisé à `100 %` au départ du service.

### 7.4 Recharge au dépôt
La puissance de recharge au dépôt est calculée via la fonction `p_charge` à partir :

1. du SoC en fin de service ;
2. de la capacité batterie ;
3. de la durée disponible avant le départ suivant ;
4. de la puissance maximale de borne.

Le calcul actuel retient une borne plafond de `150 kW`.

### 7.5 Scénarios
Les scénarios actuellement définis sont :

1. scénario 1 : recharge au dépôt uniquement ;
2. scénario 2 : recharge au dépôt + recharge au terminus ;
3. scénario 3 : recharge au dépôt + recharge au terminus + recharge intermédiaire.

### 7.6 Alerte batterie
Le système doit signaler :

1. une erreur batterie si `SoC <= 0 %` pendant le service ;
2. une alerte batterie si `SoC <= 10 %` pendant le service.

Le message doit préciser l’instant et le segment au cours desquels le minimum de SoC est observé.

## 8. Modèles de bus à considérer
Le système doit proposer au minimum les trois modèles suivants :

1. `Heuliez GX 337 ELEC`
2. `Mercedes-Benz eCitaro`
3. `Solaris Urbino 12 electric`

Pour chacun, le système doit stocker et exploiter au minimum :

1. identifiant interne ;
2. nom commercial ;
3. constructeur ;
4. longueur ;
5. largeur ;
6. hauteur ;
7. masse de référence ;
8. capacité batterie ;
9. puissance de traction nominale ;
10. coefficients aérodynamiques et de roulement ;
11. puissance auxiliaire ;
12. sources techniques documentaires.

## 9. Architecture logicielle
### 9.1 Principe général
L’architecture actuelle doit être conservée autant que possible sous forme modulaire, avec séparation entre :

1. acquisition et préparation des données GTFS ;
2. paramétrage des bus ;
3. calcul de puissance ;
4. calcul de SoC ;
5. calcul de recharge ;
6. post-traitement et visualisation ;
7. orchestration du cas d’étude.

### 9.2 Modules principaux
| Module | Fonction principale |
|---|---|
| `main_code.py` | orchestration de la simulation, parsing CLI, export des résultats |
| `gtfs_data.py` | sélection du feed, reconstruction du service bus, hypothèse dépôt |
| `bus_models.py` | définition des modèles de bus et des constantes associées |
| `route_power.py` | calcul de la puissance de traction et de recharge en ligne |
| `route_soc.py` | calcul du SoC et alerte batterie |
| `p_charge.py` | calcul de la puissance de recharge au dépôt |
| `bus_analysis.py` | profils temporels, tableaux segmentaires, exports, graphiques |

## 10. Exigences fonctionnelles
### EF-01 Sélection du feed GTFS
Le système doit permettre le chargement d’un feed GTFS :

1. depuis l’API de `transport.data.gouv.fr` ;
2. depuis un répertoire local.

### EF-02 Sélection de ligne
Le système doit permettre la sélection d’une ligne via :

1. `line_selector`
2. `route_id`
3. `trip_id`
4. `direction_id`

### EF-03 Reconstruction d’un service journalier
Le système doit reconstruire un service journalier d’un bus unique par répétition d’un ou plusieurs trajets GTFS représentatifs.

### EF-04 Prise en compte du dépôt
Le système doit intégrer un segment dépôt-sortie et un segment dépôt-retour selon les hypothèses configurées.

### EF-05 Choix du modèle de bus
Le système doit permettre la sélection d’un modèle de bus via la ligne de commande.

### EF-06 Choix du scénario
Le système doit permettre la sélection du scénario de recharge via la ligne de commande.

### EF-07 Calcul de puissance
Le système doit calculer la puissance instantanée consommée sur chaque segment de trajet.

### EF-08 Calcul de SoC
Le système doit calculer le SoC pas à pas sur l’ensemble du service.

### EF-09 Recharge nocturne
Le système doit prolonger la journée de simulation jusqu’au départ suivant afin de modéliser la recharge nocturne au dépôt.

### EF-10 Export des résultats
Le système doit produire, pour chaque exécution :

1. un profil temps réel ;
2. un tableau segmentaire ;
3. un profil journalier complet incluant recharge ;
4. un tableau de référence des modèles de bus.

### EF-11 Visualisation
Le système doit générer au minimum :

1. un graphe temporel puissance-distance-SoC ;
2. un graphe segmentaire puissance-distance-SoC ;
3. un graphe couplé distance-SoC intégrant la recharge.

### EF-12 Signalement du risque énergétique
Le système doit signaler explicitement tout risque de vidage de batterie pendant la mission.

## 11. Exigences non fonctionnelles
### ENF-01 Traçabilité
Toute simulation doit être reproductible à partir :

1. du scénario ;
2. du modèle de bus ;
3. du feed GTFS utilisé ;
4. de la date de service ;
5. des fichiers CSV exportés.

### ENF-02 Transparence scientifique
Les hypothèses simplificatrices et les formules doivent être explicites dans le code et dans la documentation.

### ENF-03 Extensibilité
L’ajout d’un nouveau modèle de bus ne doit pas nécessiter la réécriture des fonctions de calcul de puissance ou de SoC.

### ENF-04 Lisibilité des résultats
Les sorties graphiques doivent permettre l’identification visuelle :

1. des segments de ligne ;
2. des segments dépôt ;
3. de la période de recharge nocturne ;
4. du SoC en fonction du temps réel.

### ENF-05 Robustesse de fonctionnement
Le système doit gérer :

1. l’absence de `shape_dist_traveled` ;
2. l’ambiguïté de nom de réseau GTFS ;
3. l’exploitation d’un cache GTFS local.

## 12. Critères de validation
Le système sera considéré comme conforme si les conditions suivantes sont satisfaites :

1. la ligne demandée est correctement identifiée ;
2. les distances cumulées des exports et des graphes sont cohérentes ;
3. le SoC décroît lors des segments consommateurs et augmente lors des périodes de charge ;
4. les segments dépôt sont présents dans les exports et visibles sur les graphes ;
5. les sorties sont bien séparées par scénario et par modèle ;
6. le changement de modèle modifie effectivement au moins la masse, la capacité batterie et les résultats de SoC ;
7. le changement de scénario modifie effectivement la stratégie de charge ;
8. un message d’alerte est affiché lorsque le SoC devient critique ou nul.

## 13. Sorties attendues
Pour chaque simulation, les fichiers suivants doivent être produits :

1. `bus_realtime_profile.csv`
2. `bus_segment_summary.csv`
3. `bus_full_day_profile.csv`
4. `bus_models_reference.csv`
5. `bus_realtime_dashboard.png`
6. `bus_segment_dashboard.png`
7. `bus_distance_soc_recharge.png`

L’arborescence de sortie doit être organisée au minimum comme suit :

```text
outputs/
  scenario_<n>/
    <bus_model_id>/
      ...
```

## 14. Contraintes de mise en œuvre
Le système doit être compatible avec l’environnement Python défini par le projet et les dépendances actuelles.

Les dépendances minimales identifiées à ce stade sont :

1. `numpy`
2. `pandas`
3. `matplotlib`
4. `scipy`
5. `openpyxl`

Le système doit pouvoir être exécuté en mode graphique ou en mode non interactif (`Agg`) pour génération automatisée des figures.

## 15. Limites scientifiques actuelles
Les limites scientifiques actuelles du modèle sont les suivantes :

1. accélération moyenne fixée à zéro ;
2. pente locale actuellement nulle dans le flux GTFS courant ;
3. puissance auxiliaire modélisée comme constante ;
4. dynamique électrochimique batterie non modélisée ;
5. rendement de chaîne de traction non détaillé ;
6. masse de référence fixée et non dépendante du taux de charge voyageurs ;
7. absence de prise en compte d’aléas trafic et météorologie dans le flux principal courant.

## 16. Évolutions recommandées
Les évolutions recommandées à court et moyen terme sont :

1. ajout d’un mode de comparaison automatique multi-modèles et multi-scénarios ;
2. ajout d’un tableau de synthèse global regroupant les principaux indicateurs ;
3. prise en compte d’un profil altimétrique réel ;
4. raffinement du modèle de masse avec taux de charge voyageurs variable ;
5. raffinement de la loi de recharge opportuniste ;
6. couplage futur avec les modules énergétiques stationnaires historiques du dépôt.

## 17. Références techniques
### 17.1 Références méthodologiques internes
1. code source du projet `P26-Modélisation analyse technico`
2. cahier des charges de référence `Cahier des Charges LCAPAC.docx.pdf`

### 17.2 Références constructeurs pour les modèles de bus
1. Heuliez GX 337 ELEC : [IVECO BUS](https://www.ivecogroup.com/media/brand_press_releases/2025/EMEA-%28English%29/Iveco-Bus/iveco_bus_signs_three_major_framework_agreements_with_le-de-france_mobilits_to_achieve_100_clean_buses_in_the_region_by_2030_20251030T085844T052_ckim1yvpckhnsc2gkbdewqa3), [fiche technique Heuliez](https://www.heuliezbus.com/fr/vue/produits/bus/GX-ELEC/FT_GX337_ELEC.pdf)
2. Mercedes-Benz eCitaro : [Daimler Buses](https://www.daimlertruck.com/en/newsroom/pressrelease/electric-buses-on-the-road-to-success-more-than-2500-mercedes-benz-ecitaro-buses-in-use-by-european-transport-companies-53114299), [fiche technique Daimler](https://www.daimlertruck.com/en/newsroom/pressrelease/vehicle-profile-the-mercedes-benz-ecitaro-exhibition-vehicle-technical-data-53100234)
3. Solaris Urbino 12 electric : [Solaris](https://www.solarisbus.com/en/press/mobility-move-2024-new-version-of-the-solaris-urbino-12-electric-bus-debuts-2121), [fiche technique Solaris](https://www.solarisbus.com/public/assets/Biuro_prasowe/2023_05_11_UITP_zapro/Technical_details_Solaris_Urbino_12_electric.pdf)

## 18. Conclusion
Le système actuel constitue un simulateur énergétique modulaire, traçable et scientifiquement exploitable pour l’étude d’un bus électrique unique sur une ligne GTFS donnée. Le présent cahier des charges formalise le comportement attendu du logiciel, son domaine de validité, ses hypothèses, ses exigences et ses critères de conformité. Il constitue la base documentaire de référence pour les développements ultérieurs, les campagnes d’essais numériques et les comparaisons inter-scénarios ou inter-véhicules.
