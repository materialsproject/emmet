from emmet.core.mpid import MPID, MPculeID
from pydantic import Field, BaseModel
from typing import Optional


class FindStructure(BaseModel):
    """
    Class defining find structure return data
    """

    material_id: Optional[MPID] = Field(
        None,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )
    normalized_rms_displacement: Optional[float] = Field(
        None,
        description="Volume normalized root-mean squared displacement between the structures",
    )
    max_distance_paired_sites: Optional[float] = Field(
        None,
        description="Maximum distance between paired sites.",
    )


class FindMolecule(BaseModel):
    """
    Class defining find molecule return data
    """

    molecule_id: Optional[MPculeID] = Field(
        None,
        description="The ID of this molecule, used as a universal reference across property documents.",
    )
    rmsd: Optional[float] = Field(
        None,
        description="Root-mean-squared displacement of the molecule compared to a reference",
    )
