import pytest

from emmet.api.routes.materials.surface_properties.query_operators import (
    ReconstructedQuery,
)


from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(
    reason="Query operator serialization with monty not compatible with new implementation"
)
def test_reconstructed_operator():
    op = ReconstructedQuery()

    assert op.query(has_reconstructed=True) == {"criteria": {"has_reconstructed": True}}

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(has_reconstructed=True) == {
            "criteria": {"has_reconstructed": True}
        }
