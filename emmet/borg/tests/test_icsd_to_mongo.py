import unittest
from monty.serialization import loadfn
from emmet.borg.icsd_to_mongo import icsdDrone


class TestIcsdToMongo(unittest.TestCase):
    def test_icsd_drone(self):
        drone = icsdDrone()
        obtained = drone.assimilate(
            'test_files/999999999', store_mongo=False)
        expected = loadfn('test_files/999999999_expected.json')

        keys = [
            "chem_name",
            "chemsys",
            "elements",
            "formula",
            "formula_anonymous",
            "formula_reduced",
            "formula_reduced_abc",
            "icsd_id",
            "is_ordered",
            "is_valid",
            "nelements",
            "nsites",
            "pressure"]

        for key in keys:
            self.assertAlmostEqual(obtained[key], expected[key])
