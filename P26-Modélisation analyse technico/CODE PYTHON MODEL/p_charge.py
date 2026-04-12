import math


def p_charge(SoCi: float, Eb: float, TimeDifference: float, Pterminal: float) -> float:
    """
    Calcule la puissance de charge nécessaire au dépôt.

    Parameters
    ----------
    SoCi           : SoC à l'arrivée au dépôt (fraction entre 0 et 1)
    Eb             : capacité de la batterie (kWh)
    TimeDifference : durée disponible pour la charge (heures)
    Pterminal      : puissance maximale disponible (kW)

    Returns
    -------
    Pcharge : puissance de charge (kW)
    """
    Pcharge = min((1 - SoCi) * Eb / TimeDifference, Pterminal)
    Pcharge = math.ceil(Pcharge + 1)
    Pcharge = 1.01 * Pcharge
    return Pcharge
