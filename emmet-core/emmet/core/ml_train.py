"""Define schemas for ML training data organization."""
from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import Field, model_validator
from pymatgen.core import Composition, Structure

from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import RunType as VaspRunType

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self


class MLTrainDoc(StructureMetadata):
    """Generic schema for ML training data."""

    structure: Structure | None = Field(None, description="Structure for this entry.")

    energy: float | None = Field(
        None, description="The total energy associated with this structure."
    )

    forces: list[tuple[float, float, float]] | None = Field(
        None,
        description="The interatomic forces corresponding to each site in the structure.",
    )

    stress: tuple[float, float, float, float, float, float] | None = Field(
        None,
        description="The components of the symmetric stress tensor in Voigt notation (xx, yy, zz, yz, xz, xy).",
    )

    elements: list[str] | None = Field(
        None,
        description="List of unique elements in the material sorted alphabetically.",
    )

    composition: dict[str, float] | None = Field(
        None, description="Full composition for the material."
    )

    composition_reduced: dict[str, float] | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )

    @model_validator(mode="before")
    def deserialize(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure some pymatgen objects are deserialized for easier querying."""

        if values.get("elements"):
            values["elements"] = [str(ele) for ele in values["elements"]]

        for attr in (
            "composition",
            "composition_reduced",
        ):
            if (v := values.get(attr)) and isinstance(v, Composition):
                values[attr] = v.as_dict()

        return values

    @classmethod
    def from_structure(
        cls,
        meta_structure: Structure,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        """Ensure structure field is populated."""
        return super().from_structure(
            meta_structure=meta_structure,
            fields=fields,
            structure=meta_structure,
            **kwargs,
        )


class MatPESTrainDoc(MLTrainDoc):
    """Schema for VASP data in the Materials Potential Energy Surface (MatPES) effort."""

    matpes_id: str | None = Field(None, description="MatPES identifier.")
    mp_id: MPID | str | None = Field(None, description="MP identifier.")

    bandgap: float | None = Field(None, description="The DFT bandgap.")
    functional: VaspRunType | None = Field(
        None, description="The approximate functional used to generate this entry."
    )

    formation_energy_per_atom: float | None = Field(
        None,
        description="The uncorrected formation enthalpy per atom at zero pressure and temperature.",
    )
    cohesive_energy_per_atom: float | None = Field(
        None, description="The uncorrected cohesive energy per atom."
    )

    bader_charges: list[float] | None = Field(
        None, description="Bader charges on each site of the structure."
    )
    bader_magmoms: list[float] | None = Field(
        None,
        description="Bader on-site magnetic moments for each site of the structure.",
    )

    @property
    def pressure(self) -> float:
        """Return the pressure from the DFT stress tensor."""
        return sum(self.stress[:3]) / 3.0

    @property
    def magmoms(self) -> list[float] | None:
        """Retrieve on-site magnetic moments from the structure if they exist."""
        if self.structure and (magmom := self.structure.site_properties.get("magmom")):
            return magmom
