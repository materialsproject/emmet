"""Define enums with custom de-/serialization behavior.

Note that only the base classes for enums and enums
that are used widely across the code base should be
put here.

For example, `ValueEnum` is defined here, with custom
pydantic serialization features.

Similarly, `TaskState` is used across many sub-modules
in `emmet-core` and therefore is defined here.

Enums which only have one purpose / exist only within
one module, can and should remain in that module.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic_core import CoreSchema, core_schema

if TYPE_CHECKING:
    from typing import Any

    from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
    from typing_extensions import Self


class ValueEnum(Enum):
    """
    Enum that serializes to string as the value.

    While this method has an `as_dict` method, this
    returns a `str`. This is to ensure deserialization
    to a `str` when functions like `monty.json.jsanitize`
    are called on a ValueEnum with `strict = True` and
    `enum_values = False` (occurs often in jobflow).
    """

    def __str__(self):
        return str(self.value)

    def __eq__(self, obj: object) -> bool:
        """Special Equals to enable converting strings back to the enum"""
        if isinstance(obj, str):
            return super().__eq__(self.__class__(obj))
        elif isinstance(obj, self.__class__):
            return super().__eq__(obj)
        return False

    def __hash__(self):
        """Get a hash of the enum."""
        return hash(str(self))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Ensure pydantic (de)serialization."""

        from_str_schema = core_schema.chain_schema(
            [
                core_schema.str_schema(),
                core_schema.with_info_plain_validator_function(cls.validate),
            ]
        )
        return core_schema.json_or_python_schema(
            json_schema=from_str_schema,
            python_schema=from_str_schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.value
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        json_schema = handler(core_schema.str_schema())
        json_schema = handler.resolve_ref_schema(json_schema)
        return json_schema

    @classmethod
    def validate(cls, __input_value: Any, _: core_schema.ValidationInfo) -> Self:
        """Define pydantic validator for emmet enums."""
        if isinstance(__input_value, str):
            return (
                cls[__input_value]
                if __input_value in cls.__members__
                else cls(__input_value)
            )
        elif isinstance(__input_value, ValueEnum):
            return __input_value  # type: ignore[return-value]
        raise ValueError(f"Invalid {cls.__name__}: {__input_value}")


class DocEnum(ValueEnum):
    """
    Enum with docstrings support
    from: https://stackoverflow.com/a/50473952
    """

    def __new__(cls, value, doc=None):
        """add docstring to the member of Enum if exists

        Args:
            value: Enum member value
            doc: Enum member docstring, None if not exists
        """
        self = object.__new__(cls)  # calling super().__new__(value) here would fail
        self._value_ = value
        if doc is not None:
            self.__doc__ = doc
        return self


class IgnoreCaseEnum(ValueEnum):
    """Enum that permits case-insensitve lookup.

    Reference issue:
    https://github.com/materialsproject/api/issues/869
    """

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.upper() == value.upper():
                return member


class VaspObject(ValueEnum):
    """Types of VASP data objects."""

    BANDSTRUCTURE = "bandstructure"
    DOS = "dos"
    CHGCAR = "chgcar"
    AECCAR0 = "aeccar0"
    AECCAR1 = "aeccar1"
    AECCAR2 = "aeccar2"
    TRAJECTORY = "trajectory"
    ELFCAR = "elfcar"
    WAVECAR = "wavecar"
    LOCPOT = "locpot"
    OPTIC = "optic"
    PROCAR = "procar"


class StoreTrajectoryOption(ValueEnum):
    FULL = "full"
    PARTIAL = "partial"
    NO = "no"


class TaskState(ValueEnum):
    """
    VASP Calculation State
    """

    SUCCESS = "successful"
    FAILED = "failed"
    ERROR = "error"


class DeprecationMessage(DocEnum):
    MANUAL = "M", "Manual deprecation"
    SYMMETRY = (
        "S001",
        "Could not determine crystalline space group, needed for input set check.",
    )
    KPTS = "C001", "Too few KPoints"
    KSPACING = "C002", "KSpacing not high enough"
    ENCUT = "C002", "ENCUT too low"
    FORCES = "C003", "Forces too large"
    MAG = "C004", "At least one site magnetization is too large"
    POTCAR = (
        "C005",
        "At least one POTCAR used does not agree with the pymatgen input set",
    )
    CONVERGENCE = "E001", "Calculation did not converge"
    MAX_SCF = "E002", "Max SCF gradient too large"
    LDAU = "I001", "LDAU Parameters don't match the inputset"
    SET = ("I002", "Cannot validate due to missing or problematic input set")
    UNKNOWN = "U001", "Cannot validate due to unknown calc type"


class BatteryType(str, ValueEnum):
    """
    Enum for battery type
    """

    insertion = "insertion"
    conversion = "conversion"


class ThermoType(ValueEnum):
    """Thermodynamic hull types used in the database."""

    GGA_GGA_U = "GGA_GGA+U"
    GGA_GGA_U_R2SCAN = "GGA_GGA+U_R2SCAN"
    R2SCAN = "R2SCAN"
    UNKNOWN = "UNKNOWN"


class XasEdge(ValueEnum):
    """
    The interaction edge for XAS
    There are 2n-1 sub-components to each edge where
    K: n=1
    L: n=2
    M: n=3
    N: n=4
    """

    K = "K"
    L2 = "L2"
    L3 = "L3"
    L2_3 = "L2,3"


class XasType(ValueEnum):
    """
    The type of XAS Spectrum
    XANES - Just the near-edge region
    EXAFS - Just the extended region
    XAFS - Fully stitched XANES + EXAFS
    """

    XANES = "XANES"
    EXAFS = "EXAFS"
    XAFS = "XAFS"
