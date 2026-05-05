from dataclasses import dataclass
from fastapi import Query

from emmet.api.query_operator import QueryOperator
from emmet.api.query_operator.core import InQuery
from emmet.api.query_operator.identifier import CompoundIDQuery
from emmet.api.utils import STORE_PARAMS


class IsStableQuery(QueryOperator):
    """
    Method to generate a query on whether a material is stable
    """

    def query(
        self,
        is_stable: bool | None = Query(
            None, description="Whether the material is stable."
        ),
    ):
        crit = {}

        if is_stable is not None:
            crit["is_stable"] = is_stable

        return {"criteria": crit}


@dataclass
class MultiThermoIDQuery(CompoundIDQuery):
    """
    Method to generate a query for different root-level thermo_id values
    """

    field_name: str = "thermo_id"
    identifier_fields: tuple[str, ...] = ("material_id", "thermo_type")
    separator: str = "_"


@dataclass
class MultiThermoTypeQuery(InQuery):
    """
    Method to generate a query for different root-level thermo_type values
    """

    field_name: str = "thermo_type"

    def query(
        self,
        thermo_types: str | None = Query(
            None, description="Comma-separated list of thermo_type values to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(thermo_types)


@dataclass
class MultiPhaseDiagramIDQuery(InQuery):
    """
    Method to generate a query for different root-level phase_diagram_id values
    """

    field_name: str = "phase_diagram_id"

    def query(
        self,
        phase_diagram_ids: str | None = Query(
            None,
            description="Comma-separated list of phase_diagram_id values to query on",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(phase_diagram_ids)
