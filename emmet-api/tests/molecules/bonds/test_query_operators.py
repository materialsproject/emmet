import pytest

from emmet.api.routes.molecules.bonds.query_operators import BondTypeLengthQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(reason="Query operator serialization with monty not compatible with new implementation")
def test_bond_type_length_query():
    op = BondTypeLengthQuery()
    assert op.query(bond_type="C-O", bond_length_max=1.7, bond_length_min=1.4) == {
        "criteria": {"bond_types.C-O": {"$lte": 1.7, "$gte": 1.4}}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            bond_type="C-O", bond_length_max=1.7, bond_length_min=1.4
        ) == {"criteria": {"bond_types.C-O": {"$lte": 1.7, "$gte": 1.4}}}
