from emmet.api.routes._consumer.query_operator import (
    UserSettingsGetQuery,
    UserSettingsPostQuery,
)


def test_user_settings_post_query():
    op = UserSettingsPostQuery()
    q = {
        "criteria": {
            "consumer_id": "test",
            "settings": {"test": "test", "test2": 10},
        }
    }

    assert op.query(consumer_id="test", settings={"test": "test", "test2": 10}) == q

    docs = [{"consumer_id": "test", "settings": {"test": "test", "test2": 10}}]
    assert op.post_process(docs, q) == docs


def test_user_settings_get_query():
    op = UserSettingsGetQuery()

    assert op.query(consumer_id="test") == {"criteria": {"consumer_id": "test"}}
