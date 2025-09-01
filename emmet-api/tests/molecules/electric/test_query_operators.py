import pytest

from emmet.api.routes.molecules.electric.query_operators import (
    MultipoleMomentComponentQuery,
)
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(
    reason="Query operator serialization with monty not compatible with new implementation"
)
def test_multipole_moment_query():
    op = MultipoleMomentComponentQuery()
    assert op.query(
        moment_type="dipole",
        component="X",
        component_value_min=0.1,
        component_value_max=3.1,
    ) == {
        "criteria": {
            "dipole_moment.0": {"$lte": 3.1, "$gte": 0.1},
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            moment_type="octopole",
            component="ZZZ",
            component_value_min=-100.00,
            component_value_max=100.00,
        ) == {
            "criteria": {
                "octopole_moment.ZZZ": {"$lte": 100.00, "$gte": -100.00},
            }
        }

    assert op.query(moment_type="hexadecapole", component="YYYY") == {
        "criteria": {
            "hexadecapole_moment.YYYY": {"$exists": True},
        }
    }

    with pytest.raises(ValueError):
        op.query(moment_type="resp_dipole", component="flapper")
