from monty.dev import deprecated
import pytest
from pymatgen.core import Structure
from pymatgen.util.testing import PymatgenTest

from emmet.core.robocrys import RobocrystallogapherDoc

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
        "CsCl",
        "Li2O2",
        "NaFePO4",
        "Pb2TiZrO6",
        "SrTiO3",
        "TiO2",
        "BaNiO3",
        "VO2",
    ]
}


@pytest.mark.parametrize("structure", test_structures.values())
def test_robocrys(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = RobocrystallogapherDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )
    assert doc is not None
