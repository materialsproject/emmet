from datetime import datetime

import pytest
from pymatgen.core.structure import Structure

from . import test_structures

try:
    from emmet.core.optimade import OptimadeMaterialsDoc
except Exception:
    pytest.skip("could not import 'optimade' ", allow_module_level=True)


@pytest.mark.xfail(reason="Optimade + fastapi issues.")
@pytest.mark.parametrize("structure", test_structures.values())
def test_oxidation_state(structure: Structure):
    """Very simple test to make sure this actually works"""
    print(f"Should work : {structure.composition}")
    doc = OptimadeMaterialsDoc.from_structure(
        structure, material_id=33, last_updated=datetime.utcnow()
    )
    assert doc is not None
