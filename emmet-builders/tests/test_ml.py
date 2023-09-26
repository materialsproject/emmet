from typing import TYPE_CHECKING, Union

import pytest
from maggma.stores import MemoryStore
from matcalc.util import get_universal_calculator
from pymatgen.core import Lattice, Structure

from emmet.builders.materials.ml import MLBuilder

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator


material_id = "1234"


@pytest.fixture()
def materials_store():
    materials_store = MemoryStore(key="material_id")
    materials_store.connect()
    # Add fake data to materials store
    materials_store.update(
        {
            "material_id": material_id,
            "structure": Structure.from_spacegroup(
                "Pm-3m", Lattice.cubic(4.2), ["Cs", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]]
            ).as_dict(),
            "deprecated": False,
        }
    )
    return materials_store


@pytest.mark.parametrize("model", [get_universal_calculator("chgnet"), "m3gnet"])
def test_ml_ip_builder(materials_store: MemoryStore, model: Union[str, "Calculator"]):
    ml_store = MemoryStore(key="material_id")

    builder = MLBuilder(materials=materials_store, ml_potential=ml_store, model=model)
    item = materials_store.query_one()

    result_doc = builder.unary_function(item)

    assert result_doc["material_id"] == material_id
    if isinstance(model, str):
        assert result_doc["model_name"] == model
    assert result_doc["energy"] < -6
