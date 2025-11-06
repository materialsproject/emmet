"""Core definition of a Materials Document"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pymatgen.core import Structure
from pymatgen.core.structure import Molecule

from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID, MPculeID
from emmet.core.structure import MoleculeMetadata, StructureMetadata
from emmet.core.types.enums import DeprecationMessage
from emmet.core.types.pymatgen_types.structure_adapter import (
    MoleculeType,
    StructureType,
)
from emmet.core.types.typing import DateTimeType, IdentifierType

if TYPE_CHECKING:

    from typing_extensions import Self


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The property name")
    task_id: IdentifierType = Field(
        ..., description="The calculation ID this property comes from."
    )
    last_updated: DateTimeType = Field(  # type: ignore
        description="The timestamp when this calculation was last updated",
    )


class BasePropertyMetadata(StructureMetadata, EmmetBaseModel):
    """
    Base model definition for a single material property.

    This may contain any amount of structure metadata for the
    purpose of search. This is intended to be inherited and
    extended, not used directly
    """

    material_id: IdentifierType | None = Field(
        None,
        description="The Materials Project ID of the material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    deprecated: bool = Field(
        True,
        description="Whether this property document is deprecated.",
    )

    deprecation_reasons: list[DeprecationMessage | str] | None = Field(
        None,
        description="List of deprecation tags detailing why this document isn't valid.",
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation update for this property.",
    )

    origins: list[PropertyOrigin] | None = Field(
        None, description="Dictionary for tracking the provenance of properties."
    )

    warnings: list[str] = Field(
        [], description="Any warnings related to this property."
    )

    structure: StructureType | None = Field(
        ...,
        description="The structure of the this material.",
    )

    @classmethod
    def from_structure(  # type: ignore[override]
        cls,
        meta_structure: Structure,
        material_id: IdentifierType | None = None,
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


class MaterialsDoc(BasePropertyMetadata):
    """
    Definition for a core Materials Document
    """

    initial_structures: list[StructureType] = Field(
        [],
        description="Initial structures used in the DFT optimizations corresponding to this material.",
    )

    task_ids: list[IdentifierType] = Field(
        [],
        description="List of Calculations IDs used to make this Materials Document.",
    )

    deprecated_tasks: list[str] = Field([], title="Deprecated Tasks")

    calc_types: dict[str, str] | None = Field(
        None,
        description="Calculation types for all the calculations that make up this material.",
    )

    created_at: DateTimeType = Field(
        description="Timestamp for when this material document was first created.",
    )


class CoreMoleculeDoc(MoleculeMetadata, EmmetBaseModel):
    """
    Definition for a core Molecule Document
    """

    # Only molecule_id is required for all documents
    molecule_id: MPculeID = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across property documents."
        "This comes in the form of an MPID (or int) or MPculeID (or str)",
    )

    molecule: MoleculeType = Field(
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

    initial_molecules: list[MoleculeType] = Field(
        [],
        description="Initial molecules used in the DFT geometry optimizations corresponding to this molecule",
    )

    task_ids: list[MPID | MPculeID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Molecule Document",
    )

    # TODO: Should this be MPID?
    deprecated_tasks: list[str] = Field([], title="Deprecated Tasks")

    calc_types: dict[str, str] | None = Field(
        None,
        description="Calculation types for all the tasks that make up this molecule",
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for when this document was last updated",
    )

    created_at: DateTimeType = Field(
        description="Timestamp for when this document was first created",
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
