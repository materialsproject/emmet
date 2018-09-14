import unittest
import os

from emmet.vasp.mpworks import MPWorksCompatibilityBuilder, \
        convert_mpworks_to_atomate, update_mpworks_schema
from maggma.stores import JSONStore, MemoryStore

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "mpworks_tasks.json")


class MPWorksCompatibilityBuilderTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.test_tasks = JSONStore([test_tasks])
        self.elasticity = MemoryStore("atomate_tasks")
        self.test_tasks.connect()
        self.elasticity.connect()

    def test_builder(self):
        mpw_builder = MPWorksCompatibilityBuilder(self.test_tasks, self.elasticity, incremental=False)
        items = mpw_builder.get_items()
        processed = [mpw_builder.process_item(item) for item in items]
        mpw_builder.update_targets(processed)

    def test_convert_mpworks_to_atomate(self):
        doc = self.test_tasks.collection.find_one({"task_type": {"$regex": "deformed"}})
        new_doc = convert_mpworks_to_atomate(doc)
        self.assertTrue('hubbards' in new_doc['input'])
        doc = self.test_tasks.collection.find_one({"task_type": {"$regex": "(2x)"}})
        new_doc = convert_mpworks_to_atomate(doc)
        self.assertTrue('hubbards' in new_doc['input'])

    def test_update_mpworks_schema(self):
        doc = self.test_tasks.query(criteria={"task_id": "mp-612"})[0]
        doc = update_mpworks_schema(doc)
        atomate_doc = convert_mpworks_to_atomate(doc)


if __name__ == "__main__":
    unittest.main()
