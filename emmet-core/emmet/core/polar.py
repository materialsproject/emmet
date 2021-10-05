""" Core definition for Polar property Document """
from typing import Tuple
from emmet.core.mpid import MPID

import numpy as np
from pydantic import Field
from pymatgen.analysis.piezo import PiezoTensor as BasePiezoTensor

from emmet.core import SETTINGS
from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D
from pymatgen.core.structure import Structure
from pymatgen.core.tensors import Tensor

VoigtVector = Tuple[float, float, float, float, float, float]
PiezoTensor = Tuple[VoigtVector, VoigtVector, VoigtVector]
PiezoTensor.__doc__ = "Rank 3 real space tensor in Voigt notation"  # type: ignore


class DielectricDoc(PropertyDoc):
    """
    A dielectric property block
    """

    property_name = "dielectric"

    total: Tensor = Field(description="Total dielectric response")
    ionic: Tensor = Field(description="Dielectric response due to atomic rearrangement")
    electronic: Tensor = Field(
        description="Dielectric response due to electron rearrangement"
    )

    e_total: float = Field(description="Total electric permittivity")
    e_ionic: float = Field(
        description="Electric permittivity from atomic rearrangement"
    )
    e_electronic: float = Field(
        description="Electric permittivity due to electrons rearrangement"
    )

    n: float = Field(title="Refractive index")

    @classmethod
    def from_ionic_and_electronic(
        cls,
        material_id: MPID,
        ionic: Matrix3D,
        electronic: Matrix3D,
        structure: Structure,
        **kwargs,
    ):

        ionic = Tensor(ionic).convert_to_ieee(structure)
        electronic = Tensor(electronic).convert_to_ieee(structure)

        total = ionic + electronic

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **{
                "total": total,
                "ionic": ionic,
                "electronic": electronic,
                "e_total": np.average(np.diagonal(total)),
                "e_ionic": np.average(np.diagonal(ionic)),
                "e_electronic": np.average(np.diagonal(electronic)),
                "n": np.sqrt(np.average(np.diagonal(electronic))),
            },
            **kwargs,
        )


class PiezoelectricDoc(PropertyDoc):
    """
    A dielectric package block
    """

    property_name = "piezoelectric"

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

    @classmethod
    def from_ionic_and_electronic(
        cls, ionic: PiezoTensor, electronic: PiezoTensor, **kwargs
    ):

        total = BasePiezoTensor.from_voigt(np.sum(ionic, electronic))  # type: ignore

        directions, charges, strains = np.linalg.svd(total, full_matrices=False)
        max_index = np.argmax(np.abs(charges))

        max_direction = directions[max_index]

        # Allow a max miller index of 10
        min_val = np.abs(max_direction)
        min_val = min_val[min_val > (np.max(min_val) / SETTINGS.MAX_PIEZO_MILLER)]
        min_val = np.min(min_val)

        return cls(
            **{
                "total": total.zeroed().voigt,
                "ionic": ionic,
                "static": electronic,
                "e_ij_max": charges[max_index],
                "max_direction": np.round(max_direction / min_val),
                "strain_for_max": strains[max_index],
            },
            **kwargs,
        )
