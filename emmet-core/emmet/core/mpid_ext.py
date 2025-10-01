"""Define extensions of the MPID class which are used throughout emmet."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pymatgen.core import Element

from emmet.core.mpid import MPID, AlphaID
from emmet.core.types.enums import ThermoType
from emmet.core.types.typing import IdentifierType
from emmet.core.types.enums import XasType, XasEdge
from emmet.core.utils import type_override
from emmet.core.vasp.calc_types import RunType

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self


class SuffixedID(BaseModel):
    """Handle suffixed identifier formats (ex., thermo IDs)."""

    identifier: IdentifierType
    suffix: Enum
    separator: str = Field(default="_")

    @classmethod
    def from_str(cls, idx: str) -> Self:
        """Ensure the class can be instantiated from a string or dict."""
        sep = cls.model_fields["separator"].default
        parts = idx.split(sep, 1)
        return cls(
            identifier=parts[0],
            suffix=parts[1],  # type: ignore[arg-type]
        )

    def __str__(self) -> str:
        """Format as a string."""
        return self.separator.join([self.identifier.string, self.suffix.value])

    @classmethod
    def _deserialize(cls, v: Any) -> Self:
        """Utility to parse values into a suffixed ID from various formats."""
        if isinstance(v, cls):
            return v
        elif isinstance(v, str):
            return cls.from_str(v)
        elif isinstance(v, dict):
            return cls(**v)
        else:
            raise ValueError(f"{cls.__name__} cannot deserialize input type {type(v)}.")


class ThermoID(SuffixedID):
    """Thermodynamic data identifier."""

    suffix: ThermoType | RunType


class BatteryID(SuffixedID):
    """Identify battery / electrode data."""

    suffix: Element


@type_override({"suffix": str})
class XasSpectrumID(SuffixedID):
    suffix: tuple[XasType, Element, XasEdge]  # type: ignore[assignment]
    separator: str = Field(default="-")

    @classmethod
    def from_str(cls, idx: str) -> Self:
        """Ensure the class can be instantiated from a string or dict."""
        sep = cls.model_fields["separator"].default
        for i in range(2):
            if len(parts := idx.rsplit(sep, idx.count(sep) - i)) == 4:
                break
        return cls(
            identifier=parts[0],
            suffix=parts[1:],  # type: ignore[arg-type]
        )

    def __str__(self) -> str:
        """Format as a string."""
        return self.separator.join(
            [self.identifier.string, *(e.value for e in self.suffix)]
        )


def validate_identifier(
    idx: str | MPID | AlphaID | SuffixedID, serialize: bool = False
) -> str | MPID | AlphaID | SuffixedID:
    """Format an input string or identifier as a valid Materials Project format identifier.

    Parameters
    -----------
    idx : str or MPID or AlphaID or SuffixedID
        The input identifier, can either be an already instantiated
        identifier object, or a plain string
    serialize : bool = False
        If True, returns the string representation of the identifier object.
        If False, returns the object.
    """

    for id_cls in (AlphaID, *SuffixedID.__subclasses__()):
        try:
            parsed_idx = (
                AlphaID(idx).formatted
                if id_cls == AlphaID
                else id_cls._deserialize(idx)
            )
            break
        except Exception:
            continue
    else:
        raise ValueError(
            f"Invalid identifier {idx}, must be one of MPID, AlphaID, ThermoID, BatteryID, or XasSpectrumID."
        )

    if serialize:
        return (
            str(AlphaID(parsed_idx))
            if isinstance(parsed_idx, MPID | AlphaID)
            else str(parsed_idx)
        )
    return parsed_idx
