from datetime import datetime

import pytest
from pymatgen.core.structure import Structure
from pymatgen.util.testing import PymatgenTest

try:
    from emmet.core.optimade import OptimadeMaterialsDoc
except Exception:
    pytest.skip(
        "could not import 'optimade': No module named 'optimade'",
        allow_module_level=True,
    )

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


@pytest.mark.xfail(reason="Optimade + fastapi issues.")
@pytest.mark.parametrize("structure", test_structures.values())
def test_oxidation_state(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = OptimadeMaterialsDoc.from_structure(
        structure, material_id=33, last_updated=datetime.utcnow()
    )
    assert doc is not None
