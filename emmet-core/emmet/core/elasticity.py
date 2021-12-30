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

    elastic_tensor_order: int = Field(
        default=2, description="Order of the elastic tensor"
    )

    elastic_tensor: VoigtTensor = Field(
        ...,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure",
    )
    elastic_tensor_original: VoigtTensor = Field(
        None,
        description="Elastic tensor corresponding to POSCAR (conventional standard "
        "cell) orientation, unsymmetrized",
    )
    compliance_tensor: VoigtTensor = Field(
        None, description="Compliance tensor corresponding to IEEE orientation"
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

    optimization_task: List[MPID] = Field(
        None,
        description="Optimization task used to calculate the elastic tensor, i.e. "
        "non-strained state",
    )

    deformation_tasks: List[MPID] = Field(
        None, description="Deformation tasks used to calculate the elastic tensor"
    )

    fitting_method: str = Field(
        None, description="Fitting method used to calculate the elastic tensor"
    )

    @classmethod
    def from_structure_and_elastic_tensor(
        cls,
        structure: Structure,
        material_id: MPID,
        elastic_tensor: VoigtTensor,
        elastic_tensor_original: VoigtTensor,
        order: int = 2,
        compliance_tensor: Optional[VoigtTensor] = None,
        strains: Optional[List[Matrix3D]] = None,
        cauchy_stresses: Optional[List[Matrix3D]] = None,
        derived_property: Optional[ElasticityDerivedProperty] = None,
        optimization_task: List[MPID] = None,
        deformation_tasks: List[MPID] = None,
        fitting_method: str = None,
        **kwargs,
    ):
        # TODO
        if compliance_tensor is None:
            pass
        if derived_property is None:
            pass

        # consistence check
        if strains is not None:
            if cauchy_stresses:
                assert len(strains) == len(cauchy_stresses), (
                    "Expect the same number of strains and cauchy stresses; got "
                    f"{len(strains)} and {len(cauchy_stresses)}, respectively."
                )

            if optimization_task is not None and deformation_tasks is not None:
                assert len(strains) == 1 + len(deformation_tasks), (
                    "Expect the number of strains be equal to 1 plus the number of "
                    f"deformation tasks; got {len(strains)} and "
                    f"1 + {len(deformation_tasks)}, respectively."
                )

        return cls.from_structure(
            structure,
            material_id,
            elastic_tensor_order=order,
            elastic_tensor=elastic_tensor,
            elastic_tensor_original=elastic_tensor_original,
            compliance_tensor=compliance_tensor,
            strains=strains,
            cauchy_stresses=cauchy_stresses,
            derived_property=derived_property,
            optimization_task=optimization_task,
            deformation_tasks=deformation_tasks,
            fitting_method=fitting_method,
            include_structure=True,
            **kwargs,
        )
