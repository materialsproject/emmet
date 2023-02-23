from emmet.core.mpid import MPID, MPculeID
from pydantic import Field, BaseModel


class FindStructure(BaseModel):
    """
    Class defining find structure return data
    """

    material_id: MPID = Field(
        None,
        description="The ID of this material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )
    normalized_rms_displacement: float = Field(
        None,
        description="Volume normalized root-mean squared displacement between the structures",
    )
    max_distance_paired_sites: float = Field(
        None,
        description="Maximum distance between paired sites.",
    )


class FindMolecule(BaseModel):
    """
    Class defining find molecule return data
    """

    molecule_id: MPculeID = Field(
        None,
        description="The ID of this molecule, used as a universal reference across property documents."
    )
    rmsd: float = Field(
        None,
        description="Root-mean-squared displacement of the molecule compared to a reference",
    )


class FindMoleculeConnectivity(BaseModel):
    """
    Class defining find molecule connectivity return data
    """

    molecule_id: MPculeID = Field(
        None,
        description="The ID of this molecule, used as a universal reference across property documents."
    )
