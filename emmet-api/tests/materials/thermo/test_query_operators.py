from emmet.api.routes.materials.thermo.query_operators import IsStableQuery


def test_is_stable_operator():
    op = IsStableQuery()

    assert op.query(is_stable=True) == {"criteria": {"is_stable": True}}
