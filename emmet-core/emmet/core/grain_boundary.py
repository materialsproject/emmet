from typing import List, Optional
from pydantic import field_validator, BaseModel, Field
from enum import Enum
from datetime import datetime
from monty.json import MontyDecoder

from pymatgen.analysis.gb.grain import GrainBoundary


class GBTypeEnum(Enum):
    """
    Grain boundary types
    """

    tilt = "tilt"
    twist = "twist"


class GrainBoundaryDoc(BaseModel):
    """
    Grain boundary energies, work of separation...
    """

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    sigma: Optional[int] = Field(
        None,
        description="Sigma value of the boundary.",
    )

    type: Optional[GBTypeEnum] = Field(
        None,
        description="Grain boundary type.",
    )

    rotation_axis: Optional[List[int]] = Field(
        None,
        description="Rotation axis.",
    )

    gb_plane: Optional[List[int]] = Field(
        None,
        description="Grain boundary plane.",
    )

    rotation_angle: Optional[float] = Field(
        None,
        description="Rotation angle in degrees.",
    )

    gb_energy: Optional[float] = Field(
        None,
        description="Grain boundary energy in J/m^2.",
    )

    initial_structure: Optional[GrainBoundary] = Field(
        None, description="Initial grain boundary structure."
    )

    final_structure: Optional[GrainBoundary] = Field(
        None, description="Final grain boundary structure."
    )

    pretty_formula: Optional[str] = Field(
        None, description="Reduced formula of the material."
    )

    w_sep: Optional[float] = Field(None, description="Work of separation in J/m^2.")

    cif: Optional[str] = Field(None, description="CIF file of the structure.")

    chemsys: Optional[str] = Field(
        None, description="Dash-delimited string of elements in the material."
    )

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this Material document.",
    )

    # Make sure that the datetime field is properly formatted
    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)
