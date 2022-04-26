import json

import pytest
from monty.io import zopen

from emmet.core.vasp.calc_types import TaskType
from emmet.core.vasp.material import MaterialsDoc
from emmet.core.vasp.task_valid import TaskDocument


@pytest.fixture
def test_tasks(test_dir):
    with zopen(test_dir / "test_si_tasks.json.gz") as f:
        tasks = json.load(f)

    tasks = [TaskDocument(**t) for t in tasks]
    return tasks


def test_make_mat(test_tasks):

    material = MaterialsDoc.from_tasks(test_tasks)
    assert material.formula_pretty == "Si"
    assert len(material.task_ids) == 4
    assert len(material.entries) == 1

    bad_task_group = [
        task for task in test_tasks if task.task_type != TaskType.Structure_Optimization
    ]

    with pytest.raises(Exception):
        MaterialsDoc.from_tasks(bad_task_group, use_statics=False)


def test_make_deprecated_mat(test_tasks):
    bad_task_group = [
        task for task in test_tasks if task.task_type != TaskType.Structure_Optimization
    ]

    material = MaterialsDoc.construct_deprecated_material(bad_task_group)

    assert material.deprecated
    assert material.formula_pretty == "Si"
    assert len(material.task_ids) == 3
    assert material.entries is None


def test_schema():
    MaterialsDoc.schema()
