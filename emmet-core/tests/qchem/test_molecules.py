import json
import datetime

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.calc_types import TaskType
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.qchem.task import TaskDocument


@pytest.fixture(scope="session")
def test_tasks(test_dir):
    with zopen(test_dir / "liec_tasks.json.gz") as f:
        data = json.load(f)

    for d in data:
        d["last_updated"] = datetime.datetime.strptime(
            d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f"
        )

    tasks = [TaskDocument(**t) for t in data]
    return tasks


@pytest.mark.xfail
def test_make_mol(test_tasks):

    molecule = MoleculeDoc.from_tasks(test_tasks)
    assert molecule.formula_alphabetical == "C3 H4 Li1 O3"
    assert len(molecule.task_ids) == 5
    assert len(molecule.entries) == 5

    bad_task_group = [
        task
        for task in test_tasks
        if task.task_type
        not in [
            TaskType.Geometry_Optimization,
            TaskType.Frequency_Flattening_Geometry_Optimization,
        ]
    ]

    with pytest.raises(Exception):
        MoleculeDoc.from_tasks(bad_task_group)


def test_make_deprecated_mol(test_tasks):
    bad_task_group = [
        task
        for task in test_tasks
        if task.task_type
        not in [
            TaskType.Geometry_Optimization,
            TaskType.Frequency_Flattening_Geometry_Optimization,
        ]
    ]

    molecule = MoleculeDoc.construct_deprecated_molecule(bad_task_group)

    assert molecule.deprecated
    assert molecule.formula_alphabetical == "C3 H4 Li1 O3"
    assert len(molecule.task_ids) == 4
    assert molecule.entries is None


def test_schema():
    MoleculeDoc.schema()
