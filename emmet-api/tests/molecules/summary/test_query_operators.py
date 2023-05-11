from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn

from emmet.api.routes.molecules.summary.query_operators import MPculeIDsSearchQuery


def test_mpcules_ids_query():
    op = MPculeIDsSearchQuery()

    query = {
        "criteria": {
            "molecule_id": {
                "$in": [
                    "33fb88e526387337e0da25143057bb88-C2F4-1-2",
                    "d24850a2bbca341571cf57d3e2025837-C4H2-m2-3",
                ]
            }
        }
    }

    assert (
        op.query(
            molecule_ids="33fb88e526387337e0da25143057bb88-C2F4-1-2, d24850a2bbca341571cf57d3e2025837-C4H2-m2-3"
        )
        == query
    )

    docs = [
        {"molecule_id": "33fb88e526387337e0da25143057bb88-C2F4-1-2"},
        {"molecule_id": "d24850a2bbca341571cf57d3e2025837-C4H2-m2-3"},
    ]

    assert op.post_process(docs, {**query, "properties": ["molecule_id"]})[0] == docs[0]

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert (
            new_op.query(
                molecule_ids="33fb88e526387337e0da25143057bb88-C2F4-1-2, d24850a2bbca341571cf57d3e2025837-C4H2-m2-3"
            )
            == query
        )
