from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.dielectric import DielectricBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_si_tasks.json.gz")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def dielectric_store():
    return MemoryStore(key="material_id")


def test_dielectric_builder(tasks_store, dielectric_store, materials_store):
    builder = DielectricBuilder(
        tasks=tasks_store, dielectric=dielectric_store, materials=materials_store
    )
    builder.run()

    assert dielectric_store.count() == 1
    assert dielectric_store.count({"deprecated": False}) == 1


def test_serialization(tmpdir):
    builder = DielectricBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
