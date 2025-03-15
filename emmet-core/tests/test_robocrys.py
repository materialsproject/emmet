import pytest
from pymatgen.core import Structure
from robocrys import __version__ as __robocrys_version__

from . import test_structures
from emmet.core.arrow import cleanup_msonables
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


def test_robocrys_arrow_round_trip_serialization():
    structure = next(iter(test_structures.values()))
    doc = RobocrystallogapherDoc.from_structure(
        structure=structure,
        material_id=33,
        deprecated=False,
        robocrys_version=__robocrys_version__,
    )
    arrow_struct = doc.model_dump(context={"format": "arrow"})
    test_arrow_doc = RobocrystallogapherDoc.from_arrow(arrow_struct)

    assert cleanup_msonables(doc.model_dump()) == cleanup_msonables(
        test_arrow_doc.model_dump()
    )
