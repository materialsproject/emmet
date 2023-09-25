from typing import TYPE_CHECKING, Dict, List, Optional, Union

from matcalc.elasticity import ElasticityCalc
from matcalc.eos import EOSCalc
from matcalc.phonon import PhononCalc
from matcalc.relaxation import RelaxCalc
from matcalc.util import get_universal_calculator
from pydantic import Field, validator
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure

from emmet.core.material_property import PropertyDoc

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator


class MLIPDoc(PropertyDoc):
    """Document model for matcalc-generated material properties from machine learning
    interatomic potential predictions.

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
        - elastic_tensor (ElasticTensor): pymatgen ElasticTensor object
        - shear_modulus_vrh (float): Voigt-Reuss-Hill shear modulus
        - bulk_modulus_vrh (float): Voigt-Reuss-Hill bulk modulus
        - youngs_modulus (float): Young's modulus
    """

    property_name = "mlip"

    # metadata
    structure: Structure = Field(description="Original structure")
    matcalc_version: str = Field(
        None, description="Version of matcalc used to generate this document"
    )
    model_name: str = Field(None, description="Name of model used as ML potential.")
    model_version: str = Field(
        None, description="Version of model used as ML potential"
    )

    # relaxation attributes
    final_structure: Structure = Field(
        None, description="ML-potential-relaxed structure"
    )
    energy: float = Field(None, description="Final energy in eV")
    volume: float = Field(None, description="Final volume in Angstrom^3")
    a: float = Field(None, description="Lattice length a in Angstrom")
    b: float = Field(None, description="Lattice length b in Angstrom")
    c: float = Field(None, description="Lattice length c in Angstrom")
    alpha: float = Field(None, description="Lattice angle alpha in degrees")
    beta: float = Field(None, description="Lattice angle beta in degrees")
    gamma: float = Field(None, description="Lattice angle gamma in degrees")

    # equation of state attributes
    eos: Dict[str, List[float]] = Field(
        None, description="dict with keys energies and volumes"
    )
    bulk_modulus_bm: float = Field(None, description="bm.b0_GPa")

    # phonons attributes
    temperatures: List[float] = Field(None, description="list of temperatures")
    free_energy: List[float] = Field(
        None,
        description="list of Helmholtz free energies at corresponding temperatures",
    )
    entropy: List[float] = Field(
        None, description="list of entropies at corresponding temperatures in eV/K"
    )
    heat_capacity: List[float] = Field(
        None,
        description="list of heat capacities at constant volume at corresponding "
        "temperatures in eV/K",
    )

    # elasticity attributes
    elastic_tensor: ElasticTensor = Field(
        None, description="pymatgen ElasticTensor in Voigt notation (GPa)"
    )
    shear_modulus_vrh: float = Field(
        None, description="Voigt-Reuss-Hill shear modulus based on elastic tensor"
    )
    bulk_modulus_vrh: float = Field(
        None, description="Voigt-Reuss-Hill bulk modulus based on elastic tensor"
    )
    youngs_modulus: float = Field(
        None, description="Young's modulus based on elastic tensor"
    )

    @validator("elastic_tensor", pre=True)
    def make_elastic_tensor(cls, val) -> ElasticTensor:
        """This custom validator is not strictly necessary but allows elastic_tensor
        to be passed as either MSONable dict, list (specifying the Voigt array)
        or the ElasticTensor class itself.
        """
        if isinstance(val, dict):
            return ElasticTensor.from_dict(val)
        if isinstance(val, (list, tuple)):
            return ElasticTensor(val)
        return val

    def __init__(
        cls,
        structure,
        material_id,
        calculator: Union[str, "Calculator"],
        prop_kwargs: Optional[dict] = None,
        **kwargs,
    ) -> None:
        """
        Args:
            structure (Structure): Pymatgen Structure object.
            material_id (str): MP ID.
            calculator (str | Calculator): ASE calculator or name of model to use as ML
                potential. See matcalc.util.UNIVERSAL_CALCULATORS for recognized names.
            prop_kwargs (dict): Keyword arguments for each matcalc PropCalc class.
                Recognized keys are RelaxCalc, ElasticityCalc, PhononCalc, EOSCalc.
            **kwargs: Passed to the PropertyDoc constructor.

        Returns:
            MLIPRelaxationDoc
        """
        calculator = get_universal_calculator(calculator)

        results = {}
        for prop_cls in (RelaxCalc, PhononCalc, EOSCalc, ElasticityCalc):
            kwds = (prop_kwargs or {}).get(prop_cls.__name__, {})
            results.update(prop_cls(calculator, **kwds).calc(structure))

        for key, val in results.items():
            # convert arrays to lists
            if hasattr(val, "tolist") and not isinstance(val, ElasticTensor):
                results[key] = val.tolist()

        super().__init__(
            structure=structure, material_id=material_id, **results, **kwargs
        )
