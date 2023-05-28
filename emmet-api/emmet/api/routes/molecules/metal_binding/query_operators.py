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
        min_metal_partial_charge: Optional[float] = Query(
            None, description="Minimum metal partial charge."
        ),
        max_metal_partial_charge: Optional[float] = Query(
            None, description="Maximum metal partial charge."
        ),
        min_metal_partial_spin: Optional[float] = Query(
            None,
            description="Minimum metal partial spin (only meaningful for open-shell systems).",
        ),
        max_metal_partial_spin: Optional[float] = Query(
            None,
            description="Maximum metal partial spin (only meaningful for open-shell systems).",
        ),
        min_metal_assigned_charge: Optional[float] = Query(
            None,
            description="Minimum charge of the metal, determined by analyzing partial charges/spins.",
        ),
        max_metal_assigned_charge: Optional[float] = Query(
            None,
            description="Maximum charge of the metal, determined by analyzing partial charges/spins.",
        ),
        min_metal_assigned_spin: Optional[Union[int, float]] = Query(
            None,
            description="Minimum spin multiplicity of the metal, determined by analyzing partial spins.",
        ),
        max_metal_assigned_spin: Optional[Union[int, float]] = Query(
            None,
            description="Maximum spin multiplicity of the metal, determined by analyzing partial spins.",
        ),
        min_number_coordinate_bonds: Optional[int] = Query(
            None, description="Minimum number of atoms coordinated to the metal."
        ),
        max_number_coordinate_bonds: Optional[int] = Query(
            None, description="Maximum number of atoms coordinated to the metal."
        ),
        min_binding_energy: Optional[float] = Query(
            None, description="Minimum binding electronic energy (units: eV)"
        ),
        max_binding_energy: Optional[float] = Query(
            None, description="Maximum binding electronic energy (units: eV)"
        ),
        min_binding_enthalpy: Optional[float] = Query(
            None, description="Minimum binding enthalpy (units: eV)"
        ),
        max_binding_enthalpy: Optional[float] = Query(
            None, description="Maximum binding enthalpy (units: eV)"
        ),
        min_binding_entropy: Optional[float] = Query(
            None, description="Minimum binding entropy (units: eV/K)"
        ),
        max_binding_entropy: Optional[float] = Query(
            None, description="Maximum binding entropy (units: eV/K)"
        ),
        min_binding_free_energy: Optional[float] = Query(
            None, description="Minimum binding free energy (units: eV)"
        ),
        max_binding_free_energy: Optional[float] = Query(
            None, description="Maximum binding free energy (units: eV)"
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        if metal_element:
            crit["binding_data.metal_element"] = metal_element

        d = {
            "metal_partial_charge": [
                min_metal_partial_charge,
                max_metal_partial_charge,
            ],
            "metal_partial_spin": [min_metal_partial_spin, max_metal_partial_spin],
            "metal_assigned_charge": [
                min_metal_assigned_charge,
                max_metal_assigned_charge,
            ],
            "metal_assigned_spin": [min_metal_assigned_spin, max_metal_assigned_spin],
            "number_coordinate_bonds": [
                min_number_coordinate_bonds,
                max_number_coordinate_bonds,
            ],
            "binding_energy": [min_binding_energy, max_binding_energy],
            "binding_enthalpy": [min_binding_enthalpy, max_binding_enthalpy],
            "binding_entropy": [min_binding_entropy, max_binding_entropy],
            "binding_free_energy": [min_binding_free_energy, max_binding_free_energy],
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
