""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import ClassVar, Mapping, Optional, Sequence, Type, TypeVar, Union

from pydantic import BaseModel, Field, create_model
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer, Ordering

from emmet.core.material import PropertyOrigin
from emmet.core.structure import StructureMetadata
from emmet.stubs import Structure

S = TypeVar("S", bound="PropertyDoc")


class PropertyDoc(StructureMetadata):
    """
    Base model definition for any singular materials property. This may contain any amount
    of structure metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    property_name: ClassVar[str]
    material_id: str = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
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
        cls: Type[S], structure: Structure, material_id: str, **kwargs
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
