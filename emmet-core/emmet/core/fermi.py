from typing import List, Dict, Union
from datetime import datetime

from monty.json import MontyDecoder
from pydantic import Field, validator, BaseModel

from emmet.core.mpid import MPID

from pymatgen.electronic_structure.bandstructure import BandStructure

from ifermi.surface import FermiSurface
from ifermi.interpolate import FourierInterpolator
from ifermi.kpoints import kpoints_from_bandstructure

# Used only for testing on machines with low memory
from wrapt_timeout_decorator import *


class FermiDoc(BaseModel):
    """
    Fermi surfaces.
    """

    material_id: MPID = Field(
        ...,
        description="The Materials Project ID of the material, used as a universal reference across property documents."
        "This comes in the form: mp-******.",
    )

    task_id: str = Field(
        None,
        description="The source calculation (task) ID that corresponds to the calculation that generated\
            the band structure(s) that were used to generate these Fermi Surfaces."
        "This has the same form as a Materials Project ID.",
    )

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent calculation for this fermi surface document.",
    )

    fermi_surfaces: List[dict] = Field(
        ...,
        description="List of IFermi FermiSurface objects.",
    )

    surface_types: List[str] = Field(
        ...,
        description="Type of each fermi surface in the fermi_surfaces list.\
            Is either CBM or VBM for semiconductors, or fermi_surface for metals.",
    )

    @classmethod
    @timeout(10)  # Only for testing on low memory machines
    def from_structure(
        cls,
        material_id: MPID,
        task_id: str,
        bandstructure: BandStructure,
        last_updated: datetime,
        **kwargs,
    ):
        interpolator = FourierInterpolator(bandstructure)
        interpolated_bs, velocites = interpolator.interpolate_bands(
            return_velocities=True
        )

        interpolated_kpoints = kpoints_from_bandstructure(interpolated_bs)

        mu_values = {}

        if interpolated_bs.is_metal():
            mu_values["fermi_surface"] = 0
        else:
            window = 0.1
            efermi = interpolated_bs.efermi

            vbm_mu = interpolated_bs.get_vbm()["energy"] - efermi - window
            cbm_mu = interpolated_bs.get_cbm()["energy"] - efermi + window

            mu_values["VBM"] = vbm_mu
            mu_values["CBM"] = cbm_mu

        fermi_surfaces = []
        surface_types = []

        for key, mu in mu_values.items():
            fs = FermiSurface.from_band_structure(
                band_structure=interpolated_bs,
                mu=mu,
                property_data=velocites,
                property_kpoints=interpolated_kpoints,
                calculate_dimensionality=True,
                wigner_seitz=True,
            )

            fermi_surfaces.append(fs.as_dict())
            surface_types.append(key)

        return FermiDoc(
            material_id=material_id,
            task_id=task_id,
            fermi_surfaces=fermi_surfaces,
            surface_types=surface_types,
            last_updated=last_updated,
        )

    # Make sure that the datetime field is properly formatted
    @validator("last_updated", pre=True)
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)
