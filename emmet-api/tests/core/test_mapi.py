from enum import Enum
from random import choice, randint

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from emmet.api.core import MAPI
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


@pytest_asyncio.fixture
async def owner_collection(mock_database):
    collection = mock_database["owners"]

    # Insert test data
    owner_docs = [owner.model_dump() for owner in owners]
    await collection.insert_many(owner_docs)

    return CollectionWithKey(collection=collection, key="name")


@pytest_asyncio.fixture
async def pet_collection(mock_database):
    collection = mock_database["pets"]

    # Insert test data
    pet_docs = [pet.model_dump() for pet in pets]
    await collection.insert_many(pet_docs)

    return CollectionWithKey(collection=collection, key="name")


@pytest.mark.asyncio
async def test_mapi(owner_collection, pet_collection):
    owner_endpoint = ReadOnlyResource(owner_collection, Owner)
    pet_endpoint = ReadOnlyResource(pet_collection, Pet)

    manager = MAPI({"owners": [owner_endpoint], "pets": [pet_endpoint]})

    assert manager.app.openapi()["components"]["securitySchemes"] == {
        "ApiKeyAuth": {
            "descriptions": "MP API key to authorize requests",
            "name": "X-API-KEY",
            "in": "header",
            "type": "apiKey",
        }
    }
