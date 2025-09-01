from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn
import pytest

from emmet.api.routes._general_store.query_operator import (
    GeneralStoreGetQuery,
    GeneralStorePostQuery,
)

@pytest.mark.skip(reason="Serialization test skipped in maggma-free implementation")
def test_user_settings_post_query():
    op = GeneralStorePostQuery()

    assert op.query(
        kind="test", meta={"test": "test", "test2": 10}, markdown="test"
    ) == {
        "criteria": {
            "kind": "test",
            "meta": {"test": "test", "test2": 10},
            "markdown": "test",
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        query = {
            "criteria": {
                "kind": "test",
                "meta": {"test": "test", "test2": 10},
                "markdown": "test",
            }
        }
        assert (
            new_op.query(
                kind="test", meta={"test": "test", "test2": 10}, markdown="test"
            )
            == query
        )

    docs = [{"kind": "test", "meta": {"test": "test", "test2": 10}, "markdown": "test"}]
    assert op.post_process(docs, query) == docs


@pytest.mark.skip(reason="Serialization test skipped in maggma-free implementation")
def test_user_settings_get_query():
    op = GeneralStoreGetQuery()

    assert op.query(kind="test") == {"criteria": {"kind": "test"}}

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(kind="test") == {"criteria": {"kind": "test"}}
