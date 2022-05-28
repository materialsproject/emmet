import pytest

from monty.serialization import loadfn

from emmet.core.jaguar.pes import PESPointDoc, TransitionStateDoc
from emmet.core.jaguar.task import TaskDocument


@pytest.fixture(scope="session")
def task_ts(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_ts_39.json").as_posix())
    return TaskDocument(**task)


@pytest.fixture(scope="session")
def task_sp(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_sp_36810.json").as_posix())
    return TaskDocument(**task)


def test_make_ts(task_ts):

    ts_doc = TransitionStateDoc.from_tasks([task_ts])
    assert ts_doc.charge == -1
    assert len(ts_doc.task_ids) == 1
    assert len(ts_doc.entries) == 1


def test_make_bad_point(task_sp):

    with pytest.raises(Exception):
        PESPointDoc.from_tasks([task_sp])

    deprecated = PESPointDoc.construct_deprecated_pes_point([task_sp])

    assert deprecated.deprecated
    assert deprecated.charge == -2
    assert len(deprecated.task_ids) == 1
    assert deprecated.entries is None


def test_schema():
    PESPointDoc.schema()
