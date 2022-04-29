""" Core definition for Polar property Document """
from typing import Tuple, List
from emmet.core.mpid import MPID

import numpy as np
from pydantic import Field
from pymatgen.analysis.piezo import PiezoTensor as BasePiezoTensor

from emmet.core.settings import EmmetSettings
from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D, Vector3D
from pymatgen.core.structure import Structure
from pymatgen.core.tensors import Tensor

SETTINGS = EmmetSettings()

Vector = List[float]
PiezoTensor = List[Vector]
PiezoTensor.__doc__ = "Rank 3 real space tensor in Voigt notation"  # type: ignore


class DielectricDoc(PropertyDoc):
    """
    A dielectric property block
    """

    property_name = "dielectric"

    total: Matrix3D = Field(description="Total dielectric tensor.")
    ionic: Matrix3D = Field(description="Ionic contribution to dielectric tensor.")
    electronic: Matrix3D = Field(
        description="Electronic contribution to dielectric tensor."
    )

    e_total: float = Field(description="Total electric permittivity.")
    e_ionic: float = Field(
        description="Electric permittivity from atomic rearrangement."
    )
    e_electronic: float = Field(
        description="Electric permittivity due to electrons rearrangement."
    )

    n: float = Field(description="Refractive index.")

    @classmethod
    def from_ionic_and_electronic(
        cls,
        material_id: MPID,
        ionic: Matrix3D,
        electronic: Matrix3D,
        structure: Structure,
        **kwargs,
    ):

        ionic_tensor = Tensor(ionic).convert_to_ieee(structure)
        electronic_tensor = Tensor(electronic).convert_to_ieee(structure)

        total = ionic_tensor + electronic_tensor

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            **{
                "total": total.tolist(),
                "ionic": ionic_tensor.tolist(),
                "electronic": electronic_tensor.tolist(),
                "e_total": np.average(np.diagonal(total)),
                "e_ionic": np.average(np.diagonal(ionic_tensor)),
                "e_electronic": np.average(np.diagonal(electronic_tensor)),
                "n": np.sqrt(np.average(np.diagonal(electronic_tensor))),
            },
            **kwargs,
        )


class PiezoelectricDoc(PropertyDoc):
    """
    A dielectric package block
    """

    property_name = "piezoelectric"

    total: PiezoTensor = Field(description="Total piezoelectric tensor in C/m²")
    ionic: PiezoTensor = Field(
        description="Ionic contribution to piezoelectric tensor in C/m²"
    )
    electronic: PiezoTensor = Field(
        description="Electronic contribution to piezoelectric tensor in C/m²"
    )

    e_ij_max: float = Field(description="Piezoelectric modulus")
    max_direction: List[int] = Field(
        description="Miller direction for maximum piezo response"
    )
    strain_for_max: List[float] = Field(
        description="Normalized strain direction for maximum piezo repsonse"
    )

    @classmethod
    def from_ionic_and_electronic(
        cls,
        material_id: MPID,
        ionic: PiezoTensor,
        electronic: PiezoTensor,
        structure: Structure,
        **kwargs,
    ):

        ionic_tensor = BasePiezoTensor.from_vasp_voigt(ionic)
        electronic_tensor = BasePiezoTensor.from_vasp_voigt(electronic)
        total = ionic_tensor + electronic_tensor

        # Symmeterize Convert to IEEE orientation
        total = total.convert_to_ieee(structure)
        ionic_tensor = ionic_tensor.convert_to_ieee(structure)
        electronic_tensor = electronic_tensor.convert_to_ieee(structure)

        directions, charges, strains = np.linalg.svd(total.voigt, full_matrices=False)
        max_index = np.argmax(np.abs(charges))

        max_direction = directions[max_index]

        # Allow a max miller index of 10
        min_val = np.abs(max_direction)
        min_val = min_val[min_val > (np.max(min_val) / SETTINGS.MAX_PIEZO_MILLER)]
        min_val = np.min(min_val)

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            **{
                "total": total.zeroed().voigt.tolist(),
                "ionic": ionic_tensor.zeroed().voigt.tolist(),
                "electronic": electronic_tensor.zeroed().voigt.tolist(),
                "e_ij_max": charges[max_index],
                "max_direction": tuple(np.round(max_direction / min_val)),
                "strain_for_max": tuple(strains[max_index]),
            },
            **kwargs,
        )
