from emmet.api.routes.materials.oxidation_states.query_operators import (
    PossibleOxiStateQuery,
)


def test_possible_oxi_state_query():
    op = PossibleOxiStateQuery()

    assert op.query(possible_species="Cr2+, O2-") == {
        "criteria": {"possible_species": {"$all": ["Cr2+", "O2-"]}}
    }
