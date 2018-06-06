import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from maggma.runner import Runner
from emmet.materials.thermo import ThermoBuilder, chemsys_permutations

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "thermo_test.json")


class TestThermo(unittest.TestCase):
    def setUp(self):
        self.materials = JSONStore(test_mats,lu_type='isoformat')
        self.materials.connect()
        self.thermo = MemoryStore("thermo")
        self.thermo.connect()

    def test_get_entries(self):

        tbuilder = ThermoBuilder(self.materials, self.thermo)
        self.assertEqual(len(tbuilder.get_entries("Sr")), 7)
        self.assertEqual(len(tbuilder.get_entries("Hf")), 4)
        self.assertEqual(len(tbuilder.get_entries("O")), 6)
        self.assertEqual(len(tbuilder.get_entries("Hf-O-Sr")), 44)
        self.assertEqual(len(tbuilder.get_entries("Sr-Hf")), 11)

    def test_chemsys_permutations(self):
        self.assertEqual(len(chemsys_permutations("Sr")), 1)
        self.assertEqual(len(chemsys_permutations("Sr-Hf")), 3)
        self.assertEqual(len(chemsys_permutations("Sr-Hf-O")), 7)

    def test_process_items(self):
        tbuilder = ThermoBuilder(self.materials, self.thermo)

        # Ensure only one doc gets a 0 e_above_hull
        entries = tbuilder.get_entries("Sr")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 1)

        entries = tbuilder.get_entries("Hf")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 1)

        entries = tbuilder.get_entries("O")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 1)

        # Ensure 4 docs iwth 0 e_above hull for convex hull for Sr-O
        entries = tbuilder.get_entries("Sr-O")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 4)

        # Ensure 4 docs iwth 0 e_above hull for convex hull Hf-O
        entries = tbuilder.get_entries("Hf-O")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 3)

        # Ensure 4 docs iwth 0 e_above hull for convex hull
        entries = tbuilder.get_entries("Sr-Hf-O")
        t_docs = tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        self.assertEqual(len(e_above_hulls), 44)
        self.assertEqual(len([e for e in e_above_hulls if e == 0.0]), 7)

    def test_update_targets(self):
        items = [[{"task_id": 1}] * 3, [{"task_id": 2}] * 4, [{"task_id": 3}] * 4]
        tbuilder = ThermoBuilder(self.materials, self.thermo)
        tbuilder.update_targets(items)

        self.assertEqual(len(self.thermo.distinct("task_id")), 3)
        self.assertEqual(tbuilder.completed_tasks, {1, 2, 3})

    def test_get_items(self):
        tbuilder = ThermoBuilder(self.materials, self.thermo)
        self.assertEqual(len(list(tbuilder.get_items())),1)


if __name__ == "__main__":
    unittest.main()
