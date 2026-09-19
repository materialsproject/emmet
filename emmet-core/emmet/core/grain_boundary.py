from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from emmet.core.atoms.periodic import Material
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.grain_boundary_adapter import GrainBoundaryType
from emmet.core.types.typing import DateTimeType, MaterialIdentifierType

if TYPE_CHECKING:
    from typing import Any

    from typing_extensions import Self


class GBTypeEnum(ValueEnum):
    """
    Grain boundary types
    """

    tilt = "tilt"
    twist = "twist"


class GrainBoundaryDoc(BaseModel):
    """
    Grain boundary energies, work of separation...
    """

    material_id: MaterialIdentifierType | None = Field(
        None,
        description="The Materials Project ID of the material. This comes in the form: mp-******.",
    )

    sigma: int | None = Field(
        None,
        description="Sigma value of the boundary.",
    )

    type: GBTypeEnum | None = Field(
        None,
        description="Grain boundary type.",
    )

    rotation_axis: list[int] | None = Field(
        None,
        description="Rotation axis.",
    )

    gb_plane: list[int] | None = Field(
        None,
        description="Grain boundary plane.",
    )

    rotation_angle: float | None = Field(
        None,
        description="Rotation angle in degrees.",
    )

    gb_energy: float | None = Field(
        None,
        description="Grain boundary energy in J/m^2.",
    )

    initial_structure: GrainBoundaryType | None = Field(
        None, description="Initial grain boundary structure."
    )

    final_structure: GrainBoundaryType | None = Field(
        None, description="Final grain boundary structure."
    )

    pretty_formula: str | None = Field(
        None, description="Reduced formula of the material."
    )

    w_sep: float | None = Field(None, description="Work of separation in J/m^2.")

    structure: Material | None = Field(None, description="Structure.")

    chemsys: str | None = Field(
        None, description="Dash-delimited string of elements in the material."
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation for this Material document.",
    )

    @classmethod
    def _migrate_schema(cls, config: dict[str, Any]) -> Self:
        """Pipe legacy CIF data into a pymatgen structure."""
        if isinstance(cif_str := config.pop("cif", None), str) and not config.get(
            "structure"
        ):
            from emmet.core.io.pymatgen import cif_to_material

            config["structure"] = cif_to_material(cif_str)
        return cls(**config)

    @property
    def cif(self) -> str | None:
        """Support accessing legacy CIF from structure field."""
        if self.structure:
            return self.structure.to_pmg().to(fmt="cif")
        return None
