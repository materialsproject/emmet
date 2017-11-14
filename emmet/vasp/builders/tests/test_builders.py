import unittest
import os
import glob
import logging
import json
import sys
from monty.io import zopen
from atomate.vasp.database import VaspCalcDb

from maggma.stores import MongoStore

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_dir = os.path.join(module_dir, "..", "..", "..",
                        "..", "test_files", "vasp", "builders")


class BuilderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        root.addHandler(ch)

        cls.tasks = MongoStore("emmet_test", "tasks", lu_field="last_updated")
        cls.tasks.connect()
        cleardb(cls.tasks.collection.database)

        vaspdb = VaspCalcDb(database="emmet_test")
        tasks_dir = os.path.join(test_dir, "tasks")

        raw_tasks = glob.glob(os.path.join(test_dir, "tasks", "*.json.gz"))
        for task_path in raw_tasks:
            with zopen(task_path) as f:
                data = f.read().decode()
                task = json.loads(data)
            vaspdb.insert_task(task, parse_dos=True, parse_bs=True)

    @classmethod
    def tearDownClass(cls):
        cleardb(cls.tasks.collection.database)


def cleardb(db):
    for coll in db.collection_names():
        if coll != "system.indexes":
            db[coll].drop()

if __name__ == "__main__":
    unittest.main()
