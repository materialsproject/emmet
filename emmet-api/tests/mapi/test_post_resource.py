from datetime import datetime
from random import randint

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.resource import PostOnlyResource
from maggma.stores import MemoryStore


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(None, title="Owne'r Age")
    weight: float = Field(None, title="Owner's weight")
    last_updated: datetime = Field(None, title="Last updated date for this record")


owners = (
    [Owner(name=f"Person{i}", age=i + 3, weight=100 + i) for i in list(range(10))]
    + [Owner(name="PersonAge9", age=9, weight=float(randint(155, 195)))]
    + [Owner(name="PersonWeight150", age=randint(10, 15), weight=float(150))]
    + [Owner(name="PersonAge20Weight200", age=20, weight=float(200))]
)

total_owners = len(owners)


@pytest.fixture()
def owner_store():
    store = MemoryStore("owners", key="name")
    store.connect()
    store.update([d.dict() for d in owners])
    return store


def test_init(owner_store):
    resource = PostOnlyResource(collection=owner_store, model=Owner)
    assert len(resource.router.routes) == 2


def test_msonable(owner_store):
    owner_resource = PostOnlyResource(collection=owner_store, model=Owner)
    endpoint_dict = owner_resource.as_dict()

    for k in ["@class", "@module", "store", "model"]:
        assert k in endpoint_dict

    assert isinstance(endpoint_dict["model"], str)
    assert endpoint_dict["model"] == "test_post_resource.Owner"


def test_post_to_search(owner_store):
    endpoint = PostOnlyResource(owner_store, Owner)
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.post("/").status_code == 200


@pytest.mark.xfail()
def test_problem_query_params(owner_store):
    endpoint = PostOnlyResource(owner_store, Owner)
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    client.get("/?param=test").status_code
