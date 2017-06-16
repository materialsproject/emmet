import unittest
import os

from monty.serialization import loadfn
from emmet.vasp.builders.task_tagger import TaskTagger
from maggma.stores import JSONStore, MemoryStore

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..","..","..", "..", "test_files", "test_tasktagger_tasks.json")

class TaslTaggerTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.test_tasks = JSONStore(test_tasks)
        self.task_types = MemoryStore("task_types")

    def test_mp_defs(self):
        task_tagger = TaskTagger(tasks=self.test_tasks,
                                 task_types=self.task_types)

        for t in task_tagger.get_items():
            processed = task_tagger.process_item(t)
            if processed:
                self.assertEqual(processed['task_type'],
                                 t['true_task_type'])


if __name__ == "__main__":
    unittest.main()
