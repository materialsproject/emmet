import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder
from emmet.molecules.redox import RedoxBuilder

__author__ = "Sam Blau"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "sample_qchem_tasks.json")


class TestRedox(unittest.TestCase):
    def setUp(self):
        tasks = JSONStore(test_tasks)
        molecules = MemoryStore(name="molecules")
        redox = MemoryStore(name="redox")
        tasks.connect()
        molecules.connect()
        redox.connect()
        mbuilder = MoleculesBuilder(tasks, molecules)
        for group in list(mbuilder.get_items()):
            mbuilder.update_targets([mbuilder.process_item(group)])
        self.rbuilder = RedoxBuilder(molecules,redox)

    def test_get_and_process(self):
        grouped_mols = list(self.rbuilder.get_items())
        self.assertEqual(len(grouped_mols),5)
        for group in grouped_mols:
            mols = self.rbuilder.process_item(group)
        

if __name__ == "__main__":
    unittest.main()
