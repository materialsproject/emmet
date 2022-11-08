import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.materials.basic_descriptors import BasicDescriptorsBuilder
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


def test_basic_descriptions(materials_store):
    descriptors_store = MemoryStore()
    builder = BasicDescriptorsBuilder(
        materials=materials_store, descriptors=descriptors_store
    )
    builder.run()

    print(descriptors_store.query_one({}))
    assert descriptors_store.count() == 1
