from __future__ import annotations

from emmet.api.routes.materials.oxidation_states.query_operators import (
    PossibleOxiStateQuery,
)
from monty.serialization import dumpfn, loadfn
from monty.tempfile import ScratchDir


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
