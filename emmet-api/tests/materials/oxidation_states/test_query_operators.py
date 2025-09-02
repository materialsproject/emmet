import pytest

from emmet.api.routes.materials.oxidation_states.query_operators import (
    PossibleOxiStateQuery,
)

from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(
    reason="Query operator serialization with monty not compatible with new implementation"
)
def test_possible_oxi_state_query():
    op = PossibleOxiStateQuery()

    assert op.query(possible_species="Cr2+, O2-") == {
        "criteria": {"possible_species": {"$all": ["Cr2+", "O2-"]}}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        loadfn("temp.json")

        assert op.query(possible_species="Cr2+, O2-") == {
            "criteria": {"possible_species": {"$all": ["Cr2+", "O2-"]}}
        }
