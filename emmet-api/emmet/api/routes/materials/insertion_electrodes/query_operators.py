from collections import defaultdict

from fastapi import HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from pymatgen.core.periodic_table import Element

from emmet.api.routes.materials.insertion_electrodes.utils import (
    electrodes_chemsys_to_criteria,
    electrodes_formula_to_criteria,
)


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

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("eentries_composition_summary.all_composition_reduced", False),
            ("entries_composition_summary.all_formulas", False),
        ]


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

    def ensure_indexes(self):  # pragma: no cover
        keys = [
            "entries_composition_summary.all_chemsys",
            "entries_composition_summary.all_elements",
            "nelements",
        ]
        return [(key, False) for key in keys]


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


class WorkingIonQuery(QueryOperator):
    """
    Method to generate a query for ranges of insertion electrode data values
    """

    def query(
        self,
        working_ion: str | None = Query(
            None,
            title="Element of the working ion, or comma-delimited string list of working ion elements.",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        if working_ion:
            element_list = [element.strip() for element in working_ion.split(",")]
            if len(element_list) == 1:
                crit["working_ion"] = element_list[0]
            else:
                crit["working_ion"] = {"$in": element_list}

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("working_ion", False)]


class MultiBatteryIDQuery(QueryOperator):
    """
    Method to generate a query for different root-level battery_id values
    """

    def query(
        self,
        battery_ids: str | None = Query(
            None, description="Comma-separated list of battery_id values to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if battery_ids:
            battery_id_list = [
                material_id.strip() for material_id in battery_ids.split(",")
            ]

            if len(battery_id_list) == 1:
                crit.update({"battery_id": battery_id_list[0]})
            else:
                crit.update({"battery_id": {"$in": battery_id_list}})

        return {"criteria": crit}
