import pytest

from emmet.api.routes.molecules.electric.query_operators import MultipoleMomentComponentQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_multipole_moment_query():
    op = MultipoleMomentComponentQuery()
    assert op.query(
        moment_type="dipole",
        component="X",
        min_component_value=0.1,
        max_component_value=3.1,
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
            min_component_value=-100.00,
            max_component_value=100.00,
        ) == {
            "criteria": {
                "octopole_moment.ZZZ": {"$lte": 100.00, "$gte": -100.00},
            }
        }

    assert op.query(
        moment_type="hexadecapole",
        component="YYYY"
    ) == {
        "criteria": {
            "hexadecapole_moment.YYYY": {"$exists": True},
        }
    }

    with pytest.raises(ValueError):
        op.query(moment_type="resp_dipole", component="flapper")