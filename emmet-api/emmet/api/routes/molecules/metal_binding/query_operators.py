from typing import Any, Dict, Optional, Union
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class BindingDataQuery(QueryOperator):
    """
    Method to generate a query on binding data.
    """

    def query(
        self,
        metal_element: Optional[str] = Query(
            None,
            description="Element symbol for coordinated metal, e.g. 'Li' for lithium or 'Mg' for magnesium",
        ),
        metal_partial_charge_min: Optional[float] = Query(
            None, description="Minimum metal partial charge."
        ),
        metal_partial_charge_max: Optional[float] = Query(
            None, description="Maximum metal partial charge."
        ),
        metal_partial_spin_min: Optional[float] = Query(
            None,
            description="Minimum metal partial spin (only meaningful for open-shell systems).",
        ),
        metal_partial_spin_max: Optional[float] = Query(
            None,
            description="Maximum metal partial spin (only meaningful for open-shell systems).",
        ),
        metal_assigned_charge_min: Optional[float] = Query(
            None,
            description="Minimum charge of the metal, determined by analyzing partial charges/spins.",
        ),
        metal_assigned_charge_max: Optional[float] = Query(
            None,
            description="Maximum charge of the metal, determined by analyzing partial charges/spins.",
        ),
        metal_assigned_spin_min: Optional[Union[int, float]] = Query(
            None,
            description="Minimum spin multiplicity of the metal, determined by analyzing partial spins.",
        ),
        metal_assigned_spin_max: Optional[Union[int, float]] = Query(
            None,
            description="Maximum spin multiplicity of the metal, determined by analyzing partial spins.",
        ),
        number_coordinate_bonds_min: Optional[int] = Query(
            None, description="Minimum number of atoms coordinated to the metal."
        ),
        number_coordinate_bonds_max: Optional[int] = Query(
            None, description="Maximum number of atoms coordinated to the metal."
        ),
        binding_energy_min: Optional[float] = Query(
            None, description="Minimum binding electronic energy (units: eV)"
        ),
        binding_energy_max: Optional[float] = Query(
            None, description="Maximum binding electronic energy (units: eV)"
        ),
        binding_enthalpy_min: Optional[float] = Query(
            None, description="Minimum binding enthalpy (units: eV)"
        ),
        binding_enthalpy_max: Optional[float] = Query(
            None, description="Maximum binding enthalpy (units: eV)"
        ),
        binding_entropy_min: Optional[float] = Query(
            None, description="Minimum binding entropy (units: eV/K)"
        ),
        binding_entropy_max: Optional[float] = Query(
            None, description="Maximum binding entropy (units: eV/K)"
        ),
        binding_free_energy_min: Optional[float] = Query(
            None, description="Minimum binding free energy (units: eV)"
        ),
        binding_free_energy_max: Optional[float] = Query(
            None, description="Maximum binding free energy (units: eV)"
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        if metal_element:
            crit["binding_data.metal_element"] = metal_element

        d = {
            "metal_partial_charge": [
                metal_partial_charge_min,
                metal_partial_charge_max,
            ],
            "metal_partial_spin": [metal_partial_spin_min, metal_partial_spin_max],
            "metal_assigned_charge": [
                metal_assigned_charge_min,
                metal_assigned_charge_max,
            ],
            "metal_assigned_spin": [metal_assigned_spin_min, metal_assigned_spin_max],
            "number_coordinate_bonds": [
                number_coordinate_bonds_min,
                number_coordinate_bonds_max,
            ],
            "binding_energy": [binding_energy_min, binding_energy_max],
            "binding_enthalpy": [binding_enthalpy_min, binding_enthalpy_max],
            "binding_entropy": [binding_entropy_min, binding_entropy_max],
            "binding_free_energy": [binding_free_energy_min, binding_free_energy_max],
        }

        for entry in d:
            key = "binding_data." + entry
            if d[entry][0] is not None or d[entry][1] is not None:  # type: ignore
                crit[key] = dict()

            if d[entry][0] is not None:  # type: ignore
                crit[key]["$gte"] = d[entry][0]  # type: ignore

            if d[entry][1] is not None:  # type: ignore
                crit[key]["$lte"] = d[entry][1]  # type: ignore

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("binding_data.metal_element", False),
            ("binding_data.metal_partial_charge", False),
            ("binding_data.metal_partial_spin", False),
            ("binding_data.metal_assigned_charge", False),
            ("binding_data.metal_assigned_spin", False),
            ("binding_data.number_coordinate_bonds", False),
            ("binding_data.binding_energy", False),
            ("binding_data.binding_enthalpy", False),
            ("binding_data.binding_entropy", False),
            ("binding_data.binding_free_energy", False),
        ]
