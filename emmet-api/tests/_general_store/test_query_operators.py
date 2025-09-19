from emmet.api.routes._general_store.query_operator import (
    GeneralStoreGetQuery,
    GeneralStorePostQuery,
)


def test_user_settings_post_query():
    op = GeneralStorePostQuery()
    q = {
        "criteria": {
            "kind": "test",
            "meta": {"test": "test", "test2": 10},
            "markdown": "test",
        }
    }

    assert (
        op.query(kind="test", meta={"test": "test", "test2": 10}, markdown="test") == q
    )

    docs = [{"kind": "test", "meta": {"test": "test", "test2": 10}, "markdown": "test"}]
    assert op.post_process(docs, q) == docs


def test_user_settings_get_query():
    op = GeneralStoreGetQuery()

    assert op.query(kind="test") == {"criteria": {"kind": "test"}}
