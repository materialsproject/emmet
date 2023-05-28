import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.materials.oxidation_states import OxidationStatesBuilder


@pytest.fixture(scope="session")
def fake_materials(test_dir):
    entries = JSONStore(test_dir / "LiTiO2_batt.json", key="entry_id")
    entries.connect()

    materials_store = MemoryStore(key="material_id")
    materials_store.connect()

    for doc in entries.query():
        materials_store.update(
            {
                "material_id": doc["entry_id"],
                "structure": doc["structure"],
                "deprecated": False,
            }
        )
    return materials_store


def test_oxidation_store(fake_materials):
    oxi_store = MemoryStore()
    builder = OxidationStatesBuilder(
        materials=fake_materials, oxidation_states=oxi_store
    )
    builder.run()

    assert oxi_store.count() == 6
    assert all([isinstance(d["composition"], dict) for d in oxi_store.query()])
