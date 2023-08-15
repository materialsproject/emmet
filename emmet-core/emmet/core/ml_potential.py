from typing import TYPE_CHECKING, Dict, List, Union

from emmet.core.material_property import PropertyDoc
from matcalc.elasticity import ElasticityCalc
from matcalc.eos import EOSCalc
from matcalc.phonon import PhononCalc
from matcalc.relaxation import RelaxCalc
from pydantic import Field
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator


class MLIPDoc(PropertyDoc):
    """Document model for matcalc-generated material properties from machine learning
    interatomic potential predictions.

    Includes
    - relaxation properties
        - final structure: relaxed pymatgen Structure object
        - energy (float): final energy in eV
        - volume (float): final volume in Angstrom^3
        - lattice parameters: a, b, c, alpha, beta, gamma
    - equation of state properties
        - EOS (dict[str, list[float]]): with keys energies and volumes
        - bulk modulus (float): Birch-Murnaghan bulk modulus in GPa
    - phonon properties
        - temperature (list[float]): temperatures in K
        - free energy (list[float]): Helmholtz energies at those temperatures in eV
        - entropy (list[float]): entropies at those temperatures in eV/K
        - heat capacities (list[float]): heat capacities at constant volume in eV/K
    - elasticity properties
        - elastic tensor (ElasticTensor): pymatgen ElasticTensor object
        - shear modulus (float): Voigt-Reuss-Hill shear modulus
        - bulk modulus (float): Voigt-Reuss-Hill bulk modulus
        - Young's modulus (float): Young's modulus
    """

    property_name = "mlip"

    # relaxation attributes
    final_structure: Structure = Field(description="ML-potential-relaxed structure")
    energy: float = Field(description="Final energy in eV")
    volume: float = Field(description="Final volume in Angstrom^3")
    a: float = Field(description="Lattice length a in Angstrom")
    b: float = Field(description="Lattice length b in Angstrom")
    c: float = Field(description="Lattice length c in Angstrom")
    alpha: float = Field(description="Lattice angle alpha in degrees")
    beta: float = Field(description="Lattice angle beta in degrees")
    gamma: float = Field(description="Lattice angle gamma in degrees")

    # equation of state attributes
    EOS: Dict[str, List[float]] = Field(
        description="dict with keys energies and volumes"
    )
    bulk_modulus: float = Field(description="bm.b0_GPa")

    # phonons attributes
    temperature: ElasticTensor = Field(description="list of temperatures")
    free_energy: float = Field(
        description="list of Helmholtz free energies at corresponding temperatures"
    )
    entropy: float = Field(
        description="list of entropies at corresponding temperatures in eV/K"
    )
    heat_capacities: float = Field(
        description="list of heat capacities at constant volume at corresponding "
        "temperatures in eV/K"
    )

    # elasticity attributes
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

    def __init__(
        cls,
        structure,
        material_id,
        calculator: Union[str, "Calculator"],
        prop_kwargs: dict = None,
        **kwargs
    ) -> None:
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            prop_kwargs (dict): Keyword arguments for each matcalc PropCalc class.
                Recognized keys are RelaxCalc, ElasticityCalc, PhononCalc, EOSCalc.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            MLIPRelaxationDoc
        """
        prop_kwargs = prop_kwargs or {}

        relax = RelaxCalc(calculator, **prop_kwargs.get("RelaxCalc", {})).calc(
            structure
        )
        relax["ml_volume"] = relax.pop("volume")
        elasticity = ElasticityCalc(
            calculator, **prop_kwargs.get("ElasticityCalc", {})
        ).calc(structure)
        phonon = PhononCalc(calculator, **prop_kwargs.get("PhononCalc", {})).calc(
            structure
        )
        eos = EOSCalc(calculator, **prop_kwargs.get("EOSCalc", {})).calc(structure)

        results = {**relax, **elasticity, **phonon, **eos}
        super().from_structure(
            structure=structure,
            meta_structure=structure,
            material_id=material_id,
            calculator=calculator,
            **results,
            **kwargs
        )
