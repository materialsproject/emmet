from datetime import datetime
from enum import Enum
from typing import Union

import pytest
from bson import ObjectId
from pydantic import BaseModel, Field

from emmet.api.resource.utils import generate_atlas_search_pipeline
from emmet.api.utils import (
    merge_atlas_queries,
    merge_queries,
    serialization_helper,
)


class SomeEnum(Enum):
    A = 1
    B = 2
    C = 3


class Pet(BaseModel):
    def __init__(self, name, age):
        self.name = name
        self.age = age


class AnotherPet(BaseModel):
    def __init__(self, name, age):
        self.name = name
        self.age = age


class AnotherOwner(BaseModel):
    name: str = Field(..., description="Owner name")
    weight_or_pet: Union[float, AnotherPet] = Field(..., title="Owners weight or Pet")


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(..., title="Owne'r Age")
    weight: float = Field(..., title="Owner's weight")
    last_updated: datetime = Field(..., title="Last updated date for this record")
    pet: Pet = Field(..., title="Owner's Pet")
    other: SomeEnum = Field(..., title="A enum?")


def test_serialization_helper():
    oid = ObjectId("60b7d47bb671aa7b01a2adf6")
    assert serialization_helper(oid) == "60b7d47bb671aa7b01a2adf6"


@pytest.mark.xfail()
def test_serialization_helper_xfail():
    oid = "test"
    serialization_helper(oid)


def test_merge_queries():
    # Test merging empty queries
    assert merge_queries([]) == {"criteria": {}, "properties": None}

    # Test merging queries with different fields
    query1 = {"criteria": {"field1": "value1"}, "properties": ["prop1"], "skip": 10}
    query2 = {"criteria": {"field2": "value2"}, "properties": ["prop2"], "limit": 20}

    # Test merging queries with nested criteria
    nested_query1 = {
        "criteria": {"nested": {"$and": [{"field3": "value3"}, {"field4": "value4"}]}},
        "properties": ["prop4"],
    }
    nested_query2 = {
        "criteria": {"nested": {"$or": [{"field5": "value5"}]}},
        "properties": ["prop5"],
    }
    merged_nested = merge_queries([nested_query1, nested_query2])
    assert merged_nested["criteria"]["nested"] == {
        "$or": [{"field5": "value5"}]
    }  # Later query overwrites earlier one
    assert set(merged_nested["properties"]) == {"prop4", "prop5"}

    # Test merging queries with array operators
    array_query1 = {
        "criteria": {"tags": {"$in": ["tag1", "tag2"]}},
        "properties": ["prop6"],
    }
    array_query2 = {"criteria": {"tags": {"$all": ["tag3"]}}, "properties": ["prop7"]}
    merged_array = merge_queries([array_query1, array_query2])
    assert merged_array["criteria"]["tags"] == {
        "$all": ["tag3"]
    }  # Later query overwrites
    assert set(merged_array["properties"]) == {"prop6", "prop7"}

    # Test merging queries with null properties
    null_prop_query = {"criteria": {"field8": "value8"}}
    merged_null = merge_queries([null_prop_query])
    assert merged_null["properties"] is None
    assert merged_null["criteria"] == {"field8": "value8"}

    merged = merge_queries([query1, query2])
    assert merged["criteria"] == {"field1": "value1", "field2": "value2"}
    assert set(merged["properties"]) == {"prop1", "prop2"}
    assert merged["skip"] == 10
    assert merged["limit"] == 20

    # Test merging queries with overlapping criteria
    query3 = {"criteria": {"field1": "new_value"}, "properties": ["prop3"]}
    merged = merge_queries([query1, query3])
    assert merged["criteria"]["field1"] == "new_value"
    assert set(merged["properties"]) == {"prop1", "prop3"}


