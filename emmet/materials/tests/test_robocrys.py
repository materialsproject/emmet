import unittest
import os

from monty.serialization import loadfn

from emmet.materials.robocrys import RobocrysBuilder
from maggma.runner import Runner
from maggma.stores import MemoryStore

__author__ = "Alex Ganose"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files",
                         "simple_structs.json")


class TestRobocrysBuilder(unittest.TestCase):

    def setUp(self):
        """Set up materials and robocrys stores."""
        struct_docs = loadfn(test_mats, cls=None)

        self.materials = MemoryStore("materials")
        self.materials.connect()
        self.materials.update(struct_docs)
        self.robocrys = MemoryStore("robocrys")

    def test_build(self):
        """Test building the robocrys database."""
        builder = RobocrysBuilder(self.materials, self.robocrys)
        runner = Runner([builder])
        runner.run()

        doc = list(self.robocrys.query(criteria={'task_id': 'mp-66'}))[0]

        self.assertEqual(doc['condensed_structure']['formula'], 'C')
        self.assertEqual(doc['condensed_structure']['spg_symbol'], 'Fd-3m')
        self.assertEqual(doc['condensed_structure']['mineral']['type'],
                         'diamond')
        self.assertEqual(doc['condensed_structure']['dimensionality'], '3')

        self.assertTrue("C is diamond structured" in doc['description'])
        self.assertTrue("bond lengths are 1.55" in doc['description'])


if __name__ == "__main__":
    unittest.main()


