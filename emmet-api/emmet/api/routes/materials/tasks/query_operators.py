from datetime import datetime
from collections import defaultdict
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS
from emmet.api.routes.materials.tasks.utils import (
    calcs_reversed_to_trajectory,
    task_to_entry,
)
from pymatgen.core.periodic_table import Element

from emmet.api.routes.materials.tasks.utils import chemsys_to_search
from fastapi import Query, HTTPException
from typing import Optional
from monty.json import jsanitize

FACETS_PARAMS ={
                        "calc_typeFacet": {
                            "type": "string",
                            "path": "calc_type",
                        },
                        "task_typeFacet": {
                            "type": "string",
                            "path": "task_type",
                        },
                        "run_typeFacet": {
                            "type": "string",
                            "path": "run_type",
                        },
                }
class LastUpdatedQuery(QueryOperator):
    def query(
        self,
        last_updated_min: Optional[datetime] = Query(
            None, description="Minimum last updated UTC datetime"
        ),
        last_updated_max: Optional[datetime] = Query(
            None, description="Maximum last updated UTC datetime"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if last_updated_min or last_updated_max:
            crit["range"] = {"path" : "last_updated"}
            if last_updated_min:
                crit["range"]["gte"] = last_updated_min
            if last_updated_max:
                crit["range"]["lte"] = last_updated_max

        return {"criteria": crit}


class MultipleTaskIDsQuery(QueryOperator):
    """
    Method to generate a query on search docs using multiple task_id values
    """

    def query(
        self,
        task_ids: Optional[str] = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if task_ids:
            task_ids = [task_id.strip() for task_id in task_ids.split(",")]
            crit = {
                "in": {
                       "path": "task_id",
                        "value": task_ids
                    }
                }

        return {"criteria": crit, 
        }

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
        task_ids: Optional[str] = Query(
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
        Post processing to generatore trajectory data
        """

        d = [
            {
                "task_id": doc["task_id"],
                "trajectories": jsanitize(
                    calcs_reversed_to_trajectory(doc["calcs_reversed"])
                ),
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
        task_ids: Optional[str] = Query(
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

class TaskFormulaQuery(QueryOperator):
    """
    Method to generate a query on search docs using multiple task_id values
    """

    def query(
        self,
        formula: Optional[str] = Query(
            None, description="Comma-separated list of formula to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }

        if formula:
            formula_pretty = [formula.strip() for formula in formula.split(",")]
            if len(formula_pretty) == 1:
                crit = {
                    "equals": {
                        "path": "formula_pretty",
                            "value": formula_pretty[0]
                        }
                    }
            else:
                crit = {
                    "in": {
                        "path": "formula_pretty",
                            "value": formula_pretty
                        }
                    }

        return {"criteria": crit
        }

class TaskChemsysQuery(QueryOperator):
    def query(
        self,
        chemsys: Optional[str] = Query(
            None, description="Comma-separated list of chemsys to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if chemsys:
            crit = chemsys_to_search(chemsys)

        return {"criteria": crit
        }

class TaskTypeQuery(QueryOperator):
    def query(
        self,
        task_type: Optional[str] = Query(
            None, description="Comma-separated list of task_types to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if task_type:
            crit = {
                "equals": {
                    "path": "task_type",
                    "value": task_type
                }
            }
        return {"criteria": crit
        }

class TaskElementsQuery(QueryOperator):
    def query(
        self,
        elements: Optional[str] = Query(
            None, description="Comma-separated list of elements to query on"
        ),
        exclude_elements: Optional[str] = Query(
            None, description="Comma-separated list of elements to exclude from query")
    ) -> STORE_PARAMS:
        crit = {
        }
        if elements:
            try:
                eles = [Element(e) for e in elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a valid comma-seperated list of elements",
                )
            
            crit["exists"] = []
            for el in eles:    
                crit["exists"].append({
                    "path": f"composition_reduced.{el}"
                }
                )
            
            return {"criteria": crit
            }
    
        if exclude_elements:
            try:
                eles = [Element(e) for e in exclude_elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )
            
            crit["mustNot"] = []
            for ele in eles:
                crit["mustNot"].append({
                    "exists": {
                    "path": f"composition_reduced.{ele}"
                }
                }
                )
        return {"criteria": crit}

class CalcTypeQuery(QueryOperator):
    def query(
        self,
        calc_type: Optional[str] = Query(
            None, description="Comma-separated list of calc_types to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if calc_type:
            crit = {
                "equals": {
                    "path": "calc_type",
                    "value": calc_type,
                }
            } 
        return {"criteria": crit
        }
    
class RunTypeQuery(QueryOperator):
    def query(
        self,
        run_type: Optional[str] = Query(
            None, description="Comma-separated list of run_types to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if run_type:
            crit = {
                "equals": {
                    "path": "run_type",
                    "value": run_type
                }
            } 
        return {"criteria": crit
        }
class BatchQuery(QueryOperator):
    def query(
        self,
        batches: Optional[str] = Query(
            None, description="Comma-separated list of batch ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if batches:
            batch_list = [b.strip() for b in batches.split(",")]
            crit = {
                "in": {
                    "path": "batch_id",
                    "value": batch_list
                }
            } 
        return {"criteria": crit
        }

class FacetQuery(QueryOperator):
    def query(
        self,
        facets: Optional[str] = Query(
            None, description="Facets query to return facets meta information"
        ),
    ) -> STORE_PARAMS:
        crit = {
        }
        if facets:
            facets_list = [facet.strip() for facet in facets.split(",")]
            for f in facets_list:
                crit.update(
                    {
                        f"{f}Facet": {
                            "type": "string",
                            "path": f,
                        }
                    }
                )
        else:
            crit = {**FACETS_PARAMS}
        return {"facets": crit}
        