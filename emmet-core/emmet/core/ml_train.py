"""Define schemas for ML training data organization."""
from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import Field, BaseModel
from pymatgen.core import Composition, Element, Structure

from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import RunType as VaspRunType

if TYPE_CHECKING:
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

    elements: list[Element] | None = Field(
        None,
        description="List of unique elements in the material sorted alphabetically.",
    )

    composition: Composition | None = Field(
        None, description="Full composition for the material."
    )

    composition_reduced: Composition | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )

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


class MatPESProvenanceDoc(BaseModel):
    """Information regarding the origins of a MatPES structure."""

    original_mp_id: MPID | str | None = Field(
        None,
        description="MP identifier corresponding to the Materials Project structure from which this entry was sourced from.",
    )
    materials_project_version: str | None = Field(
        None,
        description="The version of the Materials Project from which the struture was sourced.",
    )
    md_ensemble: str = Field(
        None,
        description="The molecular dynamics ensemble used to generate this structure.",
    )
    md_temperature: float | None = Field(
        None,
        description="If a float, the temperature in Kelvin at which MLMD was performed.",
    )
    md_pressure: float | None = Field(
        None,
        description="If a float, the pressure in atmosphere at which MLMD was performed.",
    )
    md_step: int | None = Field(
        None,
        description="The step in the MD simulation from which the structure was sampled.",
    )
    mlip_name: str | None = Field(
        None, description="The name of the ML potential used to perform MLMD."
    )


class MatPESTrainDoc(MLTrainDoc):
    """Schema for VASP data in the Materials Potential Energy Surface (MatPES) effort."""

    matpes_id: str | None = Field(None, description="MatPES identifier.")

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

    abs_forces: list[float] | None = Field(
        None, description="The magnitude of the interatomic force on each site."
    )

    bader_charges: list[float] | None = Field(
        None, description="Bader charges on each site of the structure."
    )
    bader_magmoms: list[float] | None = Field(
        None,
        description="Bader on-site magnetic moments for each site of the structure.",
    )

    provenance: MatPESProvenanceDoc | None = Field(
        None, description="Information about the provenance of the structure."
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
