from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.piezoelectric import PiezoelectricBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_As2SO6_tasks.json.gz")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def piezoelectric_store():
    return MemoryStore(key="material_id")


def test_piezoelectric_builder(tasks_store, piezoelectric_store, materials_store):
    builder = PiezoelectricBuilder(
        tasks=tasks_store, piezoelectric=piezoelectric_store, materials=materials_store
    )
    builder.run()

    assert piezoelectric_store.count() == 1
    assert piezoelectric_store.count({"deprecated": False}) == 1


def test_serialization(tmpdir):
    builder = PiezoelectricBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
