import json
from enum import Enum
from random import choice, randint
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from requests import Response
from starlette.testclient import TestClient

from emmet.api.API import API
from emmet.api.query_operator import NumericQuery, PaginationQuery, SparseFieldsQuery, StringQueryOperator
from emmet.api.resource import ReadOnlyResource
from maggma.stores import MemoryStore


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


owners = [Owner(name=f"Person{i}", age=randint(10, 100), weight=randint(100, 200)) for i in list(range(10))]


pets = [
    Pet(
        name=f"Pet{i}",
        pet_type=choice(list(PetType)),
        owner_name=choice(owners).name,
    )
    for i in list(range(40))
]


@pytest.fixture()
def owner_store():
    store = MemoryStore("owners", key="name")
    store.connect()
    store.update([jsonable_encoder(d) for d in owners])
    return store


@pytest.fixture()
def pet_store():
    store = MemoryStore("pets", key="name")
    store.connect()
    store.update([jsonable_encoder(d) for d in pets])
    return store


def test_msonable(owner_store, pet_store):
    owner_endpoint = ReadOnlyResource(owner_store, Owner)
    pet_endpoint = ReadOnlyResource(pet_store, Pet)

    manager = API({"owners": owner_endpoint, "pets": pet_endpoint})

    api_dict = manager.as_dict()

    for k in ["@class", "@module", "resources"]:
        assert k in api_dict


def search_helper(payload, base: str = "/?", debug=True) -> tuple[Response, Any]:
    """
    Helper function to directly query search endpoints

    Args:
        store: store f
        base: base of the query, default to /query?
        client: TestClient generated from FastAPI
        payload: query in dictionary format
        debug: True = print out the url, false don't print anything

    Returns:
        request.Response object that contains the response of the corresponding payload
    """
    owner_store = MemoryStore("owners", key="name")
    owner_store.connect()
    owner_store.update([d.model_dump() for d in owners])

    pets_store = MemoryStore("pets", key="name")
    pets_store.connect()
    pets_store.update([jsonable_encoder(d) for d in pets])

    resources = {
        "owners": [
            ReadOnlyResource(
                owner_store,
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
                pets_store,
                Owner,
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


def test_cluster_run(owner_store, pet_store):
    res, data = search_helper(payload="")
    assert res.status_code == 200

    payload = {"name": "Person1", "_limit": 10, "_all_fields": True}
    res, data = search_helper(payload=payload, base="/owners/?")
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "Person1"

    payload = {"name": "Pet1", "_limit": 10, "_all_fields": True}
    res, data = search_helper(payload=payload, base="/pets/?")
    assert res.status_code == 200
    assert len(data) == 1
    assert data[0]["name"] == "Pet1"
