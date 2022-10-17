from typing import Optional
from fastapi import Query
from maggma.api.utils import STORE_PARAMS
from maggma.api.query_operator import QueryOperator


class IsStableQuery(QueryOperator):
    """
    Method to generate a query on whether a material is stable
    """

    def query(
        self,
        is_stable: Optional[bool] = Query(
            None, description="Whether the material is stable."
        ),
    ):

        crit = {}

        if is_stable is not None:
            crit["is_stable"] = is_stable

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = self._keys_from_query()
        return [(key, False) for key in keys]


class MultiThermoIDQuery(QueryOperator):
    """
    Method to generate a query for different root-level thermo_id values
    """

    def query(
        self,
        thermo_ids: Optional[str] = Query(
            None, description="Comma-separated list of thermo_id values to query on"
        ),
    ) -> STORE_PARAMS:

        crit = {}  # type: dict

        if thermo_ids:

            thermo_id_list = [thermo_id.strip() for thermo_id in thermo_ids.split(",")]

            if len(thermo_id_list) == 1:
                crit.update({"thermo_id": thermo_id_list[0]})
            else:
                crit.update({"thermo_id": {"$in": thermo_id_list}})

        return {"criteria": crit}


class MultiThermoTypeQuery(QueryOperator):
    """
    Method to generate a query for different root-level thermo_type values
    """

    def query(
        self,
        thermo_types: Optional[str] = Query(
            None, description="Comma-separated list of thermo_type values to query on"
        ),
    ) -> STORE_PARAMS:

        crit = {}  # type: dict

        if thermo_types:

            thermo_type_list = [
                thermo_type.strip() for thermo_type in thermo_types.split(",")
            ]

            if len(thermo_type_list) == 1:
                crit.update({"thermo_type": thermo_type_list[0]})
            else:
                crit.update({"thermo_type": {"$in": thermo_type_list}})

        return {"criteria": crit}
