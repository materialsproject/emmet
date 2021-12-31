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
        "cell) orientation, unsymmetrized",
    )
    ieee_format: MatrixVoigt = Field(
        None,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure",
    )


class ComplianceTensorDoc(BaseModel):
    raw: MatrixVoigt = Field(
        None,
        description="Compliance tensor corresponding to POSCAR (conventional standard "
        "cell)",
    )
    ieee_format: MatrixVoigt = Field(
        None, description="Compliance tensor corresponding to IEEE orientation"
    )


class DerivedProperties(BaseModel):
    """
    Derived elastic properties.

    For more explanation of the properties, see
    `pymatgen.analysis.elasticity.elastic.py`.
    """

    # derived properties from elastic tensor
    k_voigt: float = Field(None, description="Bulk modulus Voigt average")
    k_reuss: float = Field(None, description="Bulk modulus Reuss average")
    k_vrh: float = Field(None, description="Bulk modulus Voigt-Reuss-Hill average")
    g_voigt: float = Field(None, description="Shear modulus Voigt average")
    g_reuss: float = Field(None, description="Shear modulus Reuss average")
    g_vrh: float = Field(None, description="Shear modulus Voigt-Reuss-Hill average")
    universal_anisotropy: float = Field(
        None, description="Universal elastic anisotropy"
    )
    homogeneous_poisson: float = Field(None, description="Isotropic Poisson ratio")
    y_mod: float = Field(None, description="Young's modulus")

    # derived properties from elastic tensor and structure
    trans_v: float = Field(None, description="Transverse sound velocity (in SI units)")
    long_v: float = Field(None, description="Longitudinal sound velocity (in SI units)")
    snyder_ac: float = Field(
        None, description="Snyder's acoustic sound velocity (in SI units)"
    )
    snyder_opt: float = Field(
        None, description="Snyder's optical sound velocity (in SI units)"
    )
    snyder_total: float = Field(
        None, description="Snyder's total sound velocity (in SI units)"
    )
    clarke_thermalcond: float = Field(
        None, description="Clarke's thermal conductivity (in SI units)"
    )
    cahill_thermalcond: float = Field(
        None, description="Cahill's thermal conductivity (in SI units)"
    )
    debye_temperature: float = Field(
        None, description="Debye temperature (in SI units)"
    )


class FittingData(BaseModel):
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
        None, description="The deformations corresponding to each strain state"
    )
    optimization_task: List[MPID] = Field(
        None,
        description="Optimization task used to fit the elastic tensor, i.e. "
        "non-strained state",
    )
    deformation_tasks: List[MPID] = Field(
        None, description="Deformation tasks used to fit the elastic tensor"
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

    derived_properties: DerivedProperties = Field(
        None, description="Derived elastic properties"
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
        derived_property: Optional[DerivedProperties] = None,
        fitting_data: Optional[FittingData] = None,
        fitting_method: str = None,
        **kwargs,
    ):
        # TODO
        if compliance_tensor is None:
            pass
        if derived_property is None:
            pass

        return cls.from_structure(
            structure,
            material_id,
            elastic_tensor=elastic_tensor,
            compliance_tensor=compliance_tensor,
            order=order,
            derived_property=derived_property,
            fitting_data=fitting_data,
            fitting_method=fitting_method,
            include_structure=True,
            **kwargs,
        )
