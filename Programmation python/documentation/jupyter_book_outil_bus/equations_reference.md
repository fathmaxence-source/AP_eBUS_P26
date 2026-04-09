# Équations de référence

## Grandeurs élémentaires

La vitesse moyenne segmentaire est définie par :

$$
v = \frac{\Delta d}{\Delta t}
$$

avec :

- $v$ : vitesse moyenne du segment ;
- $\Delta d$ : distance du segment ;
- $\Delta t$ : durée du segment.

L'angle de pente est estimé par :

$$
\alpha = \arcsin\left(\frac{\Delta h}{\Delta d}\right)
$$

où $\Delta h$ désigne la différence d'altitude entre la fin et le début du segment.

L'accélération moyenne est écrite :

$$
a = \frac{v_{i+1} - v_i}{\Delta t}
$$

## Puissance de mouvement

La puissance de mouvement est modélisée sous la forme :

$$
P_{\mathrm{mouvement}} =
v \times
\left[
m g \sin(\alpha)
+
m g C_r \cos(\alpha)
+
\frac{1}{2}\rho v^2 A C_x
+
m a
\right]
$$

avec :

- $m$ : masse du véhicule ;
- $g$ : gravité ;
- $C_r$ : coefficient de roulement ;
- $\rho$ : densité de l'air ;
- $A$ : surface frontale ;
- $C_x$ : coefficient de traînée ;
- $a$ : accélération moyenne.

## Puissance totale

La puissance totale du segment est définie par :

$$
P_{\mathrm{total}} = P_{\mathrm{mouvement}} + P_{\mathrm{aux}} + P_{\mathrm{virages}}
$$

où :

- $P_{\mathrm{aux}}$ représente les auxiliaires ;
- $P_{\mathrm{virages}}$ représente la pénalité énergétique associée aux ralentissements en virage.

## Énergie segmentaire

L'énergie du segment est obtenue par intégration temporelle simplifiée :

$$
E = P_{\mathrm{total}} \times \Delta t
$$

La conversion en kilowattheures est réalisée selon :

$$
E_{\mathrm{kWh}} = \frac{E_{\mathrm{J}}}{3\,600\,000}
$$

## Consommation spécifique

La consommation spécifique du trajet est donnée par :

$$
C_{\mathrm{spec}} = \frac{E_{\mathrm{totale}}}{D_{\mathrm{totale}}}
$$

où :

- $E_{\mathrm{totale}}$ est exprimée en `kWh` ;
- $D_{\mathrm{totale}}$ est exprimée en `km`.

## Point de prudence méthodologique

Ces équations constituent un modèle énergétique d'ingénierie, non un modèle dynamique complet du véhicule.

En particulier :

- le freinage régénératif n'est pas modélisé comme une chaîne de traction détaillée ;
- la pénalité de virage reste une approximation géométrique ;
- la qualité du résultat dépend directement de la richesse du `GTFS` et de l'altimétrie disponible.
