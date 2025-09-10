from pydantic import BaseModel, Field

from emmet.core.mpid import MPculeID
from emmet.core.types.typing import IdentifierType


class FindStructure(BaseModel):
    """
    Class defining find structure return data
    """

    material_id: IdentifierType | None = Field(
        None,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )
    normalized_rms_displacement: float | None = Field(
        None,
        description="Volume normalized root-mean squared displacement between the structures",
    )
    max_distance_paired_sites: float | None = Field(
        None,
        description="Maximum distance between paired sites.",
    )


class FindMolecule(BaseModel):
    """
    Class defining find molecule return data
    """

    molecule_id: MPculeID | None = Field(
        None,
        description="The ID of this molecule, used as a universal reference across property documents.",
    )
    rmsd: float | None = Field(
        None,
        description="Root-mean-squared displacement of the molecule compared to a reference",
    )
