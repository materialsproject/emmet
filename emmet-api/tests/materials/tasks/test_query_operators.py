import json
import os

from monty.io import zopen

from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import MultiTaskIDQuery
from emmet.api.routes.materials.tasks.query_operators import EntryQuery


def test_multiple_task_ids_query():
    op = MultiTaskIDQuery(atlas_search=True)

    assert op.query(task_ids=" mp-149, mp-13") == {
        "criteria": {"in": {"path": "task_id", "value": ["aaaaaaft", "aaaaaaan"]}}
    }


def test_entries_query():
    op = EntryQuery()

    q = {"criteria": {"task_id": {"$in": ["aaaaaaft", "aaaaaaan"]}}}

    assert op.query(task_ids=" mp-149, mp-13") == q

    with zopen(
        os.path.join(MAPISettings().TEST_FILES, "tasks_Li_Fe_V.json.gz"), "rt"
    ) as file:
        tasks = json.load(file)
    docs = op.post_process(tasks, q)
    assert docs[0]["entry"]["@class"] == "ComputedStructureEntry"
