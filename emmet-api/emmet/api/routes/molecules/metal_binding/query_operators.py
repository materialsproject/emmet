from typing import Any, Optional
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
            None,
            description="Minimum metal partial charge."
        ),
        max_metal_partial_charge: Optional[float] = Query(
            None,
            description="Maximum metal partial charge."
        ),
        min_metal_partial_spin: Optional[float] = Query(
            None,
            description="Minimum metal partial spin (only meaningful for open-shell systems)."
        ),
        max_metal_partial_spin: Optional[float] = Query(
            None,
            description="Maximum metal partial spin (only meaningful for open-shell systems)."
        ),
        min_metal_assigned_charge: Optional[float] = Query(
            None,
            description="Minimum charge of the metal, determined by analyzing partial charges/spins."
        ),
        max_metal_assigned_charge: Optional[float] = Query(
            None,
            description="Maximum charge of the metal, determined by analyzing partial charges/spins."
        ),
        min_metal_assigned_spin: Optional[int | float] = Query(
            None,
            description="Minimum spin multiplicity of the metal, determined by analyzing partial spins."
        ),
        max_metal_assigned_spin: Optional[int | float] = Query(
            None,
            description="Maximum spin multiplicity of the metal, determined by analyzing partial spins."
        ),
        min_number_coordinate_bonds: Optional[int] = Query(
            None,
            description="Minimum number of atoms coordinated to the metal."
        ),
        max_number_coordinate_bonds: Optional[int] = Query(
            None,
            description="Maximum number of atoms coordinated to the metal."
        ),
        min_binding_energy: Optional[float] = Query(
            None,
            description="Minimum binding electronic energy (units: eV)"
        ),
        max_binding_energy: Optional[float] = Query(
            None,
            description="Maximum binding electronic energy (units: eV)"
        ),
        min_binding_enthalpy: Optional[float] = Query(
            None,
            description="Minimum binding enthalpy (units: eV)"
        ),
        max_binding_enthalpy: Optional[float] = Query(
            None,
            description="Maximum binding enthalpy (units: eV)"
        ),
        min_binding_entropy: Optional[float] = Query(
            None,
            description="Minimum binding entropy (units: eV/K)"
        ),
        max_binding_entropy: Optional[float] = Query(
            None,
            description="Maximum binding entropy (units: eV/K)"
        ),
        min_binding_free_energy: Optional[float] = Query(
            None,
            description="Minimum binding free energy (units: eV)"
        ),
        max_binding_free_energy: Optional[float] = Query(
            None,
            description="Maximum binding free energy (units: eV)"
        )
    ) -> STORE_PARAMS:

        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "oxidation_potentials": [min_oxidation_potential, max_oxidation_potential],
            "reduction_potentials": [min_reduction_potential, max_reduction_potential]
        }

        for entry in d:
            key = entry + "." + electrode
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("oxidation_potentials", False),
            ("reduction_potentials", False),
        ]
