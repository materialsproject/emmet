import unittest
from itertools import chain
from maggma.stores import MongoStore
from maggma.runner import Runner
from emmet.vasp.builders.tests.test_builders import BuilderTest
from emmet.vasp.builders.materials import MaterialsBuilder
from emmet.vasp.builders.thermo import ThermoBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestMaterials(BuilderTest):

    def setUp(self):
        self.materials = MongoStore("emmet_test", "materials")
        self.materials.connect()

        self.materials.collection.drop()
        self.mbuilder = MaterialsBuilder(
            self.tasks, self.materials, mat_prefix="", chunk_size=1)

    def test_get_items(self):
        to_process = list(self.mbuilder.get_items())
        to_process_forms = {tasks[0]["formula_pretty"] for tasks in to_process}

        self.assertEqual(len(to_process), 12)
        self.assertEqual(len(to_process_forms), 12)
        self.assertEqual(len(list(chain.from_iterable(to_process))), 197)
        self.assertTrue("Sr" in to_process_forms)
        self.assertTrue("Hf" in to_process_forms)
        self.assertTrue("O2" in to_process_forms)
        self.assertFalse("H" in to_process_forms)

    def test_process_item(self):
        tasks = list(self.tasks.query(criteria={"chemsys": "Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 7)

        tasks = list(self.tasks.query(criteria={"chemsys": "Hf"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 4)

        tasks = list(self.tasks.query(criteria={"chemsys": "O"}))
        mats = self.mbuilder.process_item(tasks)

        self.assertEqual(len(mats), 6)

        tasks = list(self.tasks.query(criteria={"chemsys": "O-Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 5)

        tasks = list(self.tasks.query(criteria={"chemsys": "Hf-O-Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 13)

    def test_update_targets(self):
        tasks = list(self.tasks.query(criteria={"chemsys": "Sr"}))
        mats = self.mbuilder.process_item(tasks)
        self.assertEqual(len(mats), 7)

        self.mbuilder.update_targets([mats])
        self.assertEqual(len(self.materials.distinct("task_id")), 7)
        self.assertEqual(len(list(self.materials.query())), 7)

    def tearDown(self):
        self.materials.collection.drop()


if __name__ == "__main__":
    unittest.main()
