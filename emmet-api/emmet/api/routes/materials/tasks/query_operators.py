from datetime import datetime

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


class AtlasFormulaQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        formula or chemical system with wild cards.
    """

    def query(
        self,
        formula: str | None = Query(
            None,
            description="Query by formula including anonymized formula or by including wild cards. \
A comma delimited string list of anonymous formulas or regular formulas can also be provided.",
        ),
    ) -> STORE_PARAMS:
        crit = {}
        if formula:
            crit.update(formula_to_atlas_criteria(formula))
        return {"criteria": crit}


class AtlasElementsQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by element data
    """

    def query(
        self,
        elements: str | None = Query(
            None,
            description="Query by elements in the material composition as a comma-separated list",
            max_length=60,
        ),
        exclude_elements: str | None = Query(
            None,
            description="Query by excluded elements in the material composition as a comma-separated list",
            max_length=60,
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if elements:
            must_elem = []  # type: list[dict]
            try:
                element_list = [Element(e) for e in elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )

            for el in element_list:
                must_elem.append({"exists": {"path": f"composition_reduced.{el}"}})

            crit.update({"must": must_elem})

        if exclude_elements:
            must_not_elem = []  # type: list[dict]
            try:
                element_list = [Element(e) for e in exclude_elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )

            for el in element_list:
                must_not_elem.append({"exists": {"path": f"composition_reduced.{el}"}})

            crit.update({"mustNot": must_not_elem})

        return {"criteria": crit} if len(crit) > 0 else {"criteria": {}}


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
        crit = {}  # type: list[dict]

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
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            crit.update(
                {
                    "in": {
                        "path": "task_id",
                        "value": [task_id.strip() for task_id in task_ids.split(",")],
                    }
                }
            )

        return {"criteria": crit}

    def post_process(self, docs, query):
        """
        Post processing to remove unwanted fields from all task queries
        """

        for doc in docs:
            doc.pop("tags", None)
            doc.pop("sbxn", None)
            doc.pop("dir_name", None)

        return docs


class TrajectoryQuery(QueryOperator):
    """
    Method to generate a query on calculation trajectory data from task documents
    """

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            crit.update(
                {
                    "task_id": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
            )

        return {"criteria": crit}

    def post_process(self, docs, query):
        """
        Post processing to generate trajectory data
        """

        d = [
            {
                "task_id": doc["task_id"],
                "trajectories": [
                    traj.model_dump(mode="json")
                    for traj in calcs_reversed_to_trajectory(doc["calcs_reversed"])
                ],
            }
            for doc in docs
        ]

        return d


class EntryQuery(QueryOperator):
    """
    Method to generate a query on calculation entry data from task documents
    """

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            crit.update(
                {
                    "task_id": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
            )

        return {"criteria": crit}

    def post_process(self, docs, query):
        """
        Post processing to generatore entry data
        """

        d = [
            {"task_id": doc["task_id"], "entry": jsanitize(task_to_entry(doc))}
            for doc in docs
        ]

        return d


class DeprecationQuery(QueryOperator):
    """
    Method to generate a query on calculation trajectory data from task documents
    """

    def query(
        self,
        task_ids: str = Query(
            ..., description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        self.task_ids = [task_id.strip() for task_id in task_ids.split(",")]

        crit = {}

        if task_ids:
            crit.update({"deprecated_tasks": {"$in": self.task_ids}})

        return {"criteria": crit}

    def post_process(self, docs, query):
        """
        Post processing to generatore deprecation data
        """

        d = []

        for task_id in self.task_ids:
            deprecation = {
                "task_id": task_id,
                "deprecated": False,
                "deprecation_reason": None,
            }
            for doc in docs:
                if task_id in doc["deprecated_tasks"]:
                    deprecation = {
                        "task_id": task_id,
                        "deprecated": True,
                        "deprecation_reason": None,
                    }
                    break

            d.append(deprecation)

        return d
