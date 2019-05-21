import unittest
import os

from emmet.vasp.task_tagger import TaskTagger
from maggma.stores import JSONStore, MemoryStore

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "test_tasktagger_tasks.json")


class TaskTaggerTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.test_tasks = JSONStore(test_tasks)
        self.task_types = MemoryStore("task_types")
        self.test_tasks.connect()
        self.task_types.connect()

    def test_mp_defs(self):
        task_tagger = TaskTagger(tasks=self.test_tasks, task_types=self.task_types)

        for t in task_tagger.get_items():
            processed = task_tagger.calc(t)
            true_type = self.test_tasks.query_one(
                criteria={"task_id": t["task_id"]},
                properties=["true_task_type"],
            )["true_task_type"]
            self.assertEqual(processed["task_type"], true_type)


if __name__ == "__main__":
    unittest.main()
