from pydantic import Field

from emmet.core.material_property import PropertyDoc


class ElasticityDoc(PropertyDoc):
    """
    Elasticity doc.
    """

    property_name: str = "elasticity"

    order: int = Field(..., description="Order of the elastic tensor.")

    strains = Field(..., description="Lagrangian strain tensors applied to structures.")
    cauchy_stresses = Field(
        ..., description="Cauchy stress tensors on strained structures."
    )

    elastic_tensor = Field(
        ...,
        description="Elastic tensor corresponding to IEEE orientation, symmetrized to "
        "crystal structure.",
    )
    compliance_tensor = Field(
        ..., description="Compilance tensor corresponing to IEEE orientation."
    )
    elastic_tensor_original = Field(
        ...,
        description="Elastic tensor corresponding to POSCAR (conventional standard "
        "cell) orientation unsymmetrized",
    )

    k_voigt: float = Field(..., description="Bulk modulus Voigt average.")
    k_reuss: float = Field(..., description="Bulk modulus Reuss average.")
    k_vrh: float = Field(..., description="Bulk modulus VRH average.")
    g_voigt: float = Field(..., description="Shear modulus Voigt average.")
    g_reuss: float = Field(..., description="Shear modulus Reuss average.")
    g_vrh: float = Field(..., description="Shear modulus VRH average.")

    snyder_ac: float = Field(...)
    snyder_total: float = Field(...)
    snyder_opt: float = Field(...)

    clarke_thermalcond: float = Field(...)
    cahill_thermalcond: float = Field(...)
    debye_temperature: float = Field(...)

    trans_v: float = Field(...)
    loong_v: float = Field(...)

    universal_anisotropy: float = Field(...)
    homogeneous_poisson: float = Field(...)
    y_mod: float = Field(...)
