import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder
from emmet.qchem.association import AssociationBuilder

__author__ = "Sam Blau, Shyam Dwaraknath"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "new_sample_qchem_tasks.json")
assoc_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "LiEC_tasks.json")


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
                self.assertEqual(len(mols),4)
            elif group[0]["formula_pretty"] == "H5C2Cl" or group[0]["formula_pretty"] == "BH4":
                self.assertEqual(len(mols),4)
            else:
                self.assertEqual(len(mols),6)

    def test_update(self):
        for group in list(self.mbuilder.get_items()):
            self.mbuilder.update_targets([self.mbuilder.process_item(group)])
        self.assertEqual(len(self.molecules.distinct("task_id")),24)


class TestAssocMolecules(unittest.TestCase):
    def setUp(self):
        input_tasks = JSONStore(assoc_tasks)
        tasks = MemoryStore(name="tasks")
        input_tasks.connect()
        tasks.connect()
        abuilder = AssociationBuilder(input_tasks, tasks)
        for group in list(abuilder.get_items()):
            abuilder.update_targets([abuilder.process_item(group)])
        self.assertEqual(len(tasks.distinct("task_id")),58)

        self.molecules = MemoryStore(name="molecules")
        self.molecules.connect()
        self.mbuilder = MoleculesBuilder(tasks, self.molecules)

    def test_get_and_process(self):
        grouped_tasks = list(self.mbuilder.get_items())
        self.assertEqual(len(grouped_tasks),1)
        self.assertEqual(len(grouped_tasks[0]),58)
        mols = self.mbuilder.process_item(grouped_tasks[0])
        self.assertEqual(mols[0]["environment"],"smd_18.5,1.415,0.00,0.735,20.2,0.00,0.00")
        self.assertEqual(len(mols),49)
        group_lengths = {}
        for mol in mols:
            mol_len = len(mol["task_ids"])
            if mol_len in group_lengths:
                group_lengths[mol_len] += 1
            else:
                group_lengths[mol_len] = 1
        self.assertEqual(group_lengths[1],44)
        self.assertEqual(group_lengths[2],4)
        self.assertEqual(group_lengths[3],1)

    def test_update(self):
        for group in list(self.mbuilder.get_items()):
            self.mbuilder.update_targets([self.mbuilder.process_item(group)])
        self.assertEqual(len(self.molecules.distinct("task_id")),49)

if __name__ == "__main__":
    unittest.main()
