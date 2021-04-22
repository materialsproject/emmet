import json

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.io import zopen

from emmet.core import SETTINGS
from emmet.core.vasp.calc_types import RunType, TaskType, run_type, task_type
from emmet.core.vasp.task import TaskDocument
from emmet.core.vasp.validation import ValidationDoc


def test_task_tye():

    # TODO: Switch this to actual inputs?
    input_types = [
        ("NSCF Line", {"incar": {"ICHARG": 11}, "kpoints": {"labels": ["A"]}}),
        ("NSCF Uniform", {"incar": {"ICHARG": 11}}),
        ("Dielectric", {"incar": {"LEPSILON": True}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 7}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 8}}),
        ("DFPT", {"incar": {"IBRION": 7}}),
        ("DFPT", {"incar": {"IBRION": 8}}),
        ("Static", {"incar": {"NSW": 0}}),
    ]

    for _type, inputs in input_types:
        assert task_type(inputs) == TaskType(_type)


def test_run_type():

    params_sets = [
        ("GGA", {"GGA": "--"}),
        ("GGA+U", {"GGA": "--", "LDAU": True}),
        ("SCAN", {"METAGGA": "Scan"}),
        ("SCAN+U", {"METAGGA": "Scan", "LDAU": True}),
    ]

    for _type, params in params_sets:
        assert run_type(params) == RunType(_type)


@pytest.fixture(scope="session")
def tasks(test_dir):
    with zopen(test_dir / "test_si_tasks.json.gz") as f:
        data = json.load(f)

    return [TaskDocument(**d) for d in data]


def test_validator(tasks):
    validation_docs = [ValidationDoc.from_task_doc(task) for task in tasks]

    assert len(validation_docs) == len(tasks)
    assert all(doc.valid for doc in validation_docs)


def test_computed_entry(tasks):
    entries = [task.entry for task in tasks]
    ids = {e.entry_id for e in entries}
    assert ids == {"mp-1141021", "mp-149", "mp-1686587", "mp-1440634"}


@pytest.fixture(scope="session")
def task_ldau(test_dir):
    with zopen(test_dir / "test_task.json") as f:
        data = json.load(f)

    return TaskDocument(**data)


def test_ldau(task_ldau):
    assert ValidationDoc.from_task_doc(task_ldau).valid == False