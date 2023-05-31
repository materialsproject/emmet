from typing import List
from datetime import datetime
from monty.json import MontyDecoder
from pydantic import Field, validator, BaseModel

from pymatgen.electronic_structure.bandstructure import BandStructure

from emmet.core.mpid import MPID

from ifermi.surface import FermiSurface
from ifermi.interpolate import FourierInterpolator
from ifermi.kpoints import kpoints_from_bandstructure


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

    fermi_surfaces: list[dict] = Field(
        None,
        description="List of IFermi FermiSurface objects.",
    )

    surface_types: List[str] = Field(
        None,
        description="Type of each fermi surface in the fermi_surfaces list.\
            Is either CBM or VBM for semiconductors, or fermi_surface for metals.",
    )

    fs_id: str = Field(None, description="")

    state: str = Field(None, description="")

    @classmethod
    def from_structure(
        cls,
        material_id: MPID,
        task_id: str,
        bandstructure: BandStructure,
        last_updated: datetime,
        fs_id: str,
        state: str,
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
            # temp_time0 = time.time()
            temp_fs = FermiSurface.from_band_structure(
                band_structure=interpolated_bs,
                mu=mu,
                property_data=velocites,
                property_kpoints=interpolated_kpoints,
                calculate_dimensionality=True,
                wigner_seitz=True,
            )
            # temp_finish = time.time()

            total_verts = 0
            for spin, surfaces in temp_fs.isosurfaces.items():
                for surface in surfaces:
                    total_verts += len(surface.vertices)

            desired_max_verts = 10000
            decimation_factor = int(total_verts / desired_max_verts)

            # smooth_time0 = time.time()
            fs = FermiSurface.from_band_structure(
                band_structure=interpolated_bs,
                mu=mu,
                property_data=velocites,
                property_kpoints=interpolated_kpoints,
                calculate_dimensionality=True,
                wigner_seitz=True,
                decimate_factor=decimation_factor,
                # smooth=True,
            )
            # smooth_finish = time.time()

            # print(f"\nTemp fs time is: {temp_finish - temp_time0}")
            # print(f"Smooth fs time is: {smooth_finish - smooth_time0}")

            fermi_surfaces.append(fs.as_dict())
            surface_types.append(key)

        return FermiDoc(
            material_id=material_id,
            task_id=task_id,
            last_updated=last_updated,
            fermi_surfaces=fermi_surfaces,
            surface_types=surface_types,
            fs_id=fs_id,
            state=state,
        )

    # Make sure that the datetime field is properly formatted
    @validator("last_updated", pre=True)
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)
