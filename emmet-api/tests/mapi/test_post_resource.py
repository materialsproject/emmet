from datetime import datetime
from random import randint

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.resource import PostOnlyResource
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


@pytest.mark.asyncio
async def test_init(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    resource = PostOnlyResource(store=owner_store, model=Owner)
    assert len(resource.router.routes) == 2


@pytest.mark.asyncio
async def test_msonable(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    owner_resource = PostOnlyResource(store=owner_store, model=Owner)

    # Test that the resource has the expected attributes
    assert hasattr(owner_resource, "model")
    assert hasattr(owner_resource, "collection")
    assert owner_resource.model == Owner


@pytest.mark.asyncio
async def test_post_to_search(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    endpoint = PostOnlyResource(owner_store, Owner)
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.post("/").status_code == 200


@pytest.mark.xfail()
@pytest.mark.asyncio
async def test_problem_query_params(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    endpoint = PostOnlyResource(owner_store, Owner)
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    client.get("/?param=test").status_code
