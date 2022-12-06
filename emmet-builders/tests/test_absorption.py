from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.absorption_spectrum import AbsorptionBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "sample_absorptions.json")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def absorption_store():
    return MemoryStore(key="material_id")


def test_absorption_builder(tasks_store, absorption_store, materials_store):

    builder = AbsorptionBuilder(
        tasks=tasks_store, absorption=absorption_store, materials=materials_store
    )
    builder.run()

    assert absorption_store.count() == 1
    assert absorption_store.count({"deprecated": False}) == 1


def test_serialization(tmpdir):
    builder = AbsorptionBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
