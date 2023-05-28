from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.elasticity import ElasticityBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "elasticity/SiC_tasks.json.gz")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def elasticity_store():
    return MemoryStore(key="material_id")


def test_elasticity_builder(tasks_store, materials_store, elasticity_store):
    builder = ElasticityBuilder(
        tasks=tasks_store, materials=materials_store, elasticity=elasticity_store
    )
    builder.run()

    assert elasticity_store.count() == 3
    assert elasticity_store.count({"deprecated": False}) == 3


def test_serialization(tmpdir):
    builder = ElasticityBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
