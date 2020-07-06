""" Core definition for Polar property Document """
from typing import List, Dict, ClassVar, Tuple
from datetime import datetime

from pydantic import BaseModel, Field

from emmet.stubs import Matrix3D, Vector3D
from emmet.core.structure import StructureMetadata
from emmet.core.material import PropertyDoc

import numpy as np


class Dielectric(PropertyDoc):
    """
    A dielectric property block
    """

    property_name: ClassVar[str] = Field(
        "dielectric", description="The subfield name for this property"
    )

    total: Matrix3D = Field(None, description="Total dielectric response")
    ionic: Matrix3D = Field(
        None, description="Dielectric response due to atomic rearrangement"
    )
    electronic: Matrix3D = Field(
        None, description="Dielectric response due to electron rearrangement"
    )

    e_total: float = Field(None, description="Total electric permittivity")
    e_ionic: float = Field(
        None, description="Electric permittivity from atomic rearrangement"
    )
    e_electronic: float = Field(
        None, description="Electric permittivity due to electrons rearrangement"
    )

    n: float = Field(None, title="Refractive index")


VoigtVector = Tuple[float, float, float, float, float, float]
PiezoTensor = Tuple[VoigtVector, VoigtVector, VoigtVector]
PiezoTensor.__doc__ = "Rank 3 real space tensor in Voigt notation"  # type: ignore


class Piezoelectric(PropertyDoc):
    """
    A dielectric package block
    """

    property_name: ClassVar[str] = Field(
        "piezo", description="The subfield name for this property"
    )

    total: PiezoTensor = Field(None, description="")
    ionic: PiezoTensor = Field(None, description="")
    electronic: PiezoTensor = Field(None, description="")

    e_ij_max: float = Field(None, description="")
    max_direction: Tuple[int, int, int] = Field(
        None, description="Miller direction for maximum piezo response"
    )
    strain_for_max: Matrix3D = Field(
        None, description="Normalized strain direction for maximum piezo repsonse"
    )
