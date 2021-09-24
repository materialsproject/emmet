from typing import List, Tuple

from pydantic import Field

from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D

# TODO, move to core.math?
VoigtVector = Tuple[float, float, float, float, float, float]
VoigtTensor = Tuple[
    VoigtVector, VoigtVector, VoigtVector, VoigtVector, VoigtVector, VoigtVector
]


class ElasticityDoc(PropertyDoc):
    """
    Elasticity doc.
    """

    property_name: str = "elasticity"

    order: int = Field(..., default=2, description="Order of the elastic tensor")

    strains: List[Matrix3D] = Field(
        ..., description="Lagrangian strain tensors applied to structures"
    )
    cauchy_stresses: List[Matrix3D] = Field(
        ..., description="Cauchy stress tensors on strained structures"
    )

    elastic_tensor: VoigtTensor = Field(
        ...,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure",
    )
    compliance_tensor: VoigtTensor = Field(
        ..., description="Compliance tensor corresponding to IEEE orientation"
    )
    elastic_tensor_original: VoigtTensor = Field(
        ...,
        description="Elastic tensor corresponding to POSCAR (conventional standard "
        "cell) orientation unsymmetrized",
    )

    k_voigt: float = Field(..., description="Bulk modulus Voigt average")
    k_reuss: float = Field(..., description="Bulk modulus Reuss average")
    k_vrh: float = Field(..., description="Bulk modulus Voigt-Reuss-Hill average")
    g_voigt: float = Field(..., description="Shear modulus Voigt average")
    g_reuss: float = Field(..., description="Shear modulus Reuss average")
    g_vrh: float = Field(..., description="Shear modulus Voigt-Reuss-Hill average")

    snyder_ac: float = Field(
        ..., description="Snyder's acoustic sound velocity (in SI units)"
    )
    snyder_opt: float = Field(
        ..., description="Snyder's optical sound velocity (in SI units)"
    )
    snyder_total: float = Field(
        ..., description="Snyder's total sound velocity (in SI units)"
    )

    clarke_thermalcond: float = Field(
        ..., description="Clarke's thermal conductivity (in SI units)"
    )
    cahill_thermalcond: float = Field(
        ..., description="Cahill's thermal conductivity (in SI units)"
    )
    debye_temperature: float = Field(..., description="Debye temperature (in SI units)")

    trans_v: float = Field(..., description="Transverse sound velocity (in SI units)")
    long_v: float = Field(..., description="Longitudinal sound velocity (in SI units)")

    universal_anisotropy: float = Field(..., description="Universal elastic anisotropy")
    homogeneous_poisson: float = Field(..., description="Isotropic Poisson ratio")
    y_mod: float = Field(..., description="Young's modulus")
