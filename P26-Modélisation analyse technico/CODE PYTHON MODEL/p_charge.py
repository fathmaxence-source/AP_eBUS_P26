import math


def calculer_puissance_charge_depot(
    soc_initial: float,
    capacite_batterie_kwh: float,
    duree_disponible_h: float,
    puissance_borne_max_kw: float,
) -> float:
    """
    Calcule la puissance de charge nécessaire au dépôt.

    Parameters
    ----------
    soc_initial            : SoC a l'arrivee au depot (fraction entre 0 et 1)
    capacite_batterie_kwh  : capacite de la batterie (kWh)
    duree_disponible_h     : duree disponible pour la charge (heures)
    puissance_borne_max_kw : puissance maximale disponible (kW)

    Returns
    -------
    Pcharge : puissance de charge (kW)
    """
    Pcharge = min(
        (1 - soc_initial) * capacite_batterie_kwh / duree_disponible_h,
        puissance_borne_max_kw,
    )
    Pcharge = math.ceil(Pcharge + 1)
    Pcharge = 1.01 * Pcharge
    return Pcharge


def p_charge(SoCi: float, Eb: float, TimeDifference: float, Pterminal: float) -> float:
    """
    Alias de compatibilite vers la fonction en francais.
    """

    return calculer_puissance_charge_depot(
        soc_initial=SoCi,
        capacite_batterie_kwh=Eb,
        duree_disponible_h=TimeDifference,
        puissance_borne_max_kw=Pterminal,
    )
