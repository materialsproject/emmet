import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.materials.basic_descriptors import BasicDescriptorsBuilder
from emmet.builders.vasp.materials import MaterialsBuilder
from emmet.builders.materials.similarity import StructureSimilarityBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(
        [test_dir / "test_si_tasks.json.gz", test_dir / "test_As2SO6_tasks.json.gz"]
    )


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture(scope="session")
def descriptors_store(materials_store):
    descriptors_store = MemoryStore(key="task_id")
    builder = BasicDescriptorsBuilder(
        materials=materials_store, descriptors=descriptors_store
    )
    builder.run()
    return descriptors_store


def test_basic_descriptions(descriptors_store):
    similarity_store = MemoryStore()
    builder = StructureSimilarityBuilder(
        structure_similarity=similarity_store, site_descriptors=descriptors_store
    )
    builder.run()

    print(similarity_store.query_one({}))
    assert similarity_store.count() == 1
