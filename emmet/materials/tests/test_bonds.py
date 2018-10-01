import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from maggma.runner import Runner
from emmet.materials.bonds import BondBuilder
from pymatgen.analysis.graphs import StructureGraph

__author__ = "Matthew Horton"
__email__ = "mkhorton@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "thermo_test.json")


class TestBondBuilder(unittest.TestCase):

    def setUp(self):

        self.materials = JSONStore(test_mats, lu_type='isoformat')
        self.bonding = MemoryStore("bonding")

    def test_build(self):

        builder = BondBuilder(self.materials, self.bonding)
        runner = Runner([builder])
        runner.run()

        doc = list(self.bonding.query(criteria={'task_id': 'mp-779001'}))[0]
        sg = StructureGraph.from_dict(doc['graph'])
        self.assertIsInstance(sg, StructureGraph)
        self.assertIn('Hf-O(6)', doc['summary']['coordination_envs'])


if __name__ == "__main__":
    unittest.main()
