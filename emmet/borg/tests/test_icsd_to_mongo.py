import unittest
from monty.serialization import loadfn
from emmet.borg.icsd_to_mongo import IcsdDrone


class TestIcsdToMongo(unittest.TestCase):
    def test_icsd_drone(self):
        drone = IcsdDrone()
        obtained = drone.assimilate(
            'test_files/icsd/999999999')
        expected = loadfn('test_files/icsd/999999999_expected.json')

        keys = [
            "chem_name",
            "chemsys",
            "elements",
            "formula",
            "formula_anonymous",
            "formula_reduced",
            "formula_reduced_abc",
            "is_ordered",
            "is_valid",
            "nelements",
            "nsites",
            "pressure"]

        for key in keys:
            self.assertAlmostEqual(obtained['cifmetadata'][key], expected[key])

    def test_composition(self):
        drone = IcsdDrone()
        obtained = drone.assimilate(
            'test_files/icsd/5656565656')

        self.assertTrue(obtained['metadata']['consistent_composition'])
        self.assertTrue(
            len(obtained['metadata']['deuterium_indices']) > 0)