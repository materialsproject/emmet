import pytest

from emmet.api.routes.molecules.electric.query_operators import (
    MultipoleMomentComponentQuery,
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

    assert op.query(moment_type="hexadecapole", component="YYYY") == {
        "criteria": {
            "hexadecapole_moment.YYYY": {"$exists": True},
        }
    }

    with pytest.raises(ValueError):
        op.query(moment_type="resp_dipole", component="flapper")
