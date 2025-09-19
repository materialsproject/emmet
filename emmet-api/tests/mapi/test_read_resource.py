import inspect
from datetime import datetime
from random import randint
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from requests import Response
from starlette.testclient import TestClient

from emmet.api.query_operator import (
    NumericQuery,
    SparseFieldsQuery,
    StringQueryOperator,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.resource.core import HeaderProcessor, HintScheme
from emmet.api.resource.utils import CollectionWithKey


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(None, title="Owner's Age")
    weight: float = Field(None, title="Owner's weight")
    last_updated: datetime = Field(None, title="Last updated date for this record")


owners = (
    [Owner(name=f"Person{i}", age=i + 3, weight=100 + i) for i in list(range(10))]
    + [Owner(name="PersonAge9", age=9, weight=float(randint(155, 195)))]
    + [Owner(name="PersonWeight150", age=randint(10, 15), weight=float(150))]
    + [Owner(name="PersonAge20Weight200", age=20, weight=float(200))]
)

total_owners = len(owners)


# Create a subclass of the header processor to prevent TypeErrors:
#  Can't instantiate abstract class HeaderProcessor with abstract methods
class TestHeaderProcessor(HeaderProcessor):
    def configure_query_on_request(self, request, query_operator):
        # Implement the method
        return {"name": "PersonAge9"}

    def process_header(self, response, request):
        # Implement the method
        pass


@pytest_asyncio.fixture
async def owner_collection(mock_database):
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)
    return CollectionWithKey(collection=collection, key="name")


@pytest.mark.asyncio
async def test_init(owner_collection):
    resource = ReadOnlyResource(store=owner_collection, model=Owner)
    assert len(resource.router.routes) == 2

    resource = ReadOnlyResource(
        store=owner_collection,
        model=Owner,
        enable_default_search=False,
    )
    assert len(resource.router.routes) == 1


@pytest.mark.xfail()
@pytest.mark.asyncio
async def test_problem_query_params(owner_collection):
    endpoint = ReadOnlyResource(owner_collection, Owner)
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    client.get("/?param=test").status_code


@pytest.mark.xfail()
@pytest.mark.asyncio
async def test_problem_hint_scheme(owner_collection):
    class TestHintScheme(HintScheme):
        def generate_hints(query):
            return {"hint": "test"}

    # Note: This test may need adjustment as AliasingStore equivalent
    # might not be available with async mongomock
    ReadOnlyResource(owner_collection, Owner, hint_scheme=TestHintScheme())


async def search_helper(
    payload, base: str = "/?", debug=True, mock_database=None
) -> tuple[Response, list]:
    """
    Helper function to directly query search endpoints.

    Args:
        base: base of the query, default to /query?
        payload: query in dictionary format
        debug: True = print out the url, false don't print anything
        mock_database: async mock database

    Returns:
        tuple of (request.Response object, data list)
    """
    collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)

    collection_with_key = CollectionWithKey(collection=collection, key="name")

    endpoint = ReadOnlyResource(
        collection_with_key,
        Owner,
        query_operators=[
            StringQueryOperator(model=Owner),
            NumericQuery(model=Owner),
            SparseFieldsQuery(model=Owner),
        ],
        header_processor=TestHeaderProcessor(),
        query_to_configure_on_request=StringQueryOperator(model=Owner),
        disable_validation=True,
    )
    app = FastAPI()
    app.include_router(endpoint.router)

    client = TestClient(app)

    print(inspect.signature(NumericQuery(model=Owner).query))

    url = base + urlencode(payload)
    if debug:
        print(url)
    res = client.get(url)
    json = res.json()
    return res, json.get("data", [])


@pytest.mark.asyncio
async def test_numeric_query_operator(mock_database):
    # Checking int
    payload = {"age": 20, "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["age"] == 20

    # Clear collection between tests
    await mock_database["owners"].drop()

    payload = {"age_not_eq": 9, "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 11

    await mock_database["owners"].drop()

    payload = {"age_max": 9}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 8

    await mock_database["owners"].drop()

    payload = {"age_min": 0}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 13


@pytest.mark.asyncio
async def test_string_query_operator(mock_database):
    payload = {"name": "PersonAge9", "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "PersonAge9"

    await mock_database["owners"].drop()

    payload = {"name_not_eq": "PersonAge9", "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 12


@pytest.mark.asyncio
async def test_resource_compound(mock_database):
    payload = {
        "name": "PersonAge20Weight200",
        "_all_fields": True,
        "weight_min": 199.1,
        "weight_max": 201.4,
        "age": 20,
    }
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "PersonAge20Weight200"

    await mock_database["owners"].drop()

    payload = {
        "name": "PersonAge20Weight200",
        "_all_fields": False,
        "_fields": "name,age",
        "weight_min": 199.3,
        "weight_max": 201.9,
        "age": 20,
    }
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "PersonAge20Weight200"
    assert "weight" not in data[0]


@pytest.mark.asyncio
async def test_configure_query_on_request(mock_database):
    payload = {
        "name": "PersonAge20Weight200",
        "_all_fields": False,
        "_fields": "name,age",
        "weight_min": 199.3,
        "weight_max": 201.9,
        "age": 20,
    }
    res, data = await search_helper(
        payload=payload, base="/?", debug=True, mock_database=mock_database
    )
    assert res.status_code == 200
