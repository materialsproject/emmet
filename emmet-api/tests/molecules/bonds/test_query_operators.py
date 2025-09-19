from emmet.api.routes.molecules.bonds.query_operators import BondTypeLengthQuery


def test_bond_type_length_query():
    op = BondTypeLengthQuery()
    assert op.query(bond_type="C-O", bond_length_max=1.7, bond_length_min=1.4) == {
        "criteria": {"bond_types.C-O": {"$lte": 1.7, "$gte": 1.4}}
    }
