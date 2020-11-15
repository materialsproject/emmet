""" Core definitions of Molecules-related documents """

from datetime import datetime

from typing import (
    Mapping,
    Sequence,
    TypeVar,
)

from pydantic import Field
from emmet.stubs import Composition, Molecule
from emmet.core.qchem.mol_metadata import MoleculeMetadata


S = TypeVar("S", bound="MoleculeDoc")


class MoleculeDoc(MoleculeMetadata):
    """
    Definition for a Molecule Document
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    molecule: Molecule = Field(
        ..., description="The lowest-energy optimized structure for this molecule"
    )

    task_ids: Sequence[str] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Molecule Document",
    )

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this molecule",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this molecule document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this molecule document was first created",
        default_factory=datetime.utcnow,
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this molecule"
    )
