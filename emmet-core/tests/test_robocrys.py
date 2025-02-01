import pyarrow as pa
import pytest
from pymatgen.core import Structure
from robocrys import __version__ as __robocrys_version__

from . import test_structures
from emmet.core.robocrys import RobocrystallogapherDoc
from emmet.core.utils import jsanitize


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

    sanitized_doc = jsanitize(doc.model_dump(), allow_bson=True)
    test_arrow_doc = RobocrystallogapherDoc(
        **pa.array([sanitized_doc], type=RobocrystallogapherDoc.as_arrow())
        .to_pandas(maps_as_pydicts="strict")
        .iloc[0]
    )

    assert doc == test_arrow_doc
