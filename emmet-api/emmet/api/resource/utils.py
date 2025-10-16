from typing import Callable

from fastapi import Depends, Request, Response

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, attach_signature
from pymongo.asynchronous.collection import AsyncCollection

NON_STORED_SOURCES = ["calcs_reversed", "orig_inputs"]


class CollectionWithKey:

    collection: AsyncCollection
    key: str

    def __init__(self, collection: AsyncCollection, key: str = "material_id"):
        self.collection = collection
        self.key = key


def attach_query_ops(
    function: Callable[[list[STORE_PARAMS]], dict], query_ops: list[QueryOperator]
) -> Callable[[list[STORE_PARAMS]], dict]:
    """
    Attach query operators to API compliant function
    The function has to take a list of STORE_PARAMs as the only argument.

    Args:
        function: the function to decorate
    """
    attach_signature(
        function,
        annotations={
            **{f"dep{i}": STORE_PARAMS for i, _ in enumerate(query_ops)},
            "request": Request,
            "temp_response": Response,
        },
        defaults={f"dep{i}": Depends(dep.query) for i, dep in enumerate(query_ops)},
    )
    return function


def generate_query_pipeline(query: dict):
    """
    Generate the generic aggregation pipeline used in GET endpoint queries.

    Args:
        query: Query parameters
    """
    crit = query["criteria"]
    pipeline = [{"$match": crit}] if crit else []
    sorting = query.get("sort", False)

    if sorting:
        sort_dict = {"$sort": {}}  # type: dict
        sort_dict["$sort"].update(query["sort"])
        pipeline.append(sort_dict)

    projection_dict = {"_id": 0}  # Do not return _id by default

    if query.get("properties", False):
        projection_dict.update({p: 1 for p in query["properties"]})

    pipeline.append({"$project": projection_dict})
    pipeline.append({"$skip": query.get("skip", 0)})

    if query.get("limit", False):
        pipeline.append({"$limit": query["limit"]})

    return pipeline


def generate_atlas_search_pipeline(query: dict):
    """
    Generate the aggregation pipeline for Atlas Search queries.

    Args:
        query: Query parameters
        store: Store containing endpoint data
    """
    pipeline = []

    # generate the operator, if more than one
    operator = {
        "compound": {
            "must": [q for q in query["criteria"] if not q.get("mustNot", False)]
        }
    }
    # append the mustNot criteria to the compound operator
    operator["compound"]["mustNot"] = [
        q["mustNot"] for q in query["criteria"] if q.get("mustNot", False)
    ]

    if query.get("facets", False):
        pipeline.append(
            {
                "$search": {
                    "index": "default",
                    "facet": {"operator": operator, "facets": query["facets"]},
                }
            }
        )
    else:
        pipeline.append({"$search": {"index": "default", **operator}})
    # add returnedStoredSource: True if non-stored source are not present in "properties"
    # for quicker document retrieval, otherwise, do a full lookup
    return_stored_source = not any(
        prop in NON_STORED_SOURCES for prop in query.get("properties", [])
    )
    if return_stored_source:
        pipeline[0]["$search"]["returnStoredSource"] = True  # type: ignore

    sorting = query.get("sort", False)
    if sorting:
        # no $ sign for atlas search
        sort_dict = {"sort": {}}  # type: ignore
        sort_dict["sort"].update(query["sort"])
        # add sort to $search stage
        pipeline[0]["$search"].update(sort_dict)

    projection_dict = {"_id": 0}
    if query.get("properties", False):
        projection_dict.update({p: 1 for p in query["properties"]})
    pipeline.insert(1, {"$project": projection_dict})  # type: ignore

    pipeline.append({"$skip": query.get("skip", 0)})

    if query.get("limit", False):
        pipeline.append({"$limit": query["limit"]})

    if query.get("facets", False):
        pipeline.append({"$facet": {"docs": [], "meta": [{"$replaceWith": "$$SEARCH_META"}, {"$limit": 1}]}})  # type: ignore

    return pipeline
