import pytest

from emmet.api.resource import S3URLResource
from maggma.stores import MemoryStore


@pytest.fixture()
def entries_store():
    store = MemoryStore("entries", key="url")
    store.connect()
    return store


def test_init(entries_store):
    resource = S3URLResource(store=entries_store, url_lifetime=500)
    assert len(resource.router.routes) == 2


def test_msonable(entries_store):
    resource = S3URLResource(store=entries_store, url_lifetime=500)
    endpoint_dict = resource.as_dict()

    for k in ["@class", "@module", "store", "model"]:
        assert k in endpoint_dict

    assert isinstance(endpoint_dict["model"], str)
    assert endpoint_dict["model"] == "emmet.api.models.S3URLDoc"
