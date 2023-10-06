import pytest
from emmet.core.robocrys import RobocrystallogapherDoc
from pymatgen.core import Structure

from . import test_structures


@pytest.mark.parametrize("structure", test_structures.values())
def test_robocrys(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = RobocrystallogapherDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )
    assert doc is not None
