import pytest

from emmet.api.routes.molecules.redox.query_operators import RedoxPotentialQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(
    reason="Query operator serialization with monty not compatible with new implementation"
)
def test_redox_potential_query():
    op = RedoxPotentialQuery()
    assert op.query(
        reduction_potential_min=0.0,
        reduction_potential_max=0.8,
        oxidation_potential_min=4.0,
        oxidation_potential_max=6.0,
    ) == {
        "criteria": {
            "oxidation_potential": {"$gte": 4.0, "$lte": 6.0},
            "reduction_potential": {"$gte": 0.0, "$lte": 0.8},
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            reduction_potential_min=0.0,
            reduction_potential_max=0.8,
            oxidation_potential_min=4.0,
            oxidation_potential_max=6.0,
        ) == {
            "criteria": {
                "oxidation_potential": {"$gte": 4.0, "$lte": 6.0},
                "reduction_potential": {"$gte": 0.0, "$lte": 0.8},
            }
        }
