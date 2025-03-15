import pytest
from pymatgen.core import Structure

from . import test_structures
from emmet.core.arrow import cleanup_msonables
from emmet.core.chemenv import ChemEnvDoc


@pytest.mark.parametrize("structure", test_structures.values())
def test_chemenv(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = ChemEnvDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )
    valences = [getattr(site.specie, "oxi_state", None) for site in structure]
    valences = [v for v in valences if v is not None]
    if len(valences) == len(structure):
        assert doc.model_dump()["warnings"] is None
    # elif structure.composition.almost_equals(Composition("CsCl")):
    #    # We do not have reference polyhedra above a certain number of neighbors.
    #    # ChemEnv cannot deliver an answer without oxidation states.
    #    assert doc.model_dump()["warnings"] == "ChemEnv algorithm failed."
    else:
        assert (
            doc.model_dump()["warnings"]
            == "No oxidation states available. Cation-anion bonds cannot be identified."
        )


def test_chemenv_arrow_round_trip_serialization(
    structure=next(iter(test_structures.values())),
):
    doc = ChemEnvDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )
    arrow_struct = doc.model_dump(context={"format": "arrow"})
    test_arrow_doc = ChemEnvDoc.from_arrow(arrow_struct)

    assert cleanup_msonables(doc.model_dump()) == cleanup_msonables(
        test_arrow_doc.model_dump()
    )
