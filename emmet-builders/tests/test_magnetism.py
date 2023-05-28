from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.magnetism import MagneticBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "magnetism/magnetism_task_docs.json.gz")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def magnetism_store():
    return MemoryStore(key="material_id")


def test_magnetism_builder(tasks_store, magnetism_store, materials_store):
    builder = MagneticBuilder(
        tasks=tasks_store, magnetism=magnetism_store, materials=materials_store
    )
    builder.run()

    assert magnetism_store.count() == 4
    assert magnetism_store.count({"deprecated": False}) == 4

    test_mpids = {
        "mp-1289887": "AFM",
        "mp-1369002": "FiM",
        "mp-1791788": "NM",
        "mp-1867075": "FM",
    }

    print(list([doc["material_id"] for doc in magnetism_store.query({})]))

    for mpid in test_mpids:
        doc = magnetism_store.query_one({"material_id": mpid})
        assert doc["ordering"] == test_mpids[mpid]


def test_serialization(tmpdir):
    builder = MagneticBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
