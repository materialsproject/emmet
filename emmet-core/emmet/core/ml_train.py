"""Define schemas for ML training data organization."""

from typing import List, Optional, Tuple

from pydantic import Field
from pymatgen.core import Structure

from emmet.core.mpid import MPID
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import RunType as VaspRunType


class MLTrainDoc(StructureMetadata, extra="allow"):
    """Generic schema for ML training data."""

    structure: Optional[Structure] = Field(
        None, description="Structure for this entry."
    )

    energy: Optional[float] = Field(
        None, description="The total energy associated with this structure."
    )

    forces: Optional[List[Tuple[float, float, float]]] = Field(
        None,
        description="The interatomic forces corresponding to each site in the structure.",
    )

    stress: Optional[Tuple[float, float, float, float, float, float]] = Field(
        None,
        description="The components of the stress tensor in Voigt notation (xx, yy, zz, yz, xz, xy).",
    )

    @classmethod
    def from_structure(
        cls,
        meta_structure: Structure,
        fields: Optional[list[str]] = None,
        **kwargs,
    ):
        return super().from_structure(
            meta_structure=meta_structure,
            fields=fields,
            structure=meta_structure,
            **kwargs,
        )


class MatPESTrainDoc(MLTrainDoc):
    """Schema for VASP data in the Materials Potential Energy Surface set."""
    matpes_id: Optional[str] = Field(None, description="MatPES identifier.")
    mp_id: Optional[MPID | str] = Field(None, description="MP identifier.")

    bandgap: float = Field(None, description="The DFT bandgap.")
    functional: VaspRunType = Field(
        None, description="The approximate functional used to generate this entry."
    )

    formation_energy_per_atom: float = Field(
        None,
        description="The formation enthalpy per atom at zero pressure and temperature.",
    )
    cohesive_energy_per_atom: float = Field(
        None, description="The cohesive energy per atom."
    )

    bader_charges: Optional[list[float]] = Field(
        None, description="Bader charges on each site of the structure."
    )
    bader_magmoms: Optional[list[float]] = Field(
        None,
        description="Bader on-site magnetic moments for each site of the structure.",
    )

    @property
    def pressure(self) -> float:
        return sum(self.stress[:3]) / 3.0
