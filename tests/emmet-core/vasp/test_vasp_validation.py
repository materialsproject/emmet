import pytest
import json
from maggma.stores import JSONStore, MemoryStore
from emmet.core.vasp.validation import ValidationDoc
from emmet.core.vasp.task import TaskDocument
from monty.io import zopen


@pytest.fixture(scope="session")
def tasks(test_dir):
    with zopen(test_dir / "test_si_tasks.json.gz") as f:
        data = json.load(f)

    return [TaskDocument(**d) for d in data]


def test_validator(tasks):
    validation_docs = [ValidationDoc.from_task_doc(task) for task in tasks]

    assert len(validation_docs) == len(tasks)
    assert all(doc.valid for doc in validation_docs)
