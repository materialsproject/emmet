import os
from monty.io import zopen

from emmet.core.trajectory import Trajectory

from emmet.api.routes.materials.tasks.query_operators import (
    MultipleTaskIDsQuery,
    TrajectoryQuery,
    DeprecationQuery,
    EntryQuery,
)
from emmet.api.core.settings import MAPISettings

import json


def test_multiple_task_ids_query():
    op = MultipleTaskIDsQuery()

    assert op.query(task_ids=" mp-149, mp-13") == {
        "criteria": {"task_id": {"$in": ["mp-149", "mp-13"]}}
    }


def test_entries_query():
    op = EntryQuery()

    q = {"criteria": {"task_id": {"$in": ["mp-149", "mp-13"]}}}

    assert op.query(task_ids=" mp-149, mp-13") == q

    with zopen(
        os.path.join(MAPISettings().TEST_FILES, "tasks_Li_Fe_V.json.gz"), "rt"
    ) as file:
        tasks = json.load(file)
    docs = op.post_process(tasks, q)
    assert docs[0]["entry"]["@class"] == "ComputedStructureEntry"


def test_trajectory_query():
    op = TrajectoryQuery()

    q = {"criteria": {"task_id": {"$in": ["mp-149", "mp-13"]}}}

    assert op.query(task_ids=" mp-149, mp-13") == q

    with zopen(
        os.path.join(MAPISettings().TEST_FILES, "tasks_Li_Fe_V.json.gz"), "rt"
    ) as file:
        tasks = json.load(file)
    docs = op.post_process(tasks, q)

    # assert return type is a trajectory by duck typing
    traj_model_dump_fields = {
        field
        for field, field_meta in Trajectory.model_fields.items()
        if not field_meta.exclude
    }
    assert (
        set(docs[0]["trajectories"][0]).intersection(traj_model_dump_fields)
        == traj_model_dump_fields
    )

    # assert that returned traj is JSONable
    assert isinstance(json.dumps(docs[0]["trajectories"]), str)


def test_deprecation_query():
    op = DeprecationQuery()

    q = {"criteria": {"deprecated_tasks": {"$in": ["mp-149", "mp-13"]}}}

    assert op.query(task_ids=" mp-149, mp-13") == q

    docs = [
        {"task_id": "mp-149", "deprecated_tasks": ["mp-149"]},
        {"task_id": "mp-13", "deprecated_tasks": ["mp-1234"]},
    ]
    r = op.post_process(docs, q)

    assert r[0] == {
        "task_id": "mp-149",
        "deprecated": True,
        "deprecation_reason": None,
    }

    assert r[1] == {
        "task_id": "mp-13",
        "deprecated": False,
        "deprecation_reason": None,
    }
