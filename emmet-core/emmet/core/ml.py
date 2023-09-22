from importlib.metadata import PackageNotFoundError, version
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

    Properties:
    - metadata
        - material_id (str): MP ID
        - structure (Structure): pymatgen Structure object
        - deprecated (bool): whether this material is deprecated in MP
        - calculator (str): name of model used as ML potential.
        - version (str): version of matcalc used to generate this document
    - relaxation
        - final structure: relaxed pymatgen Structure object
        - energy (float): final energy in eV
        - volume (float): final volume in Angstrom^3
        - lattice parameters: a, b, c, alpha, beta, gamma
    - equation of state
        - eos (dict[str, list[float]]): with keys energies and volumes
        - bulk modulus (float): Birch-Murnaghan bulk modulus in GPa
    - phonon
        - temperatures (list[float]): temperatures in K
        - free energy (list[float]): Helmholtz energies at those temperatures in eV
        - entropy (list[float]): entropies at those temperatures in eV/K
        - heat capacities (list[float]): heat capacities at constant volume in eV/K
    - elasticity
        - elastic tensor (ElasticTensor): pymatgen ElasticTensor object
        - shear modulus (float): Voigt-Reuss-Hill shear modulus
        - bulk modulus (float): Voigt-Reuss-Hill bulk modulus
        - Young's modulus (float): Young's modulus
    """

    property_name = "mlip"

    # metadata
    structure: Structure = Field(description="Original structure")
    calculator: str = Field(
        description="Name of model used as ML potential. See matcalc.util.UNIVERSAL_CALCULATORS for recognized names."
    )
    version: str = Field(
        description="Version of matcalc used to generate this document"
    )

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
    eos: Dict[str, List[float]] = Field(
        description="dict with keys energies and volumes"
    )
    bulk_modulus_bm: float = Field(description="bm.b0_GPa")

    # phonons attributes
    temperatures: List[float] = Field(description="list of temperatures")
    free_energy: List[float] = Field(
        description="list of Helmholtz free energies at corresponding temperatures"
    )
    entropy: List[float] = Field(
        description="list of entropies at corresponding temperatures in eV/K"
    )
    heat_capacity: List[float] = Field(
        description="list of heat capacities at constant volume at corresponding "
        "temperatures in eV/K"
    )

    # elasticity attributes
    elastic_tensor: ElasticTensor = Field(
        description="pymatgen ElasticTensor in Voigt notation (GPa)"
    )
    shear_modulus_vrh: float = Field(
        description="Voigt-Reuss-Hill shear modulus based on elastic tensor"
    )
    bulk_modulus_vrh: float = Field(
        description="Voigt-Reuss-Hill bulk modulus based on elastic tensor"
    )
    youngs_modulus: float = Field(description="Young's modulus based on elastic tensor")

    # this custom validator is not strictly necessary but
    # allows elastic_tensors to be passed as MSONable dict, list (specifying
    # the Voigt array) or the class itself
    @validator("elastic_tensor", pre=True)
    def make_elastic_tensor(cls, val):
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

        model_name = (
            calculator if isinstance(calculator, str) else type(calculator).__name__
        )
        try:
            model_version = version(model_name)
        except PackageNotFoundError:
            model_version = "unknown"

        super().__init__(
            structure=structure,
            material_id=material_id,
            calculator=model_name,
            version=model_version,
            **results,
            **kwargs,
        )
