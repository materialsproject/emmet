from emmet.api.routes.molecules.tasks.query_operators import (
    MultipleTaskIDsQuery,
    # TrajectoryQuery,
    DeprecationQuery,
    # EntryQuery,
)

from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_multiple_task_ids_query():
    op = MultipleTaskIDsQuery()

    assert op.query(task_ids=" mpcule-149, mpcule-13") == {
        "criteria": {"task_id": {"$in": ["mpcule-149", "mpcule-13"]}}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(task_ids=" mpcule-149, mpcule-13") == {
            "criteria": {"task_id": {"$in": ["mpcule-149", "mpcule-13"]}}
        }


def test_deprecation_query():
    op = DeprecationQuery()

    assert op.query(task_ids=" mpcule-149, mpcule-13") == {
        "criteria": {"deprecated_tasks": {"$in": ["mpcule-149", "mpcule-13"]}}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        query = {"criteria": {"deprecated_tasks": {"$in": ["mpcule-149", "mpcule-13"]}}}

        assert new_op.query(task_ids=" mpcule-149, mpcule-13") == query

    docs = [
        {"task_id": "mpcule-149", "deprecated_tasks": ["mpcule-149"]},
        {"task_id": "mpcule-13", "deprecated_tasks": ["mpcule-1234"]},
    ]
    r = op.post_process(docs, query)

    assert r[0] == {
        "task_id": "mpcule-149",
        "deprecated": True,
        "deprecation_reason": None,
    }

    assert r[1] == {
        "task_id": "mpcule-13",
        "deprecated": False,
        "deprecation_reason": None,
    }
