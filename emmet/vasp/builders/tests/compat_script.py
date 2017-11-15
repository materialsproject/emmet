import unittest
import os
import numpy as np
from tqdm import tqdm

from emmet.vasp.builders.compatibility import MPWorksCompatibilityBuilder, \
        set_mongolike, convert_mpworks_to_atomate, convert_string_deformation_to_list
from maggma.stores import JSONStore, MemoryStore, MongoStore
from maggma.runner import Runner
from monty.json import MontyEncoder, MontyDecoder

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

test_coll = MongoStore(host='localhost', port=27017, database="test_emmet", 
                           collection_name="test_mpworks_tasks")
test_coll.connect()
target_coll = MongoStore(host='localhost', port=27017, database='test_emmet',
                         collection_name="test_atomate_tasks")
target_coll.connect()

def build_test_coll(mpworks_file, cutoff=50):
    """
    small function to create a test collection
    """
    m = MongoStore.from_db_file(mpworks_file)
    m.connect()
    orig_task_ids = list(m.distinct("original_task_id"))
    tasks = []
    for otask_id in tqdm(orig_task_ids[:cutoff], total=cutoff):
        tasks += list(m.query(criteria={"task_id": otask_id}))
        tasks += list(m.query(criteria={"original_task_id": otask_id}))
    test_coll.collection.insert_many(tasks)
    return True

if __name__ == "__main__":
    mpworks_file = "../../../../scripts/elastic_tasks.yaml"
    # build_test_coll(mpworks_file)
    builder = MPWorksCompatibilityBuilder(test_coll, target_coll)
    runner = Runner([builder])
    runner.run()

    # snippet to fix issue with compatibility
    """
    m = MongoStore.from_db_file("../../../../scripts/atomate_tasks.yaml")
    m.connect()
    docs = []
    cursor_1 = m.query(["task_id", "transmuter"],
                       {"transmuter.transformation_params.0": {"$regex": "]"},
                        "transmuter": {"$exists": True}})
    for task in tqdm(cursor_1, total=cursor_1.count()):
        string_defo = task["transmuter"]["transformation_params"]["0"]
        assert isinstance(string_defo, str), "string defo is not string"
        defo = convert_string_deformation_to_list(string_defo)
        defo = np.transpose(defo).tolist()
        docs.append({"task_id": task['task_id'],
                     "transmuter": {"transformation_params":
                                    [{"deformation": defo}]}})
    cursor_2 = m.query(["task_id", "transmuter"], 
                       {"transmuter.transformation_params.0.0": {"$exists": True}})
    for task in tqdm(cursor_2, total=cursor_2.count()):
        defo = task['transmuter']['transformation_params']["0"]
        docs.append({"task_id": task['task_id'],
                     "transmuter": {"transformation_params":
                                    [{"deformation": defo}]}})
    m.update("task_id", docs)
    """
