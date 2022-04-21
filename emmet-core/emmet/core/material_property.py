""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from typing import Sequence, Type, TypeVar, Union, List

from pydantic import Field
from pymatgen.core import Structure

from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.validation import DeprecationMessage

S = TypeVar("S", bound="PropertyDoc")


class PropertyDoc(StructureMetadata):
    """
    Base model definition for any singular materials property. This may contain any amount
    of structure metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    property_name: str
    material_id: MPID = Field(
        ...,
        description="The Materials Project ID of the material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    deprecated: bool = Field(
        ...,
        description="Whether this property document is deprecated.",
    )

    deprecation_reasons: List[Union[DeprecationMessage, str]] = Field(
        None,
        description="List of deprecation tags detailing why this document isn't valid.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property.",
        default_factory=datetime.utcnow,
    )

    origins: Sequence[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties."
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this property."
    )

    @classmethod
    def from_structure(  # type: ignore[override]
        cls: Type[S], meta_structure: Structure, material_id: MPID, **kwargs
    ) -> S:
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(meta_structure=meta_structure, material_id=material_id, **kwargs)  # type: ignore
