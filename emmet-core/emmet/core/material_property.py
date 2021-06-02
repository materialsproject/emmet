""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Sequence, Type, TypeVar

from pydantic import Field
from pymatgen.core import Structure

from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata

S = TypeVar("S", bound="PropertyDoc")


class PropertyDoc(StructureMetadata):
    """
    Base model definition for any singular materials property. This may contain any amount
    of structure metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    property_name: ClassVar[str]
    material_id: MPID = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form of an MPID or int",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    origins: Sequence[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties"
    )

    warnings: Sequence[str] = Field(
        None, description="Any warnings related to this property"
    )

    @classmethod
    def from_structure(  # type: ignore[override]
        cls: Type[S], structure: Structure, material_id: MPID, **kwargs
    ) -> S:
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(  # type: ignore
            structure=structure,
            material_id=material_id,
            include_structure=False,
            **kwargs
        )
