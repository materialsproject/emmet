""" Core definition of a Materials Document """
from datetime import datetime
from functools import partial
from typing import ClassVar, Dict, List, Optional, Union

from pydantic import BaseModel, Field, create_model
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer, Ordering

from emmet.core.structure import StructureMetadata
from emmet.core.utils import CalcType, RunType, TaskType
from emmet.stubs import Structure


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The property name")
    task_id: str = Field(..., description="The calculation ID this property comes from")
    task_type: str = Field(
        ..., description="The original calculation type this propeprty comes from"
    )
    last_updated: datetime = Field(
        description="The timestamp when this calculation was last updated",
        default_factory=datetime.utcnow,
    )


class PropertyDoc(BaseModel):
    """
    Base model definition for any singular materials property. This may contain any amount
    of structure metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    property_name: ClassVar[str] = None
    material_id: str = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    origins: List[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties"
    )

    warnings: List[str] = Field(
        None, description="Any warnings related to this property"
    )

    sandboxes: List[str] = Field(
        ["core"],
        description="List of sandboxes this property belongs to."
        " Sandboxes provide a way of controlling access to materials."
        " No sandbox means this materials is openly visible",
    )


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
        True, description="Whether this materials document is deprecated.",
    )

    initial_structures: List[Structure] = Field(
        [],
        description="Initial structures used in the DFT optimizations corresponding to this material",
    )

    task_ids: List[str] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Materials Document",
    )

    deprecated_tasks: List[str] = Field([], title="Deprecated Tasks")

    calc_types: Dict[str, str] = Field(
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

    origins: List[PropertyOrigin] = Field(
        None, description="Dictionary for tracking the provenance of properties"
    )

    warnings: List[str] = Field([], description="Any warnings related to this material")

    sandboxes: List[str] = Field(
        ["core"],
        description="List of sandboxes this material belongs to."
        " Sandboxes provide a way of controlling access to materials."
        " Core is the primary sandbox for fully open documents",
    )

    @classmethod
    def from_structure(  # type: ignore[override]
        cls, structure: Structure, material_id: str, **kwargs
    ) -> "MaterialsDoc":
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(
            structure=structure, material_id=material_id, include_structure=True
        )
