from collections import defaultdict

from fastapi import HTTPException, Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS
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


class VoltageStepQuery(QueryOperator):
    """
    Method to generate a query for ranges of voltage step data values
    """

    def query(
        self,
        delta_volume_max: float | None = Query(
            None,
            description="Maximum value for the max volume change in percent for a particular voltage step.",
        ),
        delta_volume_min: float | None = Query(
            None,
            description="Minimum value for the max volume change in percent for a particular voltage step.",
        ),
        average_voltage_max: float | None = Query(
            None,
            description="Maximum value for the average voltage for a particular voltage step in V.",
        ),
        average_voltage_min: float | None = Query(
            None,
            description="Minimum value for the average voltage for a particular voltage step in V.",
        ),
        max_voltage_max: float | None = Query(
            None,
            description="Maximum value for the maximum voltage for a particular voltage step in V.",
        ),
        max_voltage_min: float | None = Query(
            None,
            description="Minimum value for the maximum voltage for a particular voltage step in V.",
        ),
        min_voltage_max: float | None = Query(
            None,
            description="Maximum value for the minimum voltage for a particular voltage step in V.",
        ),
        min_voltage_min: float | None = Query(
            None,
            description="Minimum value for the minimum voltage for a particular voltage step in V.",
        ),
        capacity_grav_max: float | None = Query(
            None,
            description="Maximum value for the gravimetric capacity in maH/g.",
        ),
        capacity_grav_min: float | None = Query(
            None,
            description="Minimum value for the gravimetric capacity in maH/g.",
        ),
        capacity_vol_max: float | None = Query(
            None,
            description="Maximum value for the volumetric capacity in maH/cc.",
        ),
        capacity_vol_min: float | None = Query(
            None,
            description="Minimum value for the volumetric capacity in maH/cc.",
        ),
        energy_grav_max: float | None = Query(
            None,
            description="Maximum value for the gravimetric energy (specific energy) in Wh/kg.",
        ),
        energy_grav_min: float | None = Query(
            None,
            description="Minimum value for the gravimetric energy (specific energy) in Wh/kg.",
        ),
        energy_vol_max: float | None = Query(
            None,
            description="Maximum value for the volumetric energy (energy_density) in Wh/l.",
        ),
        energy_vol_min: float | None = Query(
            None,
            description="Minimum value for the volumetric energy (energy_density) in Wh/l.",
        ),
        fracA_charge_max: float | None = Query(
            None,
            description="Maximum value for the atomic fraction of the working ion in the charged state.",
        ),
        fracA_charge_min: float | None = Query(
            None,
            description="Minimum value for the atomic fraction of the working ion in the charged state.",
        ),
        fracA_discharge_max: float | None = Query(
            None,
            description="Maximum value for the atomic fraction of the working ion in the discharged state.",
        ),
        fracA_discharge_min: float | None = Query(
            None,
            description="Minimum value for the atomic fraction of the working ion in the discharged state.",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        d = {
            "max_delta_volume": [delta_volume_min, delta_volume_max],
            "average_voltage": [average_voltage_min, average_voltage_max],
            "max_voltage": [max_voltage_min, max_voltage_max],
            "min_voltage": [min_voltage_min, min_voltage_max],
            "capacity_grav": [capacity_grav_min, capacity_grav_max],
            "capacity_vol": [capacity_vol_min, capacity_vol_max],
            "energy_grav": [energy_grav_min, energy_grav_max],
            "energy_vol": [energy_vol_min, energy_vol_max],
            "fracA_charge": [fracA_charge_min, fracA_charge_max],
            "fracA_discharge": [fracA_discharge_min, fracA_discharge_max],
        }

        for entry in d:
            if d[entry][0] is not None:
                crit[entry]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[entry]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = [key for key in self._keys_from_query() if key != "delta_volume_min"]
        indexes = []
        for key in keys:
            if "_min" in key:
                key = key.replace("_min", "")
                indexes.append((key, False))
        indexes.append(("max_delta_volume", False))
        return indexes


class InsertionVoltageStepQuery(QueryOperator):
    """
    Method to generate a query for ranges of insertion voltage step data values
    """

    def query(
        self,
        stability_charge_max: float | None = Query(
            None,
            description="The maximum value of the energy above hull of the charged material.",
        ),
        stability_charge_min: float | None = Query(
            None,
            description="The minimum value of the energy above hull of the charged material.",
        ),
        stability_discharge_max: float | None = Query(
            None,
            description="The maximum value of the energy above hull of the discharged material.",
        ),
        stability_discharge_min: float | None = Query(
            None,
            description="The minimum value of the energy above hull of the discharged material.",
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        d = {
            "stability_charge": [stability_charge_min, stability_charge_max],
            "stability_discharge": [stability_discharge_min, stability_discharge_max],
        }

        for entry in d:
            if d[entry][0] is not None:
                crit[entry]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[entry]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = self._keys_from_query()

        indexes = []
        for key in keys:
            if "_min" in key:
                key = key.replace("_min", "")
                indexes.append((key, False))
        return indexes


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


class ElectrodeMultiMaterialIDQuery(QueryOperator):
    """
    Method to generate a query for different root-level material_id values
    """

    def query(
        self,
        material_ids: str | None = Query(
            None, description="Comma-separated list of material_id values to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if material_ids:
            crit.update(
                {
                    "material_ids": {
                        "$in": [
                            material_id.strip()
                            for material_id in material_ids.split(",")
                        ]
                    }
                }
            )

        return {"criteria": crit}


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
