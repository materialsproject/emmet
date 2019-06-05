import unittest
import os
from datetime import datetime

from emmet.vasp.task_tagger import TaskTagger
from maggma.stores import JSONStore, MemoryStore

from pymatgen import Structure
from pymatgen.io.vasp.sets import MPRelaxSet, MPStaticSet, MPNonSCFSet

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(
    module_dir, "..", "..", "..", "test_files", "test_tasktagger_tasks.json"
)


class TaskTaggerTest(unittest.TestCase):
    def setUp(self):
        coords = list()
        coords.append([0, 0, 0])
        coords.append([0.75, 0.5, 0.75])
        lattice = [
            [3.8401979337, 0.00, 0.00],
            [1.9200989668, 3.3257101909, 0.00],
            [0.00, -2.2171384943, 3.1355090603],
        ]

        structure = Structure(lattice, ["Si", "Si"], coords)

        input_sets = {
            "GGA Structure Optimization": MPRelaxSet(structure),
            "GGA Static": MPStaticSet(structure),
            "GGA NSCF Line": MPNonSCFSet(structure, mode="line"),
            "GGA NSCF Uniform": MPNonSCFSet(structure, mode="uniform"),
        }

        tasks = []
        t_id = 1
        for task_type, input_set in input_sets.items():
            doc = {
                "true_task_type": task_type,
                "last_updated": datetime.now(),
                "task_id": t_id,
                "state": "successful",
                "orig_inputs": {
                    "incar": input_set.incar.as_dict(),
                    "kpoints": input_set.kpoints.as_dict(),
                },
                "output": {"structure": structure.as_dict()},
            }
            t_id += 1
            tasks.append(doc)

        self.test_tasks = MemoryStore("tasks")
        self.task_types = MemoryStore("task_types")
        self.test_tasks.connect()
        self.task_types.connect()

        self.test_tasks.update(tasks)

    def test_mp_defs(self):
        task_tagger = TaskTagger(tasks=self.test_tasks, task_types=self.task_types)

        for t in task_tagger.get_items():

            processed = task_tagger.calc(t)
            true_type = self.test_tasks.query_one(
                criteria={"task_id": t["task_id"]}, properties=["true_task_type"]
            )["true_task_type"]

            self.assertEqual(processed["task_type"], true_type)


if __name__ == "__main__":
    unittest.main()
