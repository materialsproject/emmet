import json
from enum import Enum
from random import choice, randint
from typing import Any
from urllib.parse import urlencode

import pytest
from pydantic import BaseModel, Field
from requests import Response
from starlette.testclient import TestClient

from emmet.api.API import API
from emmet.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SparseFieldsQuery,
    StringQueryOperator,
)
from emmet.api.resource import ReadOnlyResource
from emmet.api.resource.utils import CollectionWithKey


class PetType(str, Enum):
    cat = "cat"
    dog = "dog"


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(..., title="Owne'r Age")
    weight: int = Field(..., title="Owner's weight")


class Pet(BaseModel):
    name: str = Field(..., title="Pet's Name")
    pet_type: PetType = Field(..., title="Pet Type")
    owner_name: str = Field(..., title="Owner's name")


owners = [
    Owner(name=f"Person{i}", age=randint(10, 100), weight=randint(100, 200))
    for i in list(range(10))
]


pets = [
    Pet(
        name=f"Pet{i}",
        pet_type=choice(list(PetType)),
        owner_name=choice(owners).name,
    )
    for i in list(range(40))
]


async def search_helper(
    payload, base: str = "/?", debug=True, mock_database=None
) -> tuple[Response, Any]:
    """
    Helper function to directly query search endpoints

    Args:
        base: base of the query, default to /query?
        payload: query in dictionary format
        debug: True = print out the url, false don't print anything
        mock_database: async mock database

    Returns:
        request.Response object that contains the response of the corresponding payload
    """
    owner_collection = mock_database["owners"]
    owner_docs = [owner.model_dump() for owner in owners]
    await owner_collection.insert_many(owner_docs)
    owner_collection_with_key = CollectionWithKey(
        collection=owner_collection, key="name"
    )

    pets_collection = mock_database["pets"]
    pet_docs = [pet.model_dump() for pet in pets]
    await pets_collection.insert_many(pet_docs)
    pets_collection_with_key = CollectionWithKey(collection=pets_collection, key="name")

    resources = {
        "owners": [
            ReadOnlyResource(
                owner_collection_with_key,
                Owner,
                query_operators=[
                    StringQueryOperator(model=Owner),  # type: ignore
                    NumericQuery(model=Owner),  # type: ignore
                    SparseFieldsQuery(model=Owner),
                    PaginationQuery(),
                ],
            )
        ],
        "pets": [
            ReadOnlyResource(
                pets_collection_with_key,
                Pet,
                query_operators=[
                    StringQueryOperator(model=Pet),
                    NumericQuery(model=Pet),
                    SparseFieldsQuery(model=Pet),
                    PaginationQuery(),
                ],
            )
        ],
    }
    api = API(resources=resources)

    client = TestClient(api.app)

    url = base + urlencode(payload)
    if debug:
        print(url)
    res = client.get(url)
    try:
        data = res.json().get("data", [])
    except json.decoder.JSONDecodeError:
        data = res.text

    return res, data


@pytest.mark.asyncio
async def test_cluster_run(mock_database):
    res, data = await search_helper(payload="", mock_database=mock_database)
    assert res.status_code == 200

    # Clear collections between tests
    await mock_database["owners"].drop()
    await mock_database["pets"].drop()

    payload = {"name": "Person1", "_limit": 10, "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/owners/?", mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "Person1"

    await mock_database["owners"].drop()
    await mock_database["pets"].drop()

    payload = {"name": "Pet1", "_limit": 10, "_all_fields": True}
    res, data = await search_helper(
        payload=payload, base="/pets/?", mock_database=mock_database
    )
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "Pet1"
