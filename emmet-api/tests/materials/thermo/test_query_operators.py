import pytest

from emmet.api.routes.materials.thermo.query_operators import IsStableQuery

from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(
    reason="Query operator serialization with monty not compatible with new implementation"
)
def test_is_stable_operator():
    op = IsStableQuery()

    assert op.query(is_stable=True) == {"criteria": {"is_stable": True}}

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(is_stable=True) == {"criteria": {"is_stable": True}}
