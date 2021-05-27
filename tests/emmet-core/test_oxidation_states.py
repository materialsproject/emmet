import pytest
from pymatgen.core import Structure
from pymatgen.util.testing import PymatgenTest

from emmet.core.oxidation_states import OxidationStateDocument

test_structures = {
    name: struc
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
    ]
}

fail_structures = {
    name: struc
    for name, struc in PymatgenTest.TEST_STRUCTURES.items()
    if name
    in [
        "TiO2",
        "BaNiO3",
        "VO2",
    ]
}


@pytest.mark.parametrize("structure", test_structures.values())
def test_oxidation_state(structure: Structure):
    """Very simple test to make sure this actually works"""

    doc = OxidationStateDocument.from_structure(structure)
    print(structure.composition)
    assert doc is not None


@pytest.mark.parametrize("structure", fail_structures.values())
def test_oxidation_state_failures(structure: Structure):
    """Very simple test to make sure this actually fails"""

    doc = OxidationStateDocument.from_structure(structure)
    print(structure.composition)
    assert doc is None
