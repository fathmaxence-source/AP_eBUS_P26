from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from configuration_simulation import ConfigurationSimulation
from gtfs_data import GTFSBusConfig
from p_charge import calculer_puissance_charge_depot
from route_soc import calculer_soc_parcours
from service_flotte import (
    construire_lignes_resume_simulation_flotte,
    construire_resume_global_flotte,
    executer_simulation_flotte,
    exporter_resultats_flotte,
)


DOSSIER_GTFS_MINI = Path(__file__).parent / "fixtures" / "mini_gtfs"


class TestsSecuriteCalculs(unittest.TestCase):
    def test_puissance_charge_depot_cas_limites(self) -> None:
        self.assertEqual(
            calculer_puissance_charge_depot(
                soc_initial=1.0,
                capacite_batterie_kwh=350.0,
                duree_disponible_h=4.0,
                puissance_borne_max_kw=150.0,
            ),
            0.0,
        )
        self.assertEqual(
            calculer_puissance_charge_depot(
                soc_initial=0.4,
                capacite_batterie_kwh=350.0,
                duree_disponible_h=0.0,
                puissance_borne_max_kw=150.0,
            ),
            0.0,
        )
        self.assertEqual(
            calculer_puissance_charge_depot(
                soc_initial=0.0,
                capacite_batterie_kwh=350.0,
                duree_disponible_h=0.5,
                puissance_borne_max_kw=150.0,
            ),
            150.0,
        )
        with self.assertRaises(ValueError):
            calculer_puissance_charge_depot(
                soc_initial=0.5,
                capacite_batterie_kwh=0.0,
                duree_disponible_h=1.0,
                puissance_borne_max_kw=150.0,
            )

    def test_soc_recharge_plafonnee_a_100(self) -> None:
        parcours = pd.DataFrame(
            {
                "Power": [0.0, 100_000.0],
                "PowerC": [500_000.0, 0.0],
                "deltaT": [3600.0, 3600.0],
            }
        )
        resultat, capacite_kwh = calculer_soc_parcours(parcours)

        self.assertGreater(capacite_kwh, 0.0)
        self.assertEqual(float(resultat["SoC"].iloc[0]), 100.0)
        self.assertLess(float(resultat["SoC"].iloc[1]), 100.0)


class TestsSimulationFlotte(unittest.TestCase):
    def _configuration_mini_gtfs(self) -> ConfigurationSimulation:
        gtfs = GTFSBusConfig(
            data_mode="local",
            gtfs_path=str(DOSSIER_GTFS_MINI),
            network_name="",
            line_selector="L1",
            service_date="2026-04-29",
            include_depot_deadhead=False,
            default_stop_duration_s=0.0,
        )
        return ConfigurationSimulation(gtfs=gtfs, id_modele_bus="heuliez_gx337_elec")

    def test_simulation_flotte_mini_gtfs_et_exports(self) -> None:
        resultat = executer_simulation_flotte(
            configuration_simulation=self._configuration_mini_gtfs(),
            temps_battement_s=300.0,
        )
        resume_global = construire_resume_global_flotte(resultat)

        self.assertEqual(resultat.resultat_affectation.nombre_bus_necessaires, 2)
        self.assertEqual(int(resultat.resume_energie_bus["NbCourses"].sum()), 3)
        self.assertEqual(resume_global["StatutGlobal"], "OK")
        self.assertIn("StatutViabilite", resultat.resume_energie_bus.columns)
        self.assertIn("MargeMinSoc_pct", resultat.resume_energie_bus.columns)

        lignes_resume = construire_lignes_resume_simulation_flotte(resultat)
        self.assertTrue(any("Statut global" in ligne for ligne in lignes_resume))

        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemins = exporter_resultats_flotte(
                resultat,
                dossier_sortie=Path(dossier_temporaire),
            )
            for chemin in chemins.values():
                self.assertTrue(chemin.exists(), chemin)


if __name__ == "__main__":
    unittest.main()
