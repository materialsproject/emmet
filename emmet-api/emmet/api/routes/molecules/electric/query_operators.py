from typing import Any, Literal

from fastapi import Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS

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
    },
}


class MultipoleMomentComponentQuery(QueryOperator):
    """
    Method to generate a query on components of electric multipole moments.
    """

    def query(
        self,
        moment_type: (
            Literal["dipole", "resp_dipole", "quadrupole", "octopole", "hexadecapole"]
            | None
        ) = Query(
            None,
            description=(
                "Type of multipole moment. Allowed values: 'dipole', 'resp_dipole', 'quadrupole', 'octopole', and "
                "'hexadecapole'"
            ),
        ),
        component: str | None = Query(
            None,
            description="Component to query on, i.e. 'X', 'Y', or 'Z' for dipole moments",
        ),
        component_value_min: float | None = Query(
            None, description="Minimum value for the multipole moment component"
        ),
        component_value_max: float | None = Query(
            None, description="Maximum value for the multipole moment component"
        ),
    ) -> STORE_PARAMS:
        self.moment_type = moment_type
        self.component = component
        self.min_value = component_value_min
        self.max_value = component_value_max

        if self.moment_type is None or self.component is None:
            return {"criteria": dict()}

        allowed = allowed_components[self.moment_type]

        if self.component not in allowed:
            raise ValueError(
                f"Improper component! Allowed components for {self.moment_type} are {allowed}!"
            )

        key_prefix = self.moment_type + "_moment"

        if self.moment_type in ["dipole", "resp_dipole"]:
            mapping = {"X": "0", "Y": "1", "Z": "2"}
            key_suffix = mapping[self.component]
        else:
            key_suffix = self.component

        key = key_prefix + "." + key_suffix

        crit: dict[str, Any] = {key: dict()}  # type: ignore

        if self.min_value is not None and isinstance(self.min_value, float):
            crit[key]["$gte"] = self.min_value
        if self.max_value is not None and isinstance(self.max_value, float):
            crit[key]["$lte"] = self.max_value

        if not isinstance(self.min_value, float) and not isinstance(
            self.max_value, float
        ):
            crit[key]["$exists"] = True

        return {"criteria": crit}

    def ensure_indexes(self):
        # Right now, indexing on all sub-fields of all electric multipole moments
        # TODO: is this necessary? Is this the best way to do this?
        indexes = list()
        for dp in ["dipole_moment", "resp_dipole_moment"]:
            for index in range(3):
                indexes.append((f"{dp}.{index}", False))

        for mp in ["quadrupole", "octopole", "hexadecapole"]:
            for valid_key in allowed_components[mp]:
                indexes.append((f"{mp}_moment.{valid_key}", False))

        return indexes
