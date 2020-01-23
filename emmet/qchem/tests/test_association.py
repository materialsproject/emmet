import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.association import AssociationBuilder

__author__ = "Sam Blau"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "sample_assoc_tasks.json")
new_test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "new_assoc_tasks.json")


class TestAssociation(unittest.TestCase):
    def setUp(self):
        input_tasks = JSONStore(test_tasks)
        self.output_tasks = MemoryStore(name="output_tasks")
        input_tasks.connect()
        self.output_tasks.connect()
        self.abuilder = AssociationBuilder(input_tasks, self.output_tasks)

    def test_get_and_process(self):
        grouped_tasks = list(self.abuilder.get_items())
        output_tasks = []
        for group in grouped_tasks:
            tasks = self.abuilder.process_item(group)
            if len(tasks) == 3:
                self.assertEqual(tasks[0]["formula_alphabetical"],"C4 H6 O5")
            if len(tasks) == 5:
                self.assertEqual(tasks[0]["formula_alphabetical"],"C6 F2 H6 O5")
            output_tasks += tasks
        self.assertEqual(len(output_tasks),8)

    def test_update(self):
        for group in list(self.abuilder.get_items()):
            self.abuilder.update_targets([self.abuilder.process_item(group)])
        self.assertEqual(len(self.output_tasks.distinct("task_id")),8)

class WeirdAssociation(unittest.TestCase):
    def setUp(self):
        input_tasks = JSONStore(new_test_tasks)
        self.output_tasks = MemoryStore(name="output_tasks")
        input_tasks.connect()
        self.output_tasks.connect()
        self.abuilder = AssociationBuilder(input_tasks, self.output_tasks)

    def test_get_and_process(self):
        grouped_tasks = list(self.abuilder.get_items())
        output_tasks = []
        for group in grouped_tasks:
            tasks = self.abuilder.process_item(group)
            output_tasks += tasks
        self.assertEqual(len(output_tasks),16)

    def test_update(self):
        for group in list(self.abuilder.get_items()):
            self.abuilder.update_targets([self.abuilder.process_item(group)])
        self.assertEqual(len(self.output_tasks.distinct("task_id")),16)

if __name__ == "__main__":
    unittest.main()
