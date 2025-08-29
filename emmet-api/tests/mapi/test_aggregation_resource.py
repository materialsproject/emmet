from datetime import datetime
from random import randint

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.query_operator.core import QueryOperator
from emmet.api.resource import AggregationResource
from emmet.api.resource.utils import CollectionWithKey


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


@pytest.fixture
def pipeline_query_op():
    class PipelineQuery(QueryOperator):
        def query(self):
            pipeline = [
                {"$match": {"name": "PersonAge9"}},
                {"$project": {"age": 1}},
            ]
            return {"pipeline": pipeline}

    return PipelineQuery()


@pytest.mark.asyncio
async def test_init(mock_database, pipeline_query_op):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    resource = AggregationResource(
        store=owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    assert len(resource.router.routes) == 2


@pytest.mark.asyncio
async def test_msonable(mock_database, pipeline_query_op):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    owner_resource = AggregationResource(
        store=owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    # Test that the resource has the expected attributes
    assert hasattr(owner_resource, "model")
    assert hasattr(owner_resource, "collection")
    assert hasattr(owner_resource, "pipeline_query_operator")
    assert owner_resource.model == Owner


@pytest.mark.asyncio
async def test_aggregation_search(mock_database, pipeline_query_op):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    owner_store = CollectionWithKey(collection=collection, key="name")

    endpoint = AggregationResource(
        owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/").status_code == 200
