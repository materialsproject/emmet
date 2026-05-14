from dataclasses import dataclass
from fastapi import HTTPException, Query
from emmet.core.io.pymatgen import Element

from emmet.api.query_operator import QueryOperator
from emmet.api.query_operator.identifier import CompoundIDQuery

from emmet.api.query_operator import InQuery
from emmet.api.routes.materials.insertion_electrodes.utils import (
    electrodes_chemsys_to_criteria,
    electrodes_formula_to_criteria,
)
from emmet.api.utils import STORE_PARAMS

from emmet.core.electrode import validate_battery_id
from emmet.core.types.typing import CompoundIDType


class ElectrodeFormulaQuery(QueryOperator):
    """
    Method to generate a query for framework formula data
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
            crit.update(electrodes_formula_to_criteria(formula))

        return {"criteria": crit}


class ElectrodesChemsysQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        chemical system with wild cards.
    """

    def query(
        self,
        chemsys: str | None = Query(
            None,
            description="A comma delimited string list of chemical systems. \
Wildcards for unknown elements only supported for single chemsys queries",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if chemsys:
            crit.update(electrodes_chemsys_to_criteria(chemsys))

        return {"criteria": crit}


class ElectrodeElementsQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by electrode element data
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
        crit = {}  # type: dict

        if elements or exclude_elements:
            crit["entries_composition_summary.all_elements"] = {}

        if elements:
            try:
                element_list = [Element(e) for e in elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Problem processing one or more provided elements.",
                )
            crit["entries_composition_summary.all_elements"]["$all"] = [
                str(el) for el in element_list
            ]

        if exclude_elements:
            try:
                element_list = [Element(e) for e in exclude_elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Problem processing one or more provided elements.",
                )
            crit["entries_composition_summary.all_elements"]["$nin"] = [
                str(el) for el in element_list
            ]

        return {"criteria": crit}


@dataclass
class WorkingIonQuery(InQuery):
    """
    Method to generate a query for ranges of insertion electrode data values
    """

    field_name: str = "working_ion"

    def query(
        self,
        working_ion: str | None = Query(
            None,
            title="Element of the working ion, or comma-delimited string list of working ion elements.",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(working_ion)


@dataclass
class MultiBatteryIDQuery(CompoundIDQuery):
    """
    Generate a query for different root-level battery_id values
    """

    field_name: str = "battery_id"
    identifier_fields: tuple[str, ...] = ("material_ids", "working_ion")

    @staticmethod
    def validate_identifer(idx: str) -> CompoundIDType:
        """Validate a battery ID string."""
        return validate_battery_id(idx, as_components=True)
