from emmet.api.routes.materials.chemenv.query_operators import ChemEnvQuery


def test_bond_length_query_operator():
    op = ChemEnvQuery()

    q = op.query(
        chemenv_iucr="[6o],[4n]",
        chemenv_iupac="SP-4, IC-12",
        chemenv_name="Square non-coplanar, Icosahedron",
        chemenv_symbol="SS:4, PP:5",
        species="Ti4+",
        csm_min=0.5,
        csm_max=1.5,
    )

    assert q == {
        "criteria": {
            "csm": {"$gte": 0.5, "$lte": 1.5},
            "chemenv_iucr": {"$in": ["[6o]", "[4n]"]},
            "chemenv_iupac": {"$in": ["SP-4", "IC-12"]},
            "chemenv_name": {"$in": ["Square non-coplanar", "Icosahedron"]},
            "chemenv_symbol": {"$in": ["SS:4", "PP:5"]},
            "species": {"$in": ["Ti4+"]},
        }
    }
