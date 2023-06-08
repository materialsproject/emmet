from __future__ import annotations

from emmet.api.routes.materials.thermo.query_operators import IsStableQuery
from monty.serialization import dumpfn, loadfn
from monty.tempfile import ScratchDir


def test_is_stable_operator():
    op = IsStableQuery()

    assert op.query(is_stable=True) == {"criteria": {"is_stable": True}}

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(is_stable=True) == {"criteria": {"is_stable": True}}
