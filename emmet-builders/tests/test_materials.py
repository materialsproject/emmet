from pathlib import Path
from emmet.builders.settings import EmmetBuildSettings

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.vasp.materials import MaterialsBuilder
from emmet.builders.vasp.task_validator import TaskValidator


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_si_tasks.json.gz")


@pytest.fixture(scope="session")
def validation_store(tasks_store):
    settings = EmmetBuildSettings(VASP_VALIDATE_POTCAR_HASHES=False)
    validation_store = MemoryStore()
    builder = TaskValidator(
        tasks=tasks_store, task_validation=validation_store, settings=settings
    )
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
    assert materials_store.count({"deprecated": False}) == 1


def test_serialization(tmpdir):
    builder = MaterialsBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
