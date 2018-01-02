import unittest
from itertools import chain
from pydash.objects import get
from maggma.stores import MongoStore
from maggma.runner import Runner
from emmet.vasp.builders.task_tagger import task_type
from emmet.vasp.builders.tests.test_builders import BuilderTest
from emmet.vasp.builders.ml_structures import MLStructuresBuilder


__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestMaterials(BuilderTest):

    def setUp(self):
        self.ml_strucs = MongoStore("emmet_test", "ml_strucs",key="entry_id")
        self.ml_strucs.connect()

        self.ml_strucs.collection.drop()
        self.mlbuilder = MLStructuresBuilder(self.tasks, self.ml_strucs, task_types = ("Structure Optimization","Static"))


    def test_get_items(self):
        to_process = list(self.mlbuilder.get_items())
        to_process_forms = {task["formula_pretty"] for task in to_process}

        self.assertEqual(len(to_process), 197)
        self.assertEqual(len(to_process_forms), 12)
        self.assertTrue("Sr" in to_process_forms)
        self.assertTrue("Hf" in to_process_forms)
        self.assertTrue("O2" in to_process_forms)
        self.assertFalse("H" in to_process_forms)

    def test_process_item(self):
        for task in self.tasks.query():
            ml_strucs = self.mlbuilder.process_item(task)
            t_type = task_type(get(task, 'input.incar'))
            if not any([t in t_type for t in self.mlbuilder.task_types]):
                self.assertEqual(len(ml_strucs),0)
            else:
                self.assertEqual(len(ml_strucs), sum([len(t["output"]["ionic_steps"]) for t in task["calcs_reversed"]]))


    def test_update_targets(self):
        for task in self.tasks.query():
            ml_strucs = self.mlbuilder.process_item(task)
            self.mlbuilder.update_targets([ml_strucs])
        self.assertEqual(len(self.ml_strucs.distinct("task_id")), 102)
        self.assertEqual(len(list(self.ml_strucs.query())), 1012)

    def tearDown(self):
        self.ml_strucs.collection.drop()

if __name__ == "__main__":
    unittest.main()
