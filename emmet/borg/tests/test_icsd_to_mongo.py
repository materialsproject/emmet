import unittest
from monty.serialization import loadfn, dumpfn
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


        dumpfn(obtained, "tmp.json")