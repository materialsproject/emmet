import pytest

from emmet.api.routes.materials.robocrys.query_operators import RoboTextSearchQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


@pytest.mark.skip(reason="Query operator serialization with monty not compatible with new implementation")
def test_robocrys_search_query():
    op = RoboTextSearchQuery()

    pipeline = [
        {
            "$search": {
                "index": "description",
                "regex": {
                    "query": ["cubic", "octahedra"],
                    "path": "description",
                    "allowAnalyzedField": True,
                },
                "sort": {"score": {"$meta": "searchScore"}, "description": 1},
                "count": {"type": "total"},
            }
        },
        {"$skip": 0},
        {"$limit": 10},
        {
            "$project": {
                "_id": 0,
                "meta": "$$SEARCH_META",
                "material_id": 1,
                "description": 1,
                "condensed_structure": 1,
                "last_updated": 1,
            }
        },
    ]

    assert op.query(keywords="cubic, octahedra", _skip=0, _limit=10) == {
        "pipeline": pipeline
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        query = {"pipeline": pipeline}
        assert new_op.query(keywords="cubic, octahedra", _skip=0, _limit=10) == query

    doc = [{"meta": {"count": {"total": 10}}}]
    assert op.post_process(doc, query) == doc
    assert op.meta() == {"total_doc": 10}
