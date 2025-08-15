import json
from datetime import datetime
from random import randint

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.query_operator import PaginationQuery
from emmet.api.query_operator.core import QueryOperator
from emmet.api.resource import SubmissionResource
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


@pytest.fixture()
def post_query_op():
    class PostQuery(QueryOperator):
        def query(self, name):
            return {"criteria": {"name": name}}

    return PostQuery()


@pytest.fixture()
def patch_query_op():
    class PatchQuery(QueryOperator):
        def query(self, name, update):
            return {"criteria": {"name": name}, "update": update}

    return PatchQuery()


def test_init(owner_store, post_query_op, patch_query_op):
    resource = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        patch_query_operators=[patch_query_op],
        model=Owner,
    )
    assert len(resource.router.routes) == 5


def test_msonable(owner_store, post_query_op):
    owner_resource = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        model=Owner,
    )
    endpoint_dict = owner_resource.as_dict()

    for k in ["@class", "@module", "store", "model"]:
        assert k in endpoint_dict

    assert isinstance(endpoint_dict["model"], str)
    assert endpoint_dict["model"] == "test_submission_resource.Owner"


def test_submission_search(owner_store, post_query_op):
    endpoint = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=True,
        model=Owner,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.post("/?name=test_name").status_code == 200


def test_submission_patch(owner_store, post_query_op, patch_query_op):
    endpoint = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        patch_query_operators=[patch_query_op],
        calculate_submission_id=True,
        model=Owner,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)
    update = json.dumps({"last_updated": "2023-06-22T17:32:11.645713"})

    assert client.get("/").status_code == 200
    assert client.patch(f"/?name=PersonAge9&update={update}").status_code == 200


def test_key_fields(owner_store, post_query_op):
    endpoint = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=False,
        model=Owner,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/Person1/").status_code == 200
    assert client.get("/Person1/").json()["data"][0]["name"] == "Person1"


def test_patch_submission(owner_store, post_query_op):
    endpoint = SubmissionResource(
        store=owner_store,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=False,
        model=Owner,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/Person1/").status_code == 200
    assert client.get("/Person1/").json()["data"][0]["name"] == "Person1"
