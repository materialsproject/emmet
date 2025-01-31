import pytest
from pymatgen.core import Structure
from robocrys import __version__ as __robocrys_version__

from . import test_structures
from emmet.core.robocrys import RobocrystallogapherDoc


@pytest.mark.parametrize("structure", test_structures.values())
def test_robocrys(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = RobocrystallogapherDoc.from_structure(
        structure=structure,
        material_id=33,
        deprecated=False,
        robocrys_version=__robocrys_version__,
    )
    assert doc is not None
