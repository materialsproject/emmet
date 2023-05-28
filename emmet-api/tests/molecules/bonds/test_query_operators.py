from emmet.api.routes.molecules.bonds.query_operators import BondTypeLengthQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_bond_type_length_query():
    op = BondTypeLengthQuery()
    assert op.query(bond_type="C-O", max_bond_length=1.7, min_bond_length=1.4) == {
        "criteria": {"bond_types.C-O": {"$lte": 1.7, "$gte": 1.4}}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            bond_type="C-O", max_bond_length=1.7, min_bond_length=1.4
        ) == {"criteria": {"bond_types.C-O": {"$lte": 1.7, "$gte": 1.4}}}
