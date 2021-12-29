from typing import List, Optional, Tuple

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D
from emmet.core.mpid import MPID

# TODO, move to core.math?
VoigtVector = Tuple[float, float, float, float, float, float]
VoigtTensor = Tuple[
    VoigtVector, VoigtVector, VoigtVector, VoigtVector, VoigtVector, VoigtVector
]


class ElasticityDerivedProperty(BaseModel):
    """
    Derived elastic properties.
    """

    k_voigt: float = Field(None, description="Bulk modulus Voigt average")
    k_reuss: float = Field(None, description="Bulk modulus Reuss average")
    k_vrh: float = Field(None, description="Bulk modulus Voigt-Reuss-Hill average")
    g_voigt: float = Field(None, description="Shear modulus Voigt average")
    g_reuss: float = Field(None, description="Shear modulus Reuss average")
    g_vrh: float = Field(None, description="Shear modulus Voigt-Reuss-Hill average")

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

    trans_v: float = Field(None, description="Transverse sound velocity (in SI units)")
    long_v: float = Field(None, description="Longitudinal sound velocity (in SI units)")

    universal_anisotropy: float = Field(
        None, description="Universal elastic anisotropy"
    )
    homogeneous_poisson: float = Field(None, description="Isotropic Poisson ratio")
    y_mod: float = Field(None, description="Young's modulus")


class ElasticityDoc(PropertyDoc):
    """
    Elasticity doc.
    """

    property_name: str = "elasticity"

    order: int = Field(default=2, description="Order of the elastic tensor")

    elastic_tensor: VoigtTensor = Field(
        ...,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure",
    )
    compliance_tensor: VoigtTensor = Field(
        None, description="Compliance tensor corresponding to IEEE orientation"
    )
    elastic_tensor_original: VoigtTensor = Field(
        None,
        description="Elastic tensor corresponding to POSCAR (conventional standard "
        "cell) orientation unsymmetrized",
    )

    strains: List[Matrix3D] = Field(
        None, description="Lagrangian strain tensors applied to structures"
    )
    cauchy_stresses: List[Matrix3D] = Field(
        None, description="Cauchy stress tensors on strained structures"
    )

    derived_property: ElasticityDerivedProperty = Field(
        None, description="Derived elastic properties"
    )

    @classmethod
    def from_structures_and_elastic_tensor(
        cls,
        structure: Structure,
        material_id: MPID,
        elastic_tensor: VoigtTensor,
        elastic_tensor_original: VoigtTensor,
        derived_property: Optional[ElasticityDerivedProperty] = None,
        **kwargs,
    ):
        # TODO computing additional property that can be derived
        # compute derived properties, e.g. ieee tensor, compliance tensor

        return cls.from_structure(
            structure,
            material_id,
            elastic_tensor=elastic_tensor,
            elastic_tensor_original=elastic_tensor_original,
            derived_property=derived_property,
            include_structure=True,
            **kwargs,
        )
