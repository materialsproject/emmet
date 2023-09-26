import pytest
from emmet.core.oxidation_states import OxidationStateDoc
from pymatgen.core import Structure

from . import test_structures


@pytest.mark.parametrize("structure", test_structures.values())
def test_oxidation_state(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = OxidationStateDoc.from_structure(structure, material_id=33, deprecated=False)
    assert doc is not None
    assert doc.structure is not None
