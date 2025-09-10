from emmet.api.routes.materials.piezo.query_operators import PiezoelectricQuery


def test_piezo_query():
    op = PiezoelectricQuery()

    assert op.query(piezo_modulus_min=0, piezo_modulus_max=5) == {
        "criteria": {"e_ij_max": {"$gte": 0, "$lte": 5}}
    }
