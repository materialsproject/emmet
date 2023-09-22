import pytest
from maggma.stores import MemoryStore
from pymatgen.core import Lattice, Structure

from emmet.builders.materials.ml import MLIPBuilder


@pytest.fixture()
def fake_materials():
    materials_store = MemoryStore(key="material_id")
    materials_store.connect()
    # Add fake data to materials store
    materials_store.update(
        {
            "material_id": "1234",
            "structure": Structure.from_spacegroup(
                "Pm-3m", Lattice.cubic(4.2), ["Cs", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]]
            ).as_dict(),
            "deprecated": False,
        }
    )
    return materials_store


def test_ml_ip_builder(fake_materials):
    ml_potential_store = MemoryStore(key="material_id")
    for model in ("chgnet", "m3gnet"):
        builder = MLIPBuilder(
            materials=fake_materials, ml_potential=ml_potential_store, model=model
        )
        item = fake_materials.query_one()

    result_doc = builder.unary_function(item)

    # Add specific assertions for the expected structure of result_doc
    assert isinstance(result_doc, dict)
