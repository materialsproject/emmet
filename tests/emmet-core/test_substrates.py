import pytest
from pymatgen.util.testing import PymatgenTest

from emmet.core.substrates.substrates import (
    DEFAULT_SUBSTRATES,
    SubstrateMatch,
    SubstratesDoc,
)

test_structures = {
    name: struc.get_reduced_structure()
    for name, struc in PymatgenTest.TEST_STRUCTURES.items()
    if name
    in [
        "SiO2",
        "Li2O",
        # "LiFePO4",
        "TlBiSe2",
        # "K2O2",
        # "Li3V2(PO4)3",
        "CsCl",
        "Li2O2",
        # "NaFePO4",
        # "Pb2TiZrO6",
        "SrTiO3",
        # "TiO2",
        # "BaNiO3",
        "VO2",
    ]
}


def test_substrate_match():
    doc = SubstrateMatch.from_structure(
        film=DEFAULT_SUBSTRATES[0],
        substrate=DEFAULT_SUBSTRATES[1],
        substrate_id="mp-23",
    )

    assert doc is not None


@pytest.mark.parametrize("structure", test_structures.values())
def test_substrate_doc(structure):
    test_substrates = DEFAULT_SUBSTRATES[0:2]
    doc = SubstratesDoc.from_structure(
        material_id="mp-33", structure=structure, substrates=test_substrates
    )
    assert doc is not None
    assert doc.material_id == "mp-33"
    assert len(doc.substrates) > 0
