from typing import List, Optional
from pymatgen.core.structure import Structure

from pydantic import BaseModel, Field


class SurfaceEntry(BaseModel):
    """
    Surface energies, miller indicies, ...
    """

    miller_index: Optional[List[int]] = Field(
        None,
        description="Miller index of surface.",
    )

    surface_energy_EV_PER_ANG2: Optional[float] = Field(
        None,
        description="Surface energy in eV/Å².",
    )

    surface_energy: Optional[float] = Field(
        None,
        description="Surface energy in J/m².",
    )

    is_reconstructed: Optional[bool] = Field(
        None,
        description="Whether it is a reconstructed surface.",
    )

    structure: Optional[str] = Field(
        None,
        description="CIF of slab structure.",
    )

    work_function: Optional[float] = Field(
        None,
        description="Work function in eV.",
    )

    efermi: Optional[float] = Field(
        None,
        description="Fermi energy in eV.",
    )

    area_fraction: Optional[float] = Field(
        None,
        description="Area fraction.",
    )

    has_wulff: Optional[bool] = Field(
        None,
        description="Whether the surface has wulff entry.",
    )


class SurfacePropDoc(BaseModel):
    """
    Model for a document containing surface properties data
    """

    surfaces: Optional[List[SurfaceEntry]] = Field(
        None,
        description="List of individual surface data.",
    )

    weighted_surface_energy_EV_PER_ANG2: Optional[float] = Field(
        None,
        description="Weighted surface energy in eV/Å²",
    )

    weighted_surface_energy: Optional[float] = Field(
        None,
        description="Weighted surface energy in J/m²",
    )

    surface_anisotropy: Optional[float] = Field(
        None,
        description="Surface energy anisotropy.",
    )

    pretty_formula: Optional[str] = Field(
        None,
        description="Reduced Formula of the material.",
    )

    shape_factor: Optional[float] = Field(
        None,
        description="Shape factor.",
    )

    weighted_work_function: Optional[float] = Field(
        None,
        description="Weighted work function in eV.",
    )

    has_reconstructed: Optional[bool] = Field(
        None,
        description="Whether the entry has any reconstructed surfaces.",
    )

    task_id: Optional[str] = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    structure: Optional[Structure] = Field(
        None,
        description="The conventional crystal structure of the material.",
    )
