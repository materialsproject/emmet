import unittest
import os

from monty.serialization import loadfn
from emmet.vasp.builders.task_tagger import TaskTagger
from maggma.stores import JSONStore, MemoryStore

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tag_defs = os.path.join(module_dir,"..", "..","..", "..", "test_files", "test_tag_defs.json")
test_tasks = os.path.join(module_dir, "..","..","..", "..", "test_files", "test_tags_tasks.json")

class TaslTaggerTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.tasks = JSONStore(test_tasks)
        self.tag_defs = JSONStore(test_tag_defs)
        self.tags = MemoryStore("tags")

    def test(self):

        task_tagger = TaskTagger(tasks=self.tasks,
                                 tag_defs=self.tag_defs,
                                 tags=self.tags)

        for t in task_tagger.get_items():
            processed = task_tagger.process_item(t)
            if processed:
                self.assertEqual(processed['task_type'],
                                 t['task_doc']['true_task_type'])


if __name__ == "__main__":
    unittest.main()
