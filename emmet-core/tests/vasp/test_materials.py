import pytest

from emmet.core import ARROW_COMPATIBLE
from emmet.core.vasp.calc_types import TaskType
from emmet.core.vasp.material import MaterialsDoc

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


def test_make_mat(si_tasks):
    material = MaterialsDoc.from_tasks(si_tasks)
    assert material.formula_pretty == "Si"
    assert len(material.task_ids) == 4
    assert len(material.entries.model_dump(exclude_none=True)) == 1

    bad_task_group = [
        task for task in si_tasks if task.task_type != TaskType.Structure_Optimization
    ]

    with pytest.raises(Exception):
        MaterialsDoc.from_tasks(bad_task_group, use_statics=False)


def test_make_deprecated_mat(si_tasks):
    bad_task_group = [
        task for task in si_tasks if task.task_type != TaskType.Structure_Optimization
    ]

    material = MaterialsDoc.construct_deprecated_material(bad_task_group)

    assert material.deprecated
    assert material.formula_pretty == "Si"
    assert len(material.task_ids) == 3
    assert material.entries is None


def test_schema():
    MaterialsDoc.schema()


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(si_tasks):
    doc = MaterialsDoc.from_tasks(si_tasks)
    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}), type=arrowize(MaterialsDoc)
    )
    test_arrow_doc = MaterialsDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert doc == test_arrow_doc
