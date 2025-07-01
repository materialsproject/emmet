"""Core definition of a Materials Document"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from pymatgen.core import Structure

from emmet.core.common import convert_datetime
from emmet.core.material import PropertyOrigin
from emmet.core.mpid import AlphaID
from emmet.core.structure import StructureMetadata
from emmet.core.utils import utcnow
from emmet.core.vasp.validation import DeprecationMessage

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

    from emmet.core.mpid import MPID


class PropertyDoc(StructureMetadata):
    """
    Base model definition for any singular materials property.

    This may contain any amount of structure metadata for the
    purpose of search. This is intended to be inherited and
    extended, not used directly
    """

    property_name: str
    material_id: AlphaID | None = Field(
        None,
        description="The Materials Project ID of the material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    deprecated: bool = Field(
        ...,
        description="Whether this property document is deprecated.",
    )

    deprecation_reasons: list[DeprecationMessage | str] | None = Field(
        None,
        description="List of deprecation tags detailing why this document isn't valid.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property.",
        default_factory=utcnow,
    )

    origins: Sequence[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties."
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this property."
    )

    structure: SkipJsonSchema[Structure | None] = Field(
        None, description="The structure associated with this property.", exclude=True
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v: Any) -> datetime:
        return convert_datetime(cls, v)

    @classmethod
    def from_structure(  # type: ignore[override]
        cls,
        meta_structure: Structure,
        material_id: AlphaID | MPID | None = None,
        **kwargs,
    ) -> Self:
        """
        Builds a materials document using a minimal amount of information.

        Note that structure is stored as a private attr, and will not
        be included in `PropertyDoc().model_dump()`
        """

        return super().from_structure(
            meta_structure=meta_structure,
            structure=meta_structure,
            material_id=material_id,
            **kwargs,
        )  # type: ignore