def test_merge_atlas_queries():
    # Test merging empty queries
    assert merge_atlas_queries([]) == {
        "criteria": [],
        "properties": None,
        "facets": None,
    }

    # Test merging single operator queries
    query1 = {
        "criteria": {"equals": {"path": "field1", "value": "value1"}},
        "properties": ["prop1"],
    }
    query2 = {
        "criteria": {"equals": {"path": "field2", "value": "value2"}},
        "properties": ["prop2"],
        "facets": {"calc_typeFacet": {"type": "string", "path": "calc_type"}},
    }

    merged = merge_atlas_queries([query1, query2])
    assert len(merged["criteria"]) == 2
    assert {"equals": {"path": "field1", "value": "value1"}} in merged["criteria"]
    assert {"equals": {"path": "field2", "value": "value2"}} in merged["criteria"]
    assert set(merged["properties"]) == {"prop1", "prop2"}
    assert merged["facets"] == {
        "calc_typeFacet": {"type": "string", "path": "calc_type"}
    }

    # Test merging list criteria
    query3 = {
        "criteria": {
            "in": [
                {"path": "field3", "value": "val1"},
                {"path": "field4", "value": "val2"},
            ]
        },
        "skip": 10,
    }
    merged = merge_atlas_queries([query3])
    assert len(merged["criteria"]) == 2
    assert {"in": {"path": "field3", "value": "val1"}} in merged["criteria"]
    assert {"in": {"path": "field4", "value": "val2"}} in merged["criteria"]
    assert merged["skip"] == 10


def test_generate_atlas_search_pipeline():
    # Test basic search query without facets
    basic_query = {
        "criteria": [
            {"equals": {"path": "field1", "value": "value1"}},
            {"equals": {"path": "field2", "value": "value2"}},
        ],
        "properties": ["prop1", "prop2"],
        "skip": 5,
        "limit": 10,
    }
    pipeline = generate_atlas_search_pipeline(basic_query)
    assert len(pipeline) == 4  # $search, $project, $skip, $limit stages
    assert pipeline[0]["$search"]["compound"]["must"] == [
        {"equals": {"path": "field1", "value": "value1"}},
        {"equals": {"path": "field2", "value": "value2"}},
    ]
    assert pipeline[0]["$search"]["returnStoredSource"] is True
    assert pipeline[1]["$project"] == {"_id": 0, "prop1": 1, "prop2": 1}
    assert pipeline[2]["$skip"] == 5
    assert pipeline[3]["$limit"] == 10

    # Test query with facets
    faceted_query = {
        "criteria": [
            {"equals": {"path": "field1", "value": "value1"}},
            {"mustNot": {"equals": {"path": "field2", "value": "value2"}}},
        ],
        "properties": ["prop1"],
        "facets": {
            "field1_facet": {"type": "string", "path": "field1"},
            "field2_facet": {"type": "number", "path": "field2"},
        },
    }
    pipeline = generate_atlas_search_pipeline(faceted_query)
    assert len(pipeline) == 4  # $search with facet, $project, $skip, $facet stages
    assert pipeline[0]["$search"]["facet"]["operator"]["compound"]["must"] == [
        {"equals": {"path": "field1", "value": "value1"}}
    ]
    assert pipeline[0]["$search"]["facet"]["operator"]["compound"]["mustNot"] == [
        {"equals": {"path": "field2", "value": "value2"}}
    ]
    assert pipeline[0]["$search"]["facet"]["facets"] == faceted_query["facets"]
    assert pipeline[-1]["$facet"]["docs"] == []
    assert pipeline[-1]["$facet"]["meta"][0]["$replaceWith"] == "$$SEARCH_META"

    # Test query with sorting
    sorted_query = {
        "criteria": [{"equals": {"path": "field1", "value": "value1"}}],
        "properties": ["prop1"],
        "sort": {"field1": 1},
    }
    pipeline = generate_atlas_search_pipeline(sorted_query)
    assert pipeline[0]["$search"]["sort"] == {"field1": 1}

    # Test query with non-stored sources
    non_stored_query = {
        "criteria": [{"equals": {"path": "field1", "value": "value1"}}],
        "properties": ["_id", "prop1"],  # _id is typically a non-stored source
    }
    pipeline = generate_atlas_search_pipeline(non_stored_query)
    assert pipeline[0]["$search"]["returnStoredSource"] is True

    # Test empty query
    empty_query = {"criteria": []}
    pipeline = generate_atlas_search_pipeline(empty_query)
    assert pipeline[0]["$search"]["compound"]["must"] == []
    assert pipeline[0]["$search"]["compound"]["mustNot"] == []
