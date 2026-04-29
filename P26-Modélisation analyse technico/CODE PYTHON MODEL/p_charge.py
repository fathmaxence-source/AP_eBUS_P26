import math


def calculer_puissance_charge_depot(
    soc_initial: float,
    capacite_batterie_kwh: float,
    duree_disponible_h: float,
    puissance_borne_max_kw: float,
) -> float:
    """
    Calcule la puissance de charge necessaire au depot.

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

    if capacite_batterie_kwh <= 0:
        raise ValueError("La capacite de batterie doit etre strictement positive.")
    if puissance_borne_max_kw < 0:
        raise ValueError("La puissance maximale de borne ne peut pas etre negative.")
    if duree_disponible_h <= 0 or puissance_borne_max_kw == 0:
        return 0.0

    soc_borne = min(max(float(soc_initial), 0.0), 1.0)
    energie_a_recharger_kwh = (1.0 - soc_borne) * capacite_batterie_kwh
    if energie_a_recharger_kwh <= 0:
        return 0.0

    puissance_requise_kw = energie_a_recharger_kwh / duree_disponible_h
    puissance_avec_marge_kw = math.ceil(puissance_requise_kw + 1.0) * 1.01
    return min(puissance_avec_marge_kw, float(puissance_borne_max_kw))


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
