import json
from datetime import datetime
from random import randint

import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.query_operator import PaginationQuery
from emmet.api.query_operator.core import QueryOperator
from emmet.api.resource import SubmissionResource
from emmet.api.resource.utils import CollectionWithKey


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(None, title="Owner's Age")
    weight: float = Field(None, title="Owner's weight")
    last_updated: datetime | None = Field(
        None, title="Last updated date for this record"
    )


owners = (
    [Owner(name=f"Person{i}", age=i + 3, weight=100 + i) for i in list(range(10))]
    + [Owner(name="PersonAge9", age=9, weight=float(randint(155, 195)))]
    + [Owner(name="PersonWeight150", age=randint(10, 15), weight=float(150))]
    + [Owner(name="PersonAge20Weight200", age=20, weight=float(200))]
)

total_owners = len(owners)


@pytest_asyncio.fixture
async def owner_collection(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    return CollectionWithKey(collection=collection, key="name")


@pytest_asyncio.fixture
async def post_query_op():
    class PostQuery(QueryOperator):
        def query(self, name):
            return {"criteria": {"name": name}}

    return PostQuery()


@pytest_asyncio.fixture
async def patch_query_op():
    class PatchQuery(QueryOperator):
        def query(self, name, update):
            # Parse the JSON string to a dictionary
            update_dict = json.loads(update) if isinstance(update, str) else update
            return {"criteria": {"name": name}, "update": update_dict}

    return PatchQuery()


@pytest.mark.asyncio
async def test_init(owner_collection, post_query_op, patch_query_op):
    resource = SubmissionResource(
        store=owner_collection,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        patch_query_operators=[patch_query_op],
        model=Owner,
    )
    assert len(resource.router.routes) == 5


@pytest.mark.asyncio
async def test_submission_search(owner_collection, post_query_op):
    endpoint = SubmissionResource(
        owner_collection,
        Owner,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=False,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.post("/?name=test_name").status_code == 200


@pytest.mark.asyncio
async def test_submission_patch(owner_collection, post_query_op, patch_query_op):
    endpoint = SubmissionResource(
        owner_collection,
        Owner,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        patch_query_operators=[patch_query_op],
        calculate_submission_id=False,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)
    update = json.dumps({"last_updated": "2023-06-22T17:32:11.645713"})

    assert client.get("/").status_code == 200
    assert client.patch(f"/?name=PersonAge9&update={update}").status_code == 200


@pytest.mark.asyncio
async def test_key_fields(owner_collection, post_query_op):
    endpoint = SubmissionResource(
        owner_collection,
        Owner,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=False,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/Person1/").status_code == 200
    assert client.get("/Person1/").json()["data"][0]["name"] == "Person1"


@pytest.mark.asyncio
async def test_patch_submission(owner_collection, post_query_op):
    endpoint = SubmissionResource(
        owner_collection,
        Owner,
        get_query_operators=[PaginationQuery()],
        post_query_operators=[post_query_op],
        calculate_submission_id=False,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/Person1/").status_code == 200
    assert client.get("/Person1/").json()["data"][0]["name"] == "Person1"
