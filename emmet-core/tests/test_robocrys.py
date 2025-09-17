import pytest
from pymatgen.core import Structure
from robocrys import __version__ as __robocrys_version__

from . import test_structures
from emmet.core import ARROW_COMPATIBLE
from emmet.core.robocrys import RobocrystallogapherDoc

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


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


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow():
    structure = next(iter(test_structures.values()))
    doc = RobocrystallogapherDoc.from_structure(
        structure=structure,
        material_id=33,
        deprecated=False,
        robocrys_version=__robocrys_version__,
    )
    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}),
        type=arrowize(RobocrystallogapherDoc),
    )
    test_arrow_doc = RobocrystallogapherDoc(
        **arrow_struct.as_py(maps_as_pydicts="strict")
    )

    assert doc.model_dump() == test_arrow_doc.model_dump()
