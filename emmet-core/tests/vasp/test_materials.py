import json

import pyarrow as pa
import pytest
from monty.io import zopen

from emmet.core.utils import jsanitize
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
    assert len(material.entries.model_dump(exclude_none=True)) == 1

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


def test_material_arrow_round_trip_serialization(test_tasks):
    doc = MaterialsDoc.from_tasks(test_tasks)

    sanitized_doc = jsanitize(doc.model_dump(), allow_bson=True)
    test_arrow_doc = MaterialsDoc(
        **pa.array([sanitized_doc], type=MaterialsDoc.as_arrow())
        .to_pandas(maps_as_pydicts="strict")
        .iloc[0]
    )

    assert doc == test_arrow_doc
