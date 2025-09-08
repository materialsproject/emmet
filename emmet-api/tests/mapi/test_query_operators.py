from datetime import datetime
from enum import Enum

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field

from emmet.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from emmet.api.query_operator.submission import SubmissionQuery


class Owner(BaseModel):
    name: str = Field(..., title="Owner's name")
    age: int = Field(None, title="Owner's Age")
    weight: float = Field(None, title="Owner's weight")
    last_updated: datetime | None = Field(
        None, title="Last updated date for this record"
    )


def test_pagination_functionality():
    op = PaginationQuery()

    assert op.query(_skip=10, _limit=20, _page=None, _per_page=None) == {
        "limit": 20,
        "skip": 10,
    }

    assert op.query(_skip=None, _limit=None, _page=3, _per_page=23) == {
        "limit": 23,
        "skip": 46,
    }

    with pytest.raises(HTTPException):
        op.query(_limit=10000, _skip=100, _page=None, _per_page=None)

    with pytest.raises(HTTPException):
        op.query(_limit=None, _skip=None, _page=5, _per_page=10000)

    with pytest.raises(HTTPException):
        op.query(_limit=-1, _skip=100, _page=None, _per_page=None)

    with pytest.raises(HTTPException):
        op.query(_page=-1, _per_page=100, _skip=None, _limit=None)


def test_sparse_query_functionality():
    op = SparseFieldsQuery(model=Owner)

    assert op.meta()["default_fields"] == ["name", "age", "weight", "last_updated"]
    assert op.query() == {"properties": ["name", "age", "weight", "last_updated"]}


def test_numeric_query_functionality():
    op = NumericQuery(model=Owner)

    assert op.meta() == {}
    assert op.query(age_max=10, age_min=1, age_not_eq=[2, 3], weight_min=120) == {
        "criteria": {
            "age": {"$lte": 10, "$gte": 1, "$ne": [2, 3]},
            "weight": {"$gte": 120},
        }
    }


def test_sort_query_functionality():
    op = SortQuery()
    assert op.query(_sort_fields="volume,-density") == {
        "sort": {"volume": 1, "density": -1}
    }


def test_sort_query_fail():
    op = SortQuery(max_num=1)
    with pytest.raises(HTTPException):
        op.query(_sort_fields="volume,-density")


@pytest.fixture()
def status_enum():
    class StatusEnum(Enum):
        state_A = "A"
        state_B = "B"

    return StatusEnum


def test_submission_functionality(status_enum):
    op = SubmissionQuery(status_enum)
    dt = datetime.utcnow()

    assert op.query(state=status_enum.state_A, last_updated=dt) == {
        "criteria": {
            "$and": [
                {"$expr": {"$eq": [{"$arrayElemAt": ["$state", -1]}, "A"]}},
                {"$expr": {"$gt": [{"$arrayElemAt": ["$last_updated", -1]}, dt]}},
            ]
        }
    }
