"""Core definition of a Materials Document"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from pymatgen.core import Structure
from pymatgen.core.structure import Molecule

from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID, AlphaID, MPculeID
from emmet.core.structure import MoleculeMetadata, StructureMetadata
from emmet.core.utils import utcnow
from emmet.core.vasp.validation import DeprecationMessage

if TYPE_CHECKING:
    from typing_extensions import Self


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The property name")
    task_id: AlphaID | MPculeID = Field(
        ..., description="The calculation ID this property comes from"
    )
    last_updated: datetime = Field(  # type: ignore
        description="The timestamp when this calculation was last updated",
        default_factory=utcnow,
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)


class MaterialsDoc(StructureMetadata):
    """
    Definition for a core Materials Document
    """

    material_id: AlphaID | None = Field(
        None,
        description="The Materials Project ID of the material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    structure: Structure = Field(
        ...,
        description="The structure of the this material.",
    )

    deprecated: bool = Field(
        True,
        description="Whether this materials document is deprecated.",
    )

    deprecation_reasons: list[DeprecationMessage | str] | None = Field(
        None,
        description="List of deprecation tags detailing why this materials document isn't valid.",
    )

    initial_structures: list[Structure] = Field(
        [],
        description="Initial structures used in the DFT optimizations corresponding to this material.",
    )

    task_ids: list[AlphaID] = Field(
        [],
        description="List of Calculations IDs used to make this Materials Document.",
    )

    deprecated_tasks: list[str] = Field([], title="Deprecated Tasks")

    calc_types: Mapping[str, str] | None = Field(
        None,
        description="Calculation types for all the calculations that make up this material.",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated.",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created.",
        default_factory=utcnow,
    )

    origins: list[PropertyOrigin] | None = Field(
        None, description="Dictionary for tracking the provenance of properties."
    )

    warnings: list[str] = Field(
        [], description="Any warnings related to this material."
    )

    @classmethod
    def from_structure(
        cls, structure: Structure, material_id: AlphaID | MPID | None = None, **kwargs
    ) -> Self:  # type: ignore[override]
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(  # type: ignore
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **kwargs,
        )

    @field_validator("last_updated", "created_at", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)


class CoreMoleculeDoc(MoleculeMetadata):
    """
    Definition for a core Molecule Document
    """

    # Only molecule_id is required for all documents
    molecule_id: MPculeID = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across property documents."
        "This comes in the form of an MPID (or int) or MPculeID (or str)",
    )

    molecule: Molecule = Field(
        ...,
        description="The best (typically meaning lowest in energy) structure for this molecule",
    )

    deprecated: bool = Field(
        True,
        description="Whether this molecule document is deprecated.",
    )

    # TODO: Why might a molecule be deprecated?
    deprecation_reasons: list[str] | None = Field(
        None,
        description="List of deprecation tags detailing why this molecules document isn't valid",
    )

    initial_molecules: list[Molecule] = Field(
        [],
        description="Initial molecules used in the DFT geometry optimizations corresponding to this molecule",
    )

    task_ids: list[MPID | AlphaID | MPculeID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Molecule Document",
    )

    # TODO: Should this be MPID?
    deprecated_tasks: list[str] = Field([], title="Deprecated Tasks")

    calc_types: Mapping[str, str] | None = Field(
        None,
        description="Calculation types for all the tasks that make up this molecule",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this document was first created",
        default_factory=utcnow,
    )

    origins: list[PropertyOrigin] | None = Field(
        None, description="Dictionary for tracking the provenance of properties"
    )

    warnings: list[str] = Field([], description="Any warnings related to this molecule")

    @classmethod
    def from_molecule(
        cls, molecule: Molecule, molecule_id: MPculeID, **kwargs
    ) -> Self:  # type: ignore[override]
        """
        Builds a molecule document using the minimal amount of information
        """

        return super().from_molecule(  # type: ignore
            meta_molecule=molecule, molecule_id=molecule_id, molecule=molecule, **kwargs
        )

    @field_validator("last_updated", "created_at", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)
