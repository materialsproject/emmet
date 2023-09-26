from typing import TYPE_CHECKING, Dict, List, Optional, Union

from matcalc.elasticity import ElasticityCalc
from matcalc.eos import EOSCalc
from matcalc.phonon import PhononCalc
from matcalc.relaxation import RelaxCalc
from matcalc.util import get_universal_calculator
from pydantic import Field, validator
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure

from emmet.core.elasticity import (
    BulkModulus,
    ElasticityDoc,
    ElasticTensorDoc,
    ShearModulus,
)

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator


class MLDoc(ElasticityDoc):
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
        - elastic_tensor (ElasticTensorDoc): pydantic model from emmet.core.elasticity
        - shear_modulus (ShearModulus): Voigt-Reuss-Hill shear modulus (single float)
        - bulk_modulus (BulkModulus): Voigt-Reuss-Hill bulk modulus (single float)
        - youngs_modulus (float): Young's modulus
    """

    property_name: str = "ml"

    # metadata
    structure: Structure = Field(description="Original structure")
    matcalc_version: Optional[str] = Field(
        None, description="Version of matcalc used to generate this document"
    )
    model_name: Optional[str] = Field(
        None, description="Name of model used as ML potential."
    )
    model_version: Optional[str] = Field(
        None, description="Version of model used as ML potential"
    )

    # relaxation attributes
    final_structure: Optional[Structure] = Field(
        None, description="ML-potential-relaxed structure"
    )
    energy: Optional[float] = Field(None, description="Final energy in eV")
    volume: Optional[float] = Field(None, description="Final volume in Angstrom^3")
    a: Optional[float] = Field(None, description="Lattice length a in Angstrom")
    b: Optional[float] = Field(None, description="Lattice length b in Angstrom")
    c: Optional[float] = Field(None, description="Lattice length c in Angstrom")
    alpha: Optional[float] = Field(None, description="Lattice angle alpha in degrees")
    beta: Optional[float] = Field(None, description="Lattice angle beta in degrees")
    gamma: Optional[float] = Field(None, description="Lattice angle gamma in degrees")

    # equation of state attributes
    eos: Optional[Dict[str, List[float]]] = Field(
        None, description="dict with keys energies and volumes"
    )
    bulk_modulus_bm: Optional[float] = Field(None, description="bm.b0_GPa")

    # phonons attributes
    temperatures: Optional[List[float]] = Field(
        None, description="list of temperatures"
    )
    free_energy: Optional[List[float]] = Field(
        None,
        description="list of Helmholtz free energies at corresponding temperatures",
    )
    entropy: Optional[List[float]] = Field(
        None, description="list of entropies at corresponding temperatures in eV/K"
    )
    heat_capacity: Optional[List[float]] = Field(
        None,
        description="list of heat capacities at constant volume at corresponding "
        "temperatures in eV/K",
    )

    # elasticity attributes
    # all inherited from ElasticityDoc

    @validator("elastic_tensor", pre=True)
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

    @validator("bulk_modulus", pre=True, always=True)
    def bulk_vrh_no_suffix(cls, new_key, values):
        """Map field bulk_modulus_vrh to bulk_modulus."""
        val = values.get("bulk_modulus_vrh", new_key)
        return BulkModulus(vrh=val)

    @validator("shear_modulus", pre=True, always=True)
    def shear_vrh_no_suffix(cls, new_key, values):
        """Map field shear_modulus_vrh to shear_modulus."""
        val = values.get("shear_modulus_vrh", new_key)
        return ShearModulus(vrh=val)

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
            MLDoc
        """
        calculator = get_universal_calculator(calculator)

        results = {}
        for prop_cls in (RelaxCalc, PhononCalc, EOSCalc, ElasticityCalc):
            kwds = (prop_kwargs or {}).get(prop_cls.__name__, {})
            results.update(prop_cls(calculator, **kwds).calc(structure))

        for key, val in results.items():
            # convert arrays to lists
            if hasattr(val, "tolist"):
                results[key] = val.tolist()

        super().__init__(
            structure=structure, material_id=material_id, **results, **kwargs
        )
