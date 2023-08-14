from typing import Dict, List

from emmet.core.material_property import PropertyDoc
from matcalc.elasticity import ElasticityCalc
from matcalc.eos import EOSCalc
from matcalc.phonon import PhononCalc
from matcalc.relaxation import RelaxCalc
from pydantic import Field
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure


class MLIPElasticityDoc(PropertyDoc):
    """ML interatomic potential-predicted elasticity doc storing the elastic tensor,
    shear modulus, bulk modulus, and Young's modulus."""

    property_name = "elasticity"

    elastic_tensor: ElasticTensor = Field(
        description="Elastic tensor as a pymatgen ElasticTensor object"
    )
    shear_modulus_vrh: float = Field(
        description="Voigt-Reuss-Hill shear modulus based on elastic tensor"
    )
    bulk_modulus_vrh: float = Field(
        description="Voigt-Reuss-Hill bulk modulus based on elastic tensor"
    )
    youngs_modulus: float = Field(description="Young's modulus based on elastic tensor")

    @classmethod
    def from_structure(
        cls, structure, material_id, calc_kwargs: dict = None, **kwargs
    ) -> "MLIPElasticityDoc":
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            calc_kwargs (dict): Keyword arguments to passed matcalc Calculator.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            ElasticityDoc
        """
        result = ElasticityCalc(**(calc_kwargs or {})).calc(structure)
        return super().from_structure(
            meta_structure=structure, material_id=material_id, **result, **kwargs
        )


class MLIPPhononDoc(PropertyDoc):
    """ML interatomic potential-predicted phonon doc storing the temperature, free
    energy, entropy, heat capacity."""

    property_name = "phonon"

    temperature: ElasticTensor = Field(description="list of temperatures")
    free_energy: float = Field(
        description="list of Helmholtz free energies at corresponding temperatures"
    )
    entropy: float = Field(
        description="list of entropies at corresponding temperatures"
    )
    heat_capacities: float = Field(
        description="list of heat capacities at constant volume at corresponding temperatures"
    )

    @classmethod
    def from_structure(
        cls, structure, material_id, calc_kwargs: dict = None, **kwargs
    ) -> "MLIPPhononDoc":
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            calc_kwargs (dict): Keyword arguments to passed matcalc Calculator.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            ElasticityDoc
        """
        result = PhononCalc(**(calc_kwargs or {})).calc(structure)
        return super().from_structure(
            meta_structure=structure, material_id=material_id, **result, **kwargs
        )


class MLIPEosDoc(PropertyDoc):
    """ML interatomic potential-predicted equation of state doc storing the temperature,
    free energy, entropy, heat capacity."""

    property_name = "eos"

    EOS: Dict[str, List[float]] = Field(
        description="dict with keys energies and volumes"
    )
    bulk_modulus: float = Field(description="bm.b0_GPa")

    @classmethod
    def from_structure(
        cls, structure, material_id, calc_kwargs: dict = None, **kwargs
    ) -> "MLIPEosDoc":
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            calc_kwargs (dict): Keyword arguments to passed matcalc Calculator.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            ElasticityDoc
        """
        result = EOSCalc(**(calc_kwargs or {})).calc(structure)
        return super().from_structure(
            meta_structure=structure, material_id=material_id, **result, **kwargs
        )


class MLIPRelaxationDoc(PropertyDoc):
    """ML interatomic potential-predicted relaxation doc storing the final structure,
    lattice parameters, volume and energy."""

    property_name = "relaxation"
    EOS: Dict[str, List[float]] = Field(
        description="dict with keys energies and volumes"
    )
    final_structure: Structure = Field(description="ML-potential-relaxed structure")
    a: float = Field(description="Lattice length a in Angstrom")
    b: float = Field(description="Lattice length b in Angstrom")
    c: float = Field(description="Lattice length c in Angstrom")
    alpha: float = Field(description="Lattice angle alpha in degrees")
    beta: float = Field(description="Lattice angle beta in degrees")
    gamma: float = Field(description="Lattice angle gamma in degrees")
    volume: float = Field(description="Final volume in Angstrom^3")
    energy: float = Field(description="Final energy in eV")

    @classmethod
    def from_structure(
        cls, structure, material_id, calc_kwargs: dict = None, **kwargs
    ) -> "MLIPRelaxationDoc":
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            calc_kwargs (dict): Keyword arguments to passed matcalc Calculator.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            MLIPRelaxationDoc
        """
        result = RelaxCalc(**(calc_kwargs or {})).calc(structure)
        return super().from_structure(
            meta_structure=structure, material_id=material_id, **result, **kwargs
        )
