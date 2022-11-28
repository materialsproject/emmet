from monty.dev import deprecated
import pytest
from pymatgen.core import Structure, Composition
from pymatgen.util.testing import PymatgenTest

from emmet.core.chemenv import ChemEnvDoc

test_structures = {
    name: struc.get_reduced_structure()
    for name, struc in PymatgenTest.TEST_STRUCTURES.items()
    if name
    in [
        "SiO2",
        "Li2O",
        "LiFePO4",
        "TlBiSe2",
        "K2O2",
        "Li3V2(PO4)3",
        "Li2O2",
        "CsCl",
        "NaFePO4",
        "Pb2TiZrO6",
        "SrTiO3",
        "TiO2",
        "BaNiO3",
        "VO2",
    ]
}


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
        assert doc.dict()["warnings"] is None
    # elif structure.composition.almost_equals(Composition("CsCl")):
    #    # We do not have reference polyhedra above a certain number of neighbors.
    #    # ChemEnv cannot deliver an answer without oxidation states.
    #    assert doc.dict()["warnings"] == "ChemEnv algorithm failed."
    else:
        assert (
            doc.dict()["warnings"]
            == "No oxidation states available. Cation-anion bonds cannot be identified."
        )
