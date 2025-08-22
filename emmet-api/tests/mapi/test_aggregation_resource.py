from datetime import datetime
from random import randint

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

from emmet.api.query_operator.core import QueryOperator
from emmet.api.resource import AggregationResource
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
def pipeline_query_op():
    class PipelineQuery(QueryOperator):
        def query(self):
            pipeline = [
                {"$match": {"name": "PersonAge9"}},
                {"$project": {"age": 1}},
            ]
            return {"pipeline": pipeline}

    return PipelineQuery()


def test_init(owner_store, pipeline_query_op):
    resource = AggregationResource(
        collection=owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    assert len(resource.router.routes) == 2


def test_msonable(owner_store, pipeline_query_op):
    owner_resource = AggregationResource(
        collection=owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    endpoint_dict = owner_resource.as_dict()

    for k in ["@class", "@module", "store", "model"]:
        assert k in endpoint_dict

    assert isinstance(endpoint_dict["model"], str)
    assert endpoint_dict["model"] == "test_aggregation_resource.Owner"


def test_aggregation_search(owner_store, pipeline_query_op):
    endpoint = AggregationResource(
        owner_store, pipeline_query_operator=pipeline_query_op, model=Owner
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    assert client.get("/").status_code == 200
