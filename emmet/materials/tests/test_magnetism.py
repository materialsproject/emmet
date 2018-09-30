import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from maggma.runner import Runner
from emmet.materials.magnetism import MagneticBuilder

__author__ = "Matthew Horton"
__email__ = "mkhorton@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "magnetism_mats_sample.json")


class TestMagneticBuilder(unittest.TestCase):

    def setUp(self):

        self.materials = JSONStore(test_mats, lu_type='isoformat')
        self.magnetism = MemoryStore("magnetism")

    def test_build(self):

        builder = MagneticBuilder(self.materials, self.magnetism)
        runner = Runner([builder])
        runner.run()

        doc = list(self.magnetism.query(criteria={'task_id': 'mp-1034331'}))[0]

        self.assertEqual(doc['magnetism']['ordering'], 'FM')
        self.assertAlmostEqual(doc['magnetism']['total_magnetization_normalized_formula_units'], 4.8031771)


if __name__ == "__main__":
    unittest.main()
