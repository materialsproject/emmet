from typing import List
from pydantic import Field
from emmet.core.material_property import PropertyDoc
import numpy as np
from emmet.core.mpid import MPID
from pymatgen.core import Structure


class AbsorptionDoc(PropertyDoc):
    """Absorption spectrum based on frequency dependent dielectric function calculations."""

    property_name = "Optical absorption spectrum"

    task_id: str = Field(..., description="Calculation id")

    energies: List[float] = Field(..., description="Absorption energy in eV starting from 0")

    energy_max: float = Field(..., description="Maximum energy")

    absorption_coefficient: List[float] = Field(..., description="Absorption coefficient in cm^-1")

    average_imaginary_dielectric: List[float] = Field(
        ...,
        description="Imaginary part of the dielectric function corresponding to the " "energies",
    )

    average_real_dielectric: List[float] = Field(
        ...,
        description="Real part of the dielectric function corresponding to the energies",
    )

    bandgap: float = Field(None, description="The electronic band gap")

    nkpoints: float = Field(None, description="The number of kpoints used in the calculation")

    @classmethod
    def _convert_list_to_tensor(cls, l):
        l = np.array(l)
        a = np.array([[l[0], l[3], l[4]], [l[3], l[1], l[5]], [l[4], l[5], l[2]]])
        return a

    @classmethod
    def from_structure(
        cls,
        material_id: MPID,
        energies: List,
        task_id: str,
        real_d: List[np.ndarray],
        imag_d: List[np.ndarray],
        absorption_co: List,
        bandgap: float,
        structure: Structure,
        nkpoints: float,
        **kwargs,
    ):

        real_d_average = [np.average(np.diagonal(cls._convert_list_to_tensor(t))) for t in real_d]
        imag_d_average = [np.average(np.diagonal(cls._convert_list_to_tensor(t))) for t in imag_d]
        absorption_co = list(np.array(absorption_co))
        energy_max = np.array(energies).max()

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            **{
                "energies": energies,
                "energy_max": energy_max,
                "absorption_coefficient": absorption_co,
                "average_imaginary_dielectric": imag_d_average,
                "average_real_dielectric": real_d_average,
                "bandgap": bandgap,
                "nkpoints": nkpoints,
                "task_id": task_id,
            },
            **kwargs,
        )
