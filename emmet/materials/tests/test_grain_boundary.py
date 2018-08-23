from maggma.stores import MemoryStore, JSONStore
from unittest import TestCase
import os

from emmet.materials.grain_boundary import GBBuilder

__author__ = "Xiang-Guo Li"
__email__ = "xil110@ucsd.edu"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "grain_boundary", "material.json")
test_bulk = os.path.join(module_dir, "..", "..", "..", "test_files", "grain_boundary", "bulk.json")


class TestGBBuilder(TestCase):
    @classmethod
    def setUpClass(self):
        self.materials = JSONStore(test_mats, lu_type='isoformat')
        self.materials.connect()
        self.bulks = JSONStore(test_bulk, lu_type='isoformat')
        self.bulks.connect()
        self.gb = MemoryStore("GB")
        self.gb.connect()
        self.gbbuilder = GBBuilder(self.materials, self.gb, self.bulks)

    def test_get_items(self):
        self.assertEqual(len(list(self.gbbuilder.get_items())), 1)

    def test_process_items(self):
        for item in self.gbbuilder.get_items():
            processed = self.gbbuilder.process_item(item)
            self.assertEqual(len(processed), 1)
            self.assertTrue('grain_boundaries' in processed[0].keys())
            self.assertAlmostEqual(processed[0]['grain_boundaries'][0]['GB_energy in J/m2'], 0.16304030889820062)

    def test_update_targets(self):
        processed = [self.gbbuilder.process_item(item)
                     for item in self.gbbuilder.get_items()]
        self.gbbuilder.update_targets(processed)
        self.assertEqual(len(self.gb.distinct("task_id")), 1)
