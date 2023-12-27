from typing import Any, Literal, Optional, Dict
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class MultipoleMomentComponentQuery(QueryOperator):
    """
    Method to generate a query on components of electric multipole moments.
    """

    def query(
        self,
        moment_type: Optional[Literal["dipole", "resp_dipole", "quadrupole", "octopole", "hexadecapole"]] = Query(
            None, description=(
                "Type of multipole moment. Allowed values: 'dipole', 'resp_dipole', 'quadrupole', 'octopole', and "
                "'hexadecapole'"
            )
        ),
        component: Optional[str] = Query(
            None, description="Component to query on, i.e. 'X', 'Y', or 'Z' for dipole moments"
        ),
        min_value: Optional[float] = Query(
            None, description="Minimum value for the multipole moment component"
        ),
        max_value: Optional[float] = Query(
            None, description="Maximum value for the multipole moment component"
        )
    ) -> STORE_PARAMS:
        self.moment_type = moment_type
        self.component = component
        self.min_value = min_value
        self.max_value = max_value

        if self.moment_type is None or self.component is None:
            return {"criteria": dict()}

        allowed_components = {
            "dipole": {"X", "Y", "Z"},
            "resp_dipole": {"X", "Y", "Z"},
            "quadrupole": {"XX", "XY", "YY", "XZ", "YZ", "ZZ"},
            "octopole": {"XXX", "XXY", "XYY", "YYY", "XXZ", "XYZ", "YYZ", "XZZ", "YZZ", "ZZZ"},
            "hexadecapole": {
                "XXXX",
                "XXXY",
                "XXYY",
                "XYYY",
                "YYYY",
                "XXXZ",
                "XXYZ",
                "XYYZ",
                "YYYZ",
                "XXZZ",
                "XYZZ",
                "YYZZ",
                "XZZZ",
                "YZZZ",
                "ZZZZ",
            }
        }

        allowed = allowed_components[self.moment_type]

        if self.component not in allowed:
            raise ValueError(f"Improper component! Allowed components for {self.moment_type} are {allowed}!")

        key_prefix = self.moment_type + "_moment"

        crit: Dict[str, Any] = {key: dict()}  # type: ignore

        if self.moment_type in ["dipole", "resp_dipole"]:
            mapping = {"X": 0, "Y": 1, "Z": 2}
            # TODO: you are here

        if self.min_value is not None:
            crit[key]["$lte"] = max_bond_length
        if min_bond_length is not None:
            crit[key]["$gte"] = min_bond_length

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("correction_level_of_theory", False),
            ("correction_solvent", False),
            ("correction_lot_solvent", False),
            ("combined_lot_solvent", False),
        ]
