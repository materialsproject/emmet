""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from typing import List, Mapping, Type, TypeVar, Union

from pydantic import BaseModel, Field

from pymatgen.core import Structure
from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.structure import MoleculeMetadata, StructureMetadata
from emmet.core.vasp.validation import DeprecationMessage


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The property name")
    task_id: MPID = Field(
        ..., description="The calculation ID this property comes from"
    )
    last_updated: datetime = Field(
        description="The timestamp when this calculation was last updated",
        default_factory=datetime.utcnow,
    )


T = TypeVar("T", bound="MaterialsDoc")
S = TypeVar("S", bound="MoleculeDoc")


class MaterialsDoc(StructureMetadata):
    """
    Definition for a core Materials Document
    """

    # Only material_id is required for all documents
    material_id: MPID = Field(
        ...,
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

    deprecation_reasons: List[Union[DeprecationMessage, str]] = Field(
        None,
        description="List of deprecation tags detailing why this materials document isn't valid.",
    )

    initial_structures: List[Structure] = Field(
        [],
        description="Initial structures used in the DFT optimizations corresponding to this material.",
    )

    task_ids: List[MPID] = Field(
        [],
        description="List of Calculations IDs used to make this Materials Document.",
    )

    deprecated_tasks: List[str] = Field([], title="Deprecated Tasks")

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this material.",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated.",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created.",
        default_factory=datetime.utcnow,
    )

    origins: List[PropertyOrigin] = Field(
        None, description="Dictionary for tracking the provenance of properties."
    )

    warnings: List[str] = Field(
        [], description="Any warnings related to this material."
    )

    @classmethod
    def from_structure(cls: Type[T], structure: Structure, material_id: MPID, **kwargs) -> T:  # type: ignore[override]
        """
        Builds a materials document using the minimal amount of information
        """

        return super().from_structure(  # type: ignore
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **kwargs,
        )


class MoleculeDoc(MoleculeMetadata):
    """
    Definition for a core Molecule Document
    """

    # Only molecule_id is required for all documents
    molecule_id: MPID = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across property documents."
        "This comes in the form of an MPID or int",
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
    deprecation_reasons: List[str] = Field(
        None,
        description="List of deprecation tags detailing why this molecules document isn't valid",
    )

    initial_molecules: List[Molecule] = Field(
        [],
        description="Initial molecules used in the DFT geometry optimizations corresponding to this molecule",
    )

    task_ids: List[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Molecule Document",
    )

    # TODO: Should this be MPID?
    deprecated_tasks: List[str] = Field([], title="Deprecated Tasks")

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the tasks that make up this molecule",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this document was first created",
        default_factory=datetime.utcnow,
    )

    origins: List[PropertyOrigin] = Field(
        None, description="Dictionary for tracking the provenance of properties"
    )

    warnings: List[str] = Field([], description="Any warnings related to this molecule")

    @classmethod
    def from_molecule(cls: Type[S], molecule: Molecule, molecule_id: MPID, **kwargs) -> S:  # type: ignore[override]
        """
        Builds a molecule document using the minimal amount of information
        """

        return super().from_molecule(  # type: ignore
            meta_molecule=molecule, molecule_id=molecule_id, molecule=molecule, **kwargs
        )
