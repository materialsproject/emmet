import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder

__author__ = "Sam Blau, Shyam Dwaraknath"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "sample_qchem_tasks.json")


class TestMolecules(unittest.TestCase):
    def setUp(self):
        tasks = JSONStore(test_tasks)
        molecules = MemoryStore(name="molecules")
        tasks.connect()
        molecules.connect()
        self.mbuilder = MoleculesBuilder(tasks, molecules)

    def test_get_and_process(self):
        grouped_tasks = list(self.mbuilder.get_items())
        self.assertEqual(len(grouped_tasks),5)
        for group in grouped_tasks:
            mols = self.mbuilder.process_item(group)
            self.assertEqual(len(mols),3)


if __name__ == "__main__":
    unittest.main()
