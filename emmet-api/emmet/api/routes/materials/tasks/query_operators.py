from datetime import datetime
from typing import Any

from fastapi import HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from monty.json import jsanitize
from pymatgen.core.periodic_table import Element
from emmet.api.routes.materials.materials.utils import (
    formula_to_atlas_criteria,
)
from emmet.api.routes.materials.tasks.utils import (
    calcs_reversed_to_trajectory,
    task_to_entry,
)


class AtlasBatchIdQuery(QueryOperator):
    """Method to generate a query on batch_id"""

    def query(
        self,
        batch_id: str | None = Query(
            None,
            description="Query by batch identifier",
        ),
        batch_id_not_eq: str | None = Query(
            None,
            description="Exclude batch identifier",
        ),
        batch_id_eq_any: str | None = Query(
            None,
            description="Query by a comma-separated list of batch identifiers",
        ),
        batch_id_neq_any: str | None = Query(
            None,
            description="Exclude a comma-separated list of batch identifiers",
        ),
    ) -> STORE_PARAMS:
        all_kwargs = [batch_id, batch_id_not_eq, batch_id_eq_any, batch_id_neq_any]
        if sum(bool(kwarg) for kwarg in all_kwargs) > 1:
            raise HTTPException(
                status_code=400,
                detail="Please only choose one of `batch_id` parameters to filter.",
            )

        crit = {}  # type: dict
        if batch_id:
            crit.update(
                {
                    "in": {
                        "path": "batch_id",
                        "value": batch_id,
                    }
                }
            )
        elif batch_id_eq_any:
            crit.update(
                {
                    "in": {
                        "path": "batch_id",
                        "value": [
                            batch_id.strip() for batch_id in batch_id_eq_any.split(",")
                        ],
                    }
                }
            )
        elif batch_id_not_eq:
            crit.update(
                {
                    "mustNot": [
                        {
                            "in": {
                                "path": "batch_id",
                                "value": batch_id_not_eq,
                            }
                        }
                    ]
                }
            )
        elif batch_id_neq_any:
            crit.update(
                {
                    "mustNot": [
                        {
                            "in": {
                                "path": "batch_id",
                                "value": [
                                    batch_id.strip()
                                    for batch_id in batch_id_neq_any.split(",")
                                ],
                            }
                        }
                    ]
                }
            )

        return {"criteria": crit}


class AtlasFormulaQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        formula or chemical system with wild cards.
    """

    def query(
        self,
        formula: str | None = Query(
            None,
            description="Query by formula including anonymized formula or by including wild cards. "
            "A comma delimited string list of anonymous formulas or regular formulas can also be provided.",
        ),
    ) -> STORE_PARAMS:
        return {"criteria": formula_to_atlas_criteria(formula) if formula else {}}


class AtlasElementsQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by element data
    """

    def query(
        self,
        elements: str | None = Query(
            None,
            description="Query by elements in the material composition as a comma-separated list",
        ),
        exclude_elements: str | None = Query(
            None,
            description="Query by excluded elements in the material composition as a comma-separated list",
        ),
    ) -> STORE_PARAMS:
        crit: dict[str, Any] = {}

        for must_k, element_str in {
            "must": elements,
            "mustNot": exclude_elements,
        }.items():
            if element_str:
                elem_q: list[dict[str, Any]] = []
                try:
                    element_list = [
                        Element(e.strip()) for e in element_str.strip().split(",")
                    ]
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail="Please provide a comma-seperated list of elements",
                    )

                elem_q += [
                    {"exists": {"path": f"composition_reduced.{el}"}}
                    for el in element_list
                ]

                crit[must_k] = elem_q

        return {"criteria": crit}


class LastUpdatedQuery(QueryOperator):
    def query(
        self,
        last_updated_min: datetime | None = Query(
            None, description="Minimum last updated UTC datetime"
        ),
        last_updated_max: datetime | None = Query(
            None, description="Maximum last updated UTC datetime"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if last_updated_min and last_updated_max:
            # Both min and max specified - use single range query
            crit.update(
                {
                    "range": {
                        "path": "last_updated",
                        "gte": last_updated_min,
                        "lte": last_updated_max,
                    }
                }
            )
        elif last_updated_min:
            # Only minimum specified
            crit.update({"range": {"path": "last_updated", "gte": last_updated_min}})
        elif last_updated_max:
            # Only maximum specified
            crit.update({"range": {"path": "last_updated", "lte": last_updated_max}})

        return {"criteria": crit}


class MultipleTaskIDsQuery(QueryOperator):
    """
    Method to generate a query on search docs using multiple task_id values
    """

    def query(
        self,
        task_ids: str | None = Query(
            None,
            description="Comma-separated list of task_ids to query on",
        ),
    ) -> STORE_PARAMS:
        return {
            "criteria": (
                {
                    "in": {
                        "path": "task_id",
                        "value": [task_id.strip() for task_id in task_ids.split(",")],
                    }
                }
                if task_ids
                else {}
            )
        }

    def post_process(self, docs, query):
        """
        Post processing to remove unwanted fields from all task queries
        """
        _ = [doc.pop(k, None) for doc in docs for k in ("tags", "sbxn", "dir_name")]
        return docs


class TrajectoryQuery(QueryOperator):
    """
    Method to generate a query on calculation trajectory data from task documents
    """

    def query(
        self,
        task_ids: str | None = Query(
            None,
            description="Comma-separated list of task_ids to query on",
        ),
    ) -> STORE_PARAMS:
        return {
            "criteria": (
                {
                    "task_id": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
                if task_ids
                else {}
            )
        }

    def post_process(self, docs, query):
        """
        Post processing to generate trajectory data
        """
        return [
            {
                "task_id": doc["task_id"],
                "trajectories": [
                    traj.model_dump(mode="json")
                    for traj in calcs_reversed_to_trajectory(doc["calcs_reversed"])
                ],
            }
            for doc in docs
        ]


class EntryQuery(QueryOperator):
    """
    Method to generate a query on calculation entry data from task documents
    """

    def query(
        self,
        task_ids: str | None = Query(
            None,
            description="Comma-separated list of task_ids to query on",
        ),
    ) -> STORE_PARAMS:
        return {
            "criteria": (
                {
                    "task_id": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
                if task_ids
                else {}
            )
        }

    def post_process(self, docs, query):
        """
        Post processing to generate entry data
        """
        return [
            {"task_id": doc["task_id"], "entry": jsanitize(task_to_entry(doc))}
            for doc in docs
        ]


class DeprecationQuery(QueryOperator):
    """
    Method to generate a query on deprecated calculation data from task documents.
    """

    def query(
        self,
        task_ids: str = Query(
            ...,
            description="Comma-separated list of task_ids to query on",
        ),
    ) -> STORE_PARAMS:
        self.task_ids = [task_id.strip() for task_id in task_ids.split(",")]
        return {
            "criteria": {"deprecated_tasks": {"$in": self.task_ids}} if task_ids else {}
        }

    def post_process(self, docs, query):
        """
        Post processing to generate deprecation data
        """
        return [
            {
                "task_id": task_id,
                "deprecated": any(task_id in doc["deprecated_tasks"] for doc in docs),
                "deprecation_reason": None,
            }
            for task_id in self.task_ids
        ]
