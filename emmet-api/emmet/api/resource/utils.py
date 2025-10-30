from typing import Callable

from fastapi import Depends, Request, Response

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, attach_signature
from pymongo.asynchronous.collection import AsyncCollection


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

    if query.get("criteria", False) is False or len(query["criteria"]) == 0:
        operator = {"exists": {"path": "_id"}}
    else:  # generate the operator, if more than one
        operator = {"compound": {"must": [], "mustNot": []}}

        # Build the must clauses
        for q in query["criteria"]:
            if not q.get("mustNot", False):
                if "must" in q:
                    # If q has a "must" key, expand its contents instead of using q directly
                    operator["compound"]["must"].extend(q["must"])
                else:
                    # Use the query as-is
                    operator["compound"]["must"].append(q)
            else:
                operator["compound"]["mustNot"].extend(q["mustNot"])

    search_base = {
        "$search": {
            "index": "default",
            "returnStoredSource": True,
            "count": {"type": "total"},
        }
    }

    if p_token := query.get("pagination_token", None):
        if query.get("forward", True):
            search_base["$search"]["searchAfter"] = p_token
        else:
            search_base["$search"]["searchBefore"] = p_token

    # commenting out facet code for now as there are no known use cases to test it
    # if query.get("facets", False):
    #     search_base["$search"]["facet"] = {
    #         "operator": operator,
    #         "facets": query["facets"],
    #     }
    # else:
    search_base["$search"].update(operator)

    sort_dict = {"sort": {"_id": 1}}
    if query.get("sort", False):
        sort_dict["sort"] = {**query["sort"], "_id": sort_dict["sort"].get("_id", 1)}
    # add sort to $search stage
    search_base["$search"].update(sort_dict)

    pipeline.append(search_base)

    projection_dict = {
        "_id": 0,
        "meta": "$$SEARCH_META",
        "meta_pagination_token": {"$meta": "searchSequenceToken"},
    }
    if query.get("properties", False):
        projection_dict.update({p: 1 for p in query["properties"]})
    pipeline.append({"$project": projection_dict})  # type: ignore

    pipeline.append({"$skip": query.get("skip", 0)})

    if query.get("limit", False):
        pipeline.append({"$limit": query["limit"]})

    # commenting out facet code for now as there are no known use cases to test it
    # if query.get("facets", False):
    #     pipeline.append({"$facet": {"docs": [], "meta": [{"$replaceWith": "$$SEARCH_META"}, {"$limit": 1}]}})  # type: ignore

    return pipeline
