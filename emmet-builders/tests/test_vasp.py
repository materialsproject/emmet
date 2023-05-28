import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.settings import EmmetBuildSettings
from emmet.builders.vasp.task_validator import TaskValidator

intermediate_stores = ["validation"]


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_si_tasks.json.gz")


@pytest.fixture(scope="session")
def validation_store():
    return MemoryStore()


def test_validator(tasks_store, validation_store):
    settings = EmmetBuildSettings(VASP_VALIDATE_POTCAR_HASHES=False)
    builder = TaskValidator(
        tasks=tasks_store, task_validation=validation_store, settings=settings
    )
    builder.run()
    assert validation_store.count() == tasks_store.count()
    assert validation_store.count({"valid": True}) == tasks_store.count()
    assert all(list(d["run_type"] == "GGA" for d in validation_store.query()))
