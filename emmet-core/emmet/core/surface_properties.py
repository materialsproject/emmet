from pydantic import BaseModel, Field

from emmet.core.types.pymatgen_types.structure_adapter import StructureType


class SurfaceEntry(BaseModel):
    """
    Surface energies, miller indicies, ...
    """

    miller_index: list[int] | None = Field(
        None,
        description="Miller index of surface.",
    )

    surface_energy_EV_PER_ANG2: float | None = Field(
        None,
        description="Surface energy in eV/Å².",
    )

    surface_energy: float | None = Field(
        None,
        description="Surface energy in J/m².",
    )

    is_reconstructed: bool | None = Field(
        None,
        description="Whether it is a reconstructed surface.",
    )

    structure: str | None = Field(
        None,
        description="CIF of slab structure.",
    )

    work_function: float | None = Field(
        None,
        description="Work function in eV.",
    )

    efermi: float | None = Field(
        None,
        description="Fermi energy in eV.",
    )

    area_fraction: float | None = Field(
        None,
        description="Area fraction.",
    )

    has_wulff: bool | None = Field(
        None,
        description="Whether the surface has wulff entry.",
    )


class SurfacePropDoc(BaseModel):
    """
    Model for a document containing surface properties data
    """

    surfaces: list[SurfaceEntry] | None = Field(
        None,
        description="List of individual surface data.",
    )

    weighted_surface_energy_EV_PER_ANG2: float | None = Field(
        None,
        description="Weighted surface energy in eV/Å²",
    )

    weighted_surface_energy: float | None = Field(
        None,
        description="Weighted surface energy in J/m²",
    )

    surface_anisotropy: float | None = Field(
        None,
        description="Surface energy anisotropy.",
    )

    pretty_formula: str | None = Field(
        None,
        description="Reduced Formula of the material.",
    )

    shape_factor: float | None = Field(
        None,
        description="Shape factor.",
    )

    weighted_work_function: float | None = Field(
        None,
        description="Weighted work function in eV.",
    )

    has_reconstructed: bool | None = Field(
        None,
        description="Whether the entry has any reconstructed surfaces.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    structure: StructureType | None = Field(
        None,
        description="The conventional crystal structure of the material.",
    )
