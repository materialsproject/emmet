from emmet.api.routes.materials.surface_properties.query_operators import (
    ReconstructedQuery,
)


def test_reconstructed_operator():
    op = ReconstructedQuery()

    assert op.query(has_reconstructed=True) == {"criteria": {"has_reconstructed": True}}
