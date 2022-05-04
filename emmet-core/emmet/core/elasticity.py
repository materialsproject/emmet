from typing import List, Optional

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D, MatrixVoigt
from emmet.core.mpid import MPID


class ElasticTensorDoc(BaseModel):
    raw: MatrixVoigt = Field(
        None,
        description="Elastic tensor corresponding to POSCAR (conventional standard "
        "cell) orientation, unsymmetrized. (in GPa)",
    )
    ieee_format: MatrixVoigt = Field(
        None,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure. (in GPa)",
    )


class ComplianceTensorDoc(BaseModel):
    raw: MatrixVoigt = Field(
        None,
        description="Compliance tensor corresponding to POSCAR (conventional standard "
        "cell). (in TPa^-1)",
    )
    ieee_format: MatrixVoigt = Field(
        None,
        description="Compliance tensor corresponding to IEEE orientation (in TPa^-1)",
    )


class BulkModulus(BaseModel):
    voigt: float = Field(None, description="Bulk modulus Voigt average")
    reuss: float = Field(None, description="Bulk modulus Reuss average")
    vrh: float = Field(None, description="Bulk modulus Voigt-Reuss-Hill average")


class ShearModulus(BaseModel):
    voigt: float = Field(None, description="Shear modulus Voigt average")
    reuss: float = Field(None, description="Shear modulus Reuss average")
    vrh: float = Field(None, description="Shear modulus Voigt-Reuss-Hill average")


class SoundVelocity(BaseModel):

    transverse: float = Field(
        None, description="Transverse sound velocity (in SI units)"
    )
    longitudinal: float = Field(
        None, description="Longitudinal sound velocity (in SI units)"
    )
    snyder_acoustic: float = Field(
        None, description="Snyder's acoustic sound velocity (in SI units)"
    )
    snyder_optical: float = Field(
        None, description="Snyder's optical sound velocity (in SI units)"
    )
    snyder_total: float = Field(
        None, description="Snyder's total sound velocity (in SI units)"
    )


class ThermalConductivity(BaseModel):
    clarke: float = Field(
        None, description="Clarke's thermal conductivity (in SI units)"
    )
    cahill: float = Field(
        None, description="Cahill's thermal conductivity (in SI units)"
    )


class FittingData(BaseModel):
    """
    Data to fit the elastic tensor.

    These are intended for the explicitly calculated primary data, not containing
    derived data from symmetry operations.
    """

    # data associated with deformation tasks
    strains: List[Matrix3D] = Field(
        None, description="Lagrangian strain tensors applied to structures"
    )
    cauchy_stresses: List[Matrix3D] = Field(
        None, description="Cauchy stress tensors on strained structures"
    )
    second_pk_stresses: List[Matrix3D] = Field(
        None, description="Second Piola–Kirchhoff stress tensors on structures"
    )
    deformations: List[Matrix3D] = Field(
        None, description="Deformations corresponding to the strained structures"
    )
    deformation_tasks: List[MPID] = Field(
        None, description="Deformation tasks corresponding to the strained structures"
    )
    deformation_dir_name: List[str] = Field(
        None, description="Paths to the deformation tasks running directories"
    )

    # data associated with optimization task
    equilibrium_cauchy_stress: Matrix3D = Field(
        None, description="Cauchy stress tensor of the equilibrium (relaxed) structure"
    )
    optimization_task: MPID = Field(
        None, description="Optimization task corresponding to the relaxed structure"
    )
    optimization_dir_name: str = Field(
        None, description="Path to the optimization task running directory"
    )


class ElasticityDoc(PropertyDoc):
    """
    Elasticity doc.
    """

    property_name: str = "elasticity"

    elastic_tensor: ElasticTensorDoc = Field(None, description="Elastic tensor")

    compliance_tensor: ComplianceTensorDoc = Field(
        None, description="Compliance tensor"
    )

    order: int = Field(
        default=2, description="Order of the expansion of the elastic tensor"
    )

    # derived properties
    k: BulkModulus = Field(None, description="Bulk modulus")
    g: ShearModulus = Field(None, description="Shear modulus")
    v: SoundVelocity = Field(None, description="Sound velocity")
    kappa: ThermalConductivity = Field(None, description="Thermal conductivity")
    y_mod: float = Field(None, description="Young's modulus")
    universal_anisotropy: float = Field(
        None, description="Universal elastic anisotropy"
    )
    homogeneous_poisson: float = Field(None, description="Isotropic Poisson ratio")
    debye_temperature: float = Field(
        None, description="Debye temperature (in SI units)"
    )

    fitting_data: FittingData = Field(
        None, description="Data used to fit the elastic tensor"
    )

    fitting_method: str = Field(
        None, description="Method used to fit the elastic tensor"
    )

    @classmethod
    def from_structure_and_elastic_tensor(
        cls,
        structure: Structure,
        material_id: MPID,
        elastic_tensor: ElasticTensorDoc,
        *,
        order: int = 2,
        compliance_tensor: Optional[ComplianceTensorDoc] = None,
        derived_properties: Optional[DerivedProperties] = None,
        fitting_data: Optional[FittingData] = None,
        fitting_method: str = None,
        **kwargs,
    ):

        return cls.from_structure(
            structure,
            material_id,
            elastic_tensor=elastic_tensor,
            compliance_tensor=compliance_tensor,
            order=order,
            derived_properties=derived_properties,
            fitting_data=fitting_data,
            fitting_method=fitting_method,
            include_structure=True,
            **kwargs,
        )
