""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import ClassVar, Mapping, Optional, Sequence, Type, TypeVar, Union

from pydantic import BaseModel, Field, create_model
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer, Ordering

from emmet.core.structure import StructureMetadata
from emmet.stubs import Structure


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The property name")
    task_id: str = Field(..., description="The calculation ID this property comes from")
    last_updated: datetime = Field(
        description="The timestamp when this calculation was last updated",
        default_factory=datetime.utcnow,
    )


T = TypeVar("T", bound="MaterialsDoc")


class MaterialsDoc(StructureMetadata):
    """
    Definition for a core Materials Document
    """

    # Only material_id is required for all documents
    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    structure: Structure = Field(
        ..., description="The best structure for this material"
    )

    deprecated: bool = Field(
        True,
        description="Whether this materials document is deprecated.",
    )

    initial_structures: Sequence[Structure] = Field(
        [],
        description="Initial structures used in the DFT optimizations corresponding to this material",
    )

    task_ids: Sequence[str] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Materials Document",
    )

    deprecated_tasks: Sequence[str] = Field([], title="Deprecated Tasks")

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this material",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )

    origins: Sequence[PropertyOrigin] = Field(
        None, description="Dictionary for tracking the provenance of properties"
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this material"
    )

    sandboxes: Sequence[str] = Field(
        ["core"],
        description="List of sandboxes this material belongs to."
        " Sandboxes provide a way of controlling access to materials."
        " Core is the primary sandbox for fully open documents",
    )

    @classmethod
    def from_structure(  # type: ignore[override]
        cls: Type[T], structure: Structure, material_id: str, **kwargs
    ) -> T:
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(  # type: ignore
            structure=structure,
            material_id=material_id,
            include_structure=True,
            **kwargs
        )
