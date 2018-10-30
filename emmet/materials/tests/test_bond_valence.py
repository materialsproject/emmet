import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from maggma.runner import Runner
from emmet.materials.bond_valence import BondValenceBuilder

__author__ = "Matthew Horton"
__email__ = "mkhorton@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "thermo_test.json")


class TestBondValence(unittest.TestCase):
    def setUp(self):

        self.materials = JSONStore(test_mats)
        self.bond_valence = MemoryStore("bond_valence")

    def test_build(self):

        builder = BondValenceBuilder(self.materials, self.bond_valence)
        runner = Runner([builder])
        runner.run()

        doc = list(self.bond_valence.query(criteria={'task_id': 'mp-779001'}))[0]
        self.assertSetEqual(set(doc["bond_valence"]['possible_species']), {'Hf4+', 'Sr2+', 'O2-'})


if __name__ == "__main__":
    unittest.main()
