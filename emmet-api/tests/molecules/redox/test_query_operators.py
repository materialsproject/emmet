from emmet.api.routes.molecules.redox.query_operators import RedoxPotentialQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_redox_potential_query():
    op = RedoxPotentialQuery()
    assert op.query(
        min_reduction_potential=0.0,
        max_reduction_potential=0.8,
        min_oxidation_potential=4.0,
        max_oxidation_potential=6.0,
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
            min_reduction_potential=0.0,
            max_reduction_potential=0.8,
            min_oxidation_potential=4.0,
            max_oxidation_potential=6.0,
        ) == {
            "criteria": {
                "oxidation_potential": {"$gte": 4.0, "$lte": 6.0},
                "reduction_potential": {"$gte": 0.0, "$lte": 0.8},
            }
        }
