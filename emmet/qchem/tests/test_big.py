import unittest
import os
import copy
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder
from emmet.qchem.association import AssociationBuilder

__author__ = "Sam Blau, Shyam Dwaraknath"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
# test_tasks = "/Users/samuelblau/Desktop/smd_production_entries.json"
assoc_tasks = "/Users/samuelblau/Desktop/LiEC_tasks.json"


# class TestMolecules(unittest.TestCase):
#     def setUp(self):
#         tasks = JSONStore(test_tasks)
#         self.molecules = MemoryStore(name="molecules")
#         tasks.connect()
#         self.molecules.connect()
#         self.mbuilder = MoleculesBuilder(tasks, self.molecules)

#     def test_get_and_process(self):
#         grouped_tasks = list(self.mbuilder.get_items())
#         # self.assertEqual(len(grouped_tasks),5)
#         print(len(grouped_tasks))
#         # for group in grouped_tasks:
#         #     mols = self.mbuilder.process_item(group)
#         #     if group[0]["formula_pretty"] == "H2C":
#         #         self.assertEqual(len(mols),1)
#         #     elif group[0]["formula_pretty"] == "H5C2Cl" or group[0]["formula_pretty"] == "BH4":
#         #         self.assertEqual(len(mols),2)
#         #     else:
#         #         self.assertEqual(len(mols),3)

#     def test_update(self):
#         for group in list(self.mbuilder.get_items()):
#             self.mbuilder.update_targets([self.mbuilder.process_item(group)])
#         # self.assertEqual(len(self.molecules.distinct("task_id")),11)
#         print(len(self.molecules.distinct("task_id")))

class TestAssocMolecules(unittest.TestCase):
    def setUp(self):
        input_tasks = JSONStore(assoc_tasks)
        tasks = MemoryStore(name="tasks")
        input_tasks.connect()
        tasks.connect()
        abuilder = AssociationBuilder(input_tasks, tasks)
        for group in list(abuilder.get_items()):
            abuilder.update_targets([abuilder.process_item(group)])
        # self.assertEqual(len(tasks.distinct("task_id")),8)
        print(len(tasks.distinct("task_id")),"associated tasks")

        self.molecules = MemoryStore(name="molecules")
        self.molecules.connect()
        self.mbuilder = MoleculesBuilder(tasks, self.molecules)

    def test_get_and_process(self):
        print("grouping")
        grouped_tasks = list(self.mbuilder.get_items())
        for group in grouped_tasks:
            # print(len(group))
            self.mbuilder.process_item(group)

    # def test_update(self):
    #     for group in list(self.mbuilder.get_items()):
    #         self.mbuilder.update_targets([self.mbuilder.process_item(group)])
    #     self.assertEqual(len(self.molecules.distinct("task_id")),6)

if __name__ == "__main__":
    unittest.main()
