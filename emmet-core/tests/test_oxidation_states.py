import pytest
from emmet.core.oxidation_states import OxidationStateDoc, OxiStateAssigner
from pymatgen.core import Structure

from . import test_structures


@pytest.mark.parametrize("structure", test_structures.values())
def test_oxidation_state(structure: Structure):
    """Very simple test to make sure this actually works"""
    struct_has_charges_assigned = (
        structure.composition.copy().remove_charges() != structure.composition
    )

    for method in (
        None,
        "bva",
    ):

        doc = OxidationStateDoc.from_structure(
            structure, material_id=33, deprecated=False
        )
        assert doc is not None
        assert doc.structure is not None

        if struct_has_charges_assigned and not method:
            assert doc.method == OxiStateAssigner.MANUAL
        elif doc.possible_valences:
            assert doc.method in {OxiStateAssigner.BVA, OxiStateAssigner.GUESS}
        else:
            assert doc.method is None
