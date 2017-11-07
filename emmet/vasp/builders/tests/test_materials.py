import unittest
import os
import glob
import logging
from bson.json_util import loads
from itertools import chain
from monty.io import zopen
from atomate.vasp.database import VaspCalcDb

from maggma.stores import MongoStore
from emmet.vasp.builders.materials import MaterialsBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_dir = os.path.join(module_dir, "..", "..", "..",
                        "..", "test_files", "vasp", "builders")


class TestMaterials(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.tasks = MongoStore("emmet_test", "tasks", lu_field="last_updated")
        cls.tasks.connect()
        cleardb(cls.tasks.collection.database)

        vaspdb = VaspCalcDb(database="emmet_test")
        tasks_dir = os.path.join(test_dir, "tasks")
        for f in glob.glob("{}/*.json.gz".format(tasks_dir)):
            with zopen(f) as f:
                data = f.read()
                task = loads(data)
                vaspdb.insert_task(task, parse_dos=True, parse_bs=True)

        cls.materials = MongoStore("emmet_test", "materials")

        cls.tasks.connect()
        cls.materials.connect()

        cls.mbuilder = MaterialsBuilder(
            cls.tasks, cls.materials, mat_prefix="", chunk_size=1)

    def test_get_items(self):
        self.materials.collection.drop()

        to_process = list(self.mbuilder.get_items())
        to_process_forms = {tasks[0]["formula_pretty"] for tasks in to_process}

        self.assertEqual(len(to_process), 12)
        self.assertEqual(len(to_process_forms), 12)
        self.assertEqual(len(list(chain.from_iterable(to_process))), 182)
        self.assertTrue("Sr" in to_process_forms)
        self.assertTrue("Hf" in to_process_forms)
        self.assertTrue("O2" in to_process_forms)
        self.assertFalse("H" in to_process_forms)

    def test_process_item(self):

        tasks = list(self.tasks.query(criteria={"chemsys": "Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 6)

        tasks = list(self.tasks.query(criteria={"chemsys": "Hf"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 4)

        tasks = list(self.tasks.query(criteria={"chemsys": "O"}))
        mats = self.mbuilder.process_item(tasks)

        self.assertEqual(len(mats), 5)

        tasks = list(self.tasks.query(criteria={"chemsys": "O-Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 5)

        tasks = list(self.tasks.query(criteria={"chemsys": "Hf-O-Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 13)

    def test_update_targets(self):

        tasks = list(self.tasks.query(criteria={"chemsys": "Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 6)

        self.mbuilder.update_targets([mats])
        self.assertEqual(len(self.materials.distinct("material_id")), 6)
        self.assertEqual(len(list(self.materials.query())), 6)

    @classmethod
    def tearDownClass(cls):
        cleardb(cls.tasks.collection.database)


def cleardb(db):
    for coll in db.collection_names():
        if coll != "system.indexes":
            db[coll].drop()

if __name__ == "__main__":
    unittest.main()
