import pytest
from pymatgen.core import Structure

from . import test_structures
from emmet.core import ARROW_COMPATIBLE
from emmet.core.chemenv import ChemEnvDoc

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.mark.parametrize("structure", test_structures.values())
def test_chemenv(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = ChemEnvDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )
    valences = [getattr(site.specie, "oxi_state", None) for site in structure]
    valences = [v for v in valences if v is not None]
    if len(valences) == len(structure):
        assert doc.model_dump()["warnings"] is None
    # elif structure.composition.almost_equals(Composition("CsCl")):
    #    # We do not have reference polyhedra above a certain number of neighbors.
    #    # ChemEnv cannot deliver an answer without oxidation states.
    #    assert doc.model_dump()["warnings"] == "ChemEnv algorithm failed."
    else:
        assert (
            doc.model_dump()["warnings"]
            == "No oxidation states available. Cation-anion bonds cannot be identified."
        )


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(
    structure=next(iter(test_structures.values())),
):
    doc = ChemEnvDoc.from_structure(
        structure=structure, material_id=33, deprecated=False
    )

    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}), type=arrowize(ChemEnvDoc)
    )
    test_arrow_doc = ChemEnvDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert doc == test_arrow_doc
