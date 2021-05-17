import pytest
from pathlib import Path
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.vasp.materials import MaterialsBuilder
from emmet.builders.materials.electronic_structure import ElectronicStructureBuilder
from monty.serialization import dumpfn, loadfn
from emmet.core.utils import jsanitize


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
def electronic_structure_store():
    return MemoryStore(key="material_id")


@pytest.fixture
def bandstructure_fs():
    return MemoryStore()


@pytest.fixture
def dos_fs():
    return MemoryStore()


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
    assert electronic_structure_store.count() == 1


def test_serialization(tmpdir):
    builder = ElectronicStructureBuilder(MemoryStore(), MemoryStore(), MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
