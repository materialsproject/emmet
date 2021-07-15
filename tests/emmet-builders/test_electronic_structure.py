from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.electronic_structure import ElectronicStructureBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(
        test_dir / "electronic_structure/es_task_docs.json.gz", key="task_id"
    )


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture
def electronic_structure_store():
    return MemoryStore(key="material_id")


@pytest.fixture
def bandstructure_fs(test_dir):
    return JSONStore(
        test_dir / "electronic_structure/es_bs_objs.json.gz", key="task_id"
    )


@pytest.fixture
def dos_fs(test_dir):
    return JSONStore(
        test_dir / "electronic_structure/es_dos_objs.json.gz", key="task_id"
    )


def test_electronic_structure_builder(
    tasks_store, materials_store, electronic_structure_store, bandstructure_fs, dos_fs
):

    builder = ElectronicStructureBuilder(
        tasks=tasks_store,
        materials=materials_store,
        electronic_structure=electronic_structure_store,
        bandstructure_fs=bandstructure_fs,
        dos_fs=dos_fs,
    )

    builder.run()
    assert electronic_structure_store.count() == 3


def test_serialization(tmpdir):
    builder = ElectronicStructureBuilder(
        MemoryStore(), MemoryStore(), MemoryStore(), MemoryStore(), MemoryStore()
    )

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
