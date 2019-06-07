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
        self.molecules = MemoryStore(name="molecules")
        tasks.connect()
        self.molecules.connect()
        self.mbuilder = MoleculesBuilder(tasks, self.molecules)

    def test_get_and_process(self):
        grouped_tasks = list(self.mbuilder.get_items())
        self.assertEqual(len(grouped_tasks),5)
        for group in grouped_tasks:
            mols = self.mbuilder.process_item(group)
            if group[0]["formula_pretty"] == "H2C":
                self.assertEqual(len(mols),1)
            elif group[0]["formula_pretty"] == "H5C2Cl" or group[0]["formula_pretty"] == "BH4":
                self.assertEqual(len(mols),2)
            else:
                self.assertEqual(len(mols),3)

    def test_update(self):
        for group in list(self.mbuilder.get_items()):
            self.mbuilder.update_targets([self.mbuilder.process_item(group)])
        self.assertEqual(len(self.molecules.distinct("task_id")),11)

if __name__ == "__main__":
    unittest.main()
