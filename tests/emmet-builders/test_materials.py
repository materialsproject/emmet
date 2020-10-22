import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.vasp.task_validator import TaskValidator
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_si_tasks.json.gz")


@pytest.fixture(scope="session")
def validation_store(tasks_store):
    validation_store = MemoryStore()
    builder = TaskValidator(tasks=tasks_store, task_validation=validation_store)
    builder.run()
    return validation_store


@pytest.fixture
def materials_store():
    return MemoryStore()


def test_materials_builder(tasks_store, validation_store, materials_store):

    builder = MaterialsBuilder(
        tasks=tasks_store, task_validation=validation_store, materials=materials_store
    )
    builder.run()
    assert materials_store.count() == 1
    print(materials_store.query_one())
    assert materials_store.count({"deprecated": False}) == 1
