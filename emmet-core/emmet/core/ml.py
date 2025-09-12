"""Define schemas for ML calculations and training data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Element, Structure

from emmet.core.elasticity import (
    BulkModulus,
    ElasticityDoc,
    ElasticTensorDoc,
    ShearModulus,
)
from emmet.core.math import Matrix3D, Vector3D, Vector6D, matrix_3x3_to_voigt
from emmet.core.structure import StructureMetadata
from emmet.core.tasks import TaskDoc
from emmet.core.types.pymatgen_types.composition_adapter import CompositionType
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import IdentifierType
from emmet.core.utils import jsanitize
from emmet.core.vasp.calc_types import RunType as VaspRunType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self


class MLDoc(ElasticityDoc):
    """Schema for machine learning interatomic potential calculations.

    Attributes:
    - metadata
        - material_id (str): MP ID
        - structure (Structure): pymatgen Structure object
        - deprecated (bool): whether this material is deprecated in MP
        - calculator (str): name of model used as ML potential.
        - version (str): version of matcalc used to generate this document
    - relaxation
        - final_structure: relaxed pymatgen Structure object
        - energy (float): final energy in eV
        - volume (float): final volume in Angstrom^3
        - lattice parameters (float): a, b, c, alpha, beta, gamma
    - equation of state
        - eos (dict[str, list[float]]): with keys energies and volumes
        - bulk_modulus_bm (float): Birch-Murnaghan bulk modulus in GPa
    - phonon
        - temperatures (list[float]): temperatures in K
        - free_energy (list[float]): Helmholtz energies at those temperatures in eV
        - entropy (list[float]): entropies at those temperatures in eV/K
        - heat_capacities (list[float]): heat capacities at constant volume in eV/K
    - elasticity
        - elastic_tensor (ElasticTensorDoc): pydantic model from emmet.core.elasticity
        - shear_modulus (ShearModulus): Voigt-Reuss-Hill shear modulus (single float in eV/Angstrom^3)
        - bulk_modulus (BulkModulus): Voigt-Reuss-Hill bulk modulus (single float in eV/Angstrom^3)
        - youngs_modulus (float): Young's modulus (single float in eV/Angstrom^3)
    """

    property_name: str = "ml"

    # metadata
    structure: StructureType = Field(description="Original structure")
    model: str | None = Field(None, description="Name of model used as ML potential.")
    version: str | None = Field(
        None, description="Version of model used as ML potential"
    )

    # relaxation attributes
    final_structure: StructureType | None = Field(
        None, description="ML-potential-relaxed structure"
    )
    energy: float | None = Field(None, description="Final energy in eV")
    volume: float | None = Field(None, description="Final volume in Angstrom^3")
    a: float | None = Field(None, description="Lattice length a in Angstrom")
    b: float | None = Field(None, description="Lattice length b in Angstrom")
    c: float | None = Field(None, description="Lattice length c in Angstrom")
    alpha: float | None = Field(None, description="Lattice angle alpha in degrees")
    beta: float | None = Field(None, description="Lattice angle beta in degrees")
    gamma: float | None = Field(None, description="Lattice angle gamma in degrees")

    # equation of state attributes
    eos: dict[str, list[float]] | None = Field(
        None, description="dict with keys energies and volumes"
    )
    bulk_modulus_bm: float | None = Field(None, description="bm.b0_GPa")

    # phonons attributes
    temperatures: list[float] | None = Field(None, description="list of temperatures")
    free_energy: list[float] | None = Field(
        None,
        description="list of Helmholtz free energies at corresponding temperatures",
    )
    entropy: list[float] | None = Field(
        None, description="list of entropies at corresponding temperatures in eV/K"
    )
    heat_capacity: list[float] | None = Field(
        None,
        description="list of heat capacities at constant volume at corresponding "
        "temperatures in eV/K",
    )

    # elasticity attributes
    # all inherited from ElasticityDoc

    @field_validator("elastic_tensor", mode="before")
    def elastic_tensor(cls, val) -> ElasticTensorDoc:
        """ElasticTensorDoc from MSONable dict of ElasticTensor, or list (specifying the Voigt array)
        or the ElasticTensor class itself.
        """
        if isinstance(val, dict):
            tensor = ElasticTensor.from_dict(val)
        elif isinstance(val, (list, tuple)):
            tensor = ElasticTensor(val)
        else:
            tensor = val
        return ElasticTensorDoc(raw=tensor.voigt.tolist())

    @field_validator("bulk_modulus", mode="before")
    def bulk_vrh_no_suffix(cls, new_key, values):
        """Map field bulk_modulus_vrh to bulk_modulus."""
        val = values.get("bulk_modulus_vrh", new_key)
        return BulkModulus(vrh=val)

    @field_validator("shear_modulus", mode="before")
    def shear_vrh_no_suffix(cls, new_key, values):
        """Map field shear_modulus_vrh to shear_modulus."""
        val = values.get("shear_modulus_vrh", new_key)
        return ShearModulus(vrh=val)


class MLTrainDoc(StructureMetadata):
    """Generic schema for ML training data."""

    structure: StructureType | None = Field(
        None, description="Structure for this entry."
    )

    energy: float | None = Field(
        None, description="The total energy associated with this structure."
    )

    forces: list[Vector3D] | None = Field(
        None,
        description="The interatomic forces corresponding to each site in the structure.",
    )

    abs_forces: list[float] | None = Field(
        None, description="The magnitude of the interatomic force on each site."
    )

    stress: Vector6D | None = Field(
        None,
        description="The components of the symmetric stress tensor in Voigt notation (xx, yy, zz, yz, xz, xy).",
    )

    stress_matrix: Matrix3D | None = Field(
        None,
        description="The 3x3 stress tensor. Use this if the tensor is unphysically non-symmetric.",
    )

    bandgap: float | None = Field(None, description="The final DFT bandgap.")

    elements: list[Element] | None = Field(
        None,
        description="List of unique elements in the material sorted alphabetically.",
    )

    composition: CompositionType | None = Field(
        None, description="Full composition for the material."
    )

    composition_reduced: CompositionType | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )

    functional: VaspRunType | None = Field(
        None, description="The approximate functional used to generate this entry."
    )

    bader_charges: list[float] | None = Field(
        None, description="Bader charges on each site of the structure."
    )
    bader_magmoms: list[float] | None = Field(
        None,
        description="Bader on-site magnetic moments for each site of the structure.",
    )

    @model_serializer
    def deseralize(self):
        """Ensure output is JSON compliant."""
        return jsanitize({k: getattr(self, k, None) for k in self.model_fields})

    @model_validator(mode="after")
    def set_abs_forces(
        self,
    ) -> Self:
        """Ensure the abs_forces are set if the vector-valued forces are."""
        if self.forces is not None and self.abs_forces is None:
            self.abs_forces = [np.linalg.norm(f) for f in self.forces]  # type: ignore[misc]
        return self

    @classmethod
    def from_structure(
        cls,
        meta_structure: Structure,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        """
        Create an ML training document from a structure and fields.

        This method mostly exists to ensure that the structure field is
        set because `meta_structure` does not populate it automatically.

        Parameters
        -----------
        meta_structure : Structure
        fields : list of str or None
            Additional fields in the document to populate
        **kwargs
            Any other fields / constructor kwargs
        """
        return super().from_structure(
            meta_structure=meta_structure,
            fields=fields,
            structure=meta_structure,
            **kwargs,
        )

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDoc,
        **kwargs,
    ) -> list[Self]:
        """Create a list of ML training documents from the ionic steps in a TaskDoc.

        Parameters
        -----------
        task_doc : TaskDoc
        **kwargs
            Any kwargs to pass to `from_structure`.
        """
        entries = []

        for cr in task_doc.calcs_reversed[::-1]:
            nion = len(cr.output.ionic_steps)

            for iion, ionic_step in enumerate(cr.output.ionic_steps):
                structure = Structure.from_dict(ionic_step.structure.as_dict())
                # these are fields that should only be set on the final frame of a calculation
                # also patch in magmoms because of how Calculation works
                last_step_kwargs = {}
                if iion == nion - 1:
                    if magmom := cr.output.structure.site_properties.get("magmom"):
                        structure.add_site_property("magmom", magmom)
                    last_step_kwargs["bandgap"] = cr.output.bandgap
                    if bader_analysis := cr.bader:
                        for bk in (
                            "charge",
                            "magmom",
                        ):
                            last_step_kwargs[f"bader_{bk}s"] = bader_analysis[bk]

                if (_st := ionic_step.stress) is not None:
                    st = np.array(_st)
                    if np.allclose(st, st.T, rtol=1e-8):
                        # Stress tensor is symmetric
                        last_step_kwargs["stress"] = matrix_3x3_to_voigt(_st)
                    else:
                        # Stress tensor is non-symmetric
                        last_step_kwargs["stress_matrix"] = _st

                entries.append(
                    cls.from_structure(
                        meta_structure=structure,
                        energy=ionic_step.e_0_energy,
                        forces=ionic_step.forces,
                        functional=cr.run_type,
                        **last_step_kwargs,
                        **kwargs,
                    )
                )
        return entries


class MatPESProvenanceDoc(BaseModel):
    """Information regarding the origins of a MatPES structure."""

    original_mp_id: IdentifierType | None = Field(
        None,
        description="MP identifier corresponding to the Materials Project structure from which this entry was sourced from.",
    )
    materials_project_version: str | None = Field(
        None,
        description="The version of the Materials Project from which the struture was sourced.",
    )
    md_ensemble: str | None = Field(
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
    """
    Schema for VASP data in the Materials Potential Energy Surface (MatPES) effort.

    This schema is used in the data entries for MatPES v2025.1,
    which can be downloaded either:
        - On [MPContribs](https://materialsproject-contribs.s3.amazonaws.com/index.html#MatPES_2025_1/)
        - or on [the site]
    """

    matpes_id: str | None = Field(None, description="MatPES identifier.")

    formation_energy_per_atom: float | None = Field(
        None,
        description="The uncorrected formation enthalpy per atom at zero pressure and temperature.",
    )
    cohesive_energy_per_atom: float | None = Field(
        None, description="The uncorrected cohesive energy per atom."
    )

    provenance: MatPESProvenanceDoc | None = Field(
        None, description="Information about the provenance of the structure."
    )

    @property
    def pressure(self) -> float | None:
        """Return the pressure from the DFT stress tensor."""
        return sum(self.stress[:3]) / 3.0 if self.stress else None

    @property
    def magmoms(self) -> Sequence[float] | None:
        """Retrieve on-site magnetic moments from the structure if they exist."""
        magmom = (
            self.structure.site_properties.get("magmom") if self.structure else None
        )
        return magmom
