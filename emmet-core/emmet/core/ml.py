"""Define schemas for ML calculations and training data."""

from __future__ import annotations

from pydantic import (
    Field,
    field_validator,
)
from pymatgen.analysis.elasticity import ElasticTensor

from emmet.core.elasticity import (
    BulkModulus,
    ElasticityDoc,
    ElasticTensorDoc,
    ShearModulus,
)
from emmet.core.types.pymatgen_types.structure_adapter import StructureType


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
