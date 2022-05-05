from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field
from pymatgen.analysis.elasticity.elastic import ElasticTensor, ElasticTensorExpansion
from pymatgen.analysis.elasticity.strain import Deformation, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.core.structure import Structure
from pymatgen.core.tensors import TensorMapping
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.common import Status
from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D, MatrixVoigt
from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings

STRAIN_COMP_TOL = 0.002


SETTINGS = EmmetSettings()


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

    # data of strained structures
    deformations: List[Matrix3D] = Field(
        description="Deformations corresponding to the strained structures"
    )
    strains: List[Matrix3D] = Field(
        description="Lagrangian strain tensors applied to structures"
    )
    cauchy_stresses: List[Matrix3D] = Field(
        description="Cauchy stress tensors on strained structures"
    )
    second_pk_stresses: List[Matrix3D] = Field(
        description="Second Piola–Kirchhoff stress tensors on structures"
    )
    deformation_tasks: List[MPID] = Field(
        None, description="Deformation tasks corresponding to the strained structures"
    )
    deformation_dir_names: List[str] = Field(
        None, description="Paths to the deformation tasks running directories"
    )

    # data of equilibrium structure
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
    bulk_modulus: BulkModulus = Field(None, description="Bulk modulus")
    shear_modulus: ShearModulus = Field(None, description="Shear modulus")
    sound_velocity: SoundVelocity = Field(None, description="Sound velocity")
    thermal_conductivity: ThermalConductivity = Field(
        None, description="Thermal conductivity"
    )
    young_modulus: float = Field(None, description="Young's modulus")
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

    state: Status = Field(
        None,
        description="State of the elasticity calculation, " "`successful` or `failed`",
    )

    @classmethod
    def from_deformations_and_stresses(
        cls,
        structure: Structure,
        material_id: MPID,
        deformations: List[Deformation],
        stresses: List[Stress],
        deformation_task_ids: Optional[List[MPID]] = None,
        deformation_dir_names: Optional[List[str]] = None,
        equilibrium_stress: Optional[Stress] = None,
        optimization_task_id: Optional[MPID] = None,
        optimization_dir_name: Optional[str] = None,
        fitting_method: str = "finite_difference",
        **kwargs,
    ):

        (
            p_deforms,
            p_strains,
            p_stresses,
            p_pk_stresses,
            p_task_ids,
            p_dir_names,
        ) = generate_primary_fitting_data(
            deformations, stresses, deformation_task_ids, deformation_dir_names
        )

        (
            d_deforms,
            d_strains,
            d_stresses,
            d_pk_stress,
            d_task_ids,
            d_dir_names,
        ) = generate_derived_fitting_data(structure, p_deforms, p_stresses)

        elastic_tensor = fit_elastic_tensor(
            p_strains + d_strains,
            p_pk_stresses + d_pk_stress,
            eq_stress=equilibrium_stress,
            fitting_method=fitting_method,
        )

        eq_stress = None if equilibrium_stress is None else equilibrium_stress.tolist()

        fitting_data = FittingData(
            deformations=[x.tolist() for x in p_deforms],
            strains=[x.tolist() for x in p_strains],
            cauchy_stresses=[x.tolist() for x in p_stresses],
            second_pk_stresses=[x.tolist() for x in p_pk_stresses],
            deformation_tasks=deformation_task_ids,
            deformation_dir_names=d_dir_names,
            equilibrium_cauchy_stress=eq_stress,
            optimization_task=optimization_task_id,
            optimization_dir_name=optimization_dir_name,
        )

        # elastic and compliance tensors, only round ieee format ones
        ieee_et = elastic_tensor.voigt_symmetrized.convert_to_ieee(structure)
        et_doc = ElasticTensorDoc(
            raw=elastic_tensor.voigt.tolist(),
            ieee_format=ieee_et.round(0).voigt.tolist(),
        )

        try:
            compliance = elastic_tensor.compliance_tensor
            compliance_ieee = ieee_et.compliance_tensor

            # compliance tensor, *1000 to convert units to TPa^-1, i.e. 10^-12 Pa,
            # assuming elastic tensor in units of GPa
            ct_doc = ComplianceTensorDoc(
                raw=(compliance * 1000).voigt.tolist(),
                ieee_format=(compliance_ieee * 1000).round(0).voigt.tolist(),
            )

            # derived properties
            # (should put it here since some derived properties also dependent on
            # compliance tensor)
            derived_props = get_derived_properties(structure, elastic_tensor)

            # check all
            state, warnings = sanity_check(
                structure, et_doc, p_strains + d_strains, derived_props
            )
        except np.linalg.LinAlgError as e:
            ct_doc = None
            derived_props = {}
            state = Status("failed")
            warnings = [
                f"Critical: cannot invert elastic tensor to get compliance tensor: {e}"
            ]

        return cls.from_structure(
            structure,
            material_id,
            order=2,
            state=state,
            elastic_tensor=et_doc,
            compliance_tensor=ct_doc,
            fitting_data=fitting_data,
            fitting_method=fitting_method,
            warnings=warnings,
            deprecated=False,
            **derived_props,
            **kwargs,
        )


def generate_primary_fitting_data(
    deforms: List[Deformation],
    stresses: List[Stress],
    task_ids: List[MPID] = None,
    dir_names: List[str] = None,
) -> Tuple[
    List[Deformation],
    List[Strain],
    List[Stress],
    List[Stress],
    Union[List[MPID], None],
    Union[List[str], None],
]:
    """
    Get the primary fitting data, i.e. data explicitly computed from a calculation.

    Args:
        deforms: deformations on the structure
        stresses: stresses on the structure
        task_ids: ids of the tasks that generate the data
        dir_names: dir names in which the calculations are performed
    """
    return _generate_fitting_data(deforms, stresses, task_ids, dir_names)


def generate_derived_fitting_data(
    structure: Structure,
    deforms: List[Deformation],
    stresses: List[Stress],
    symprec=SETTINGS.SYMPREC,
) -> Tuple[
    List[Deformation],
    List[Strain],
    List[Stress],
    List[Stress],
    Union[List[MPID], None],
    Union[List[str], None],
]:
    """
    Get the derived fitting data from symmetry operations on the primary fitting data.

    It can happen that multiple primary deformations can be mapped to the same derived
    deformation from different symmetry operations. In such cases, the stress for a
    derived deformation is the average of all derived stresses, each corresponding to a
    primary calculation. In doing so, we also check that:

    1. only independent derived strains are used
    2. for a specific derived strain, a primary deformation is only used once to
       obtain the average

    Args:
        structure: equilibrium structure
        deforms: primary deformations
        stresses: stresses corresponding to structure subject to primary deformations
        symprec: symmetry operation precision
    """

    sga = SpacegroupAnalyzer(structure, symprec=symprec)
    symmops = sga.get_symmetry_operations(cartesian=True)

    # primary deformation mapping (used only for checking purpose below)
    p_mapping = TensorMapping()
    for d in deforms:
        p_mapping[d] = d

    #
    # generated derived deforms
    #
    mapping = TensorMapping()
    for i, p_deform in enumerate(deforms):
        for op in symmops:
            d_deform = p_deform.transform(op)

            # sym op generates another primary deform
            if d_deform in p_mapping:
                continue

            # sym op generates a non-independent deform
            if not d_deform.is_independent():
                continue

            # seen this derived deform before
            if d_deform in mapping:

                # all the existing `i`
                current = [t[1] for t in mapping[d_deform]]

                if i not in current:
                    mapping[d_deform].append((op, i))

            # not seen this derived deform before
            else:
                mapping[d_deform] = [(op, i)]

    #
    # get average stress from derived deforms
    #
    derived_deforms = []
    derived_stresses = []

    for d_deform, op_set in mapping.items():
        symmops, p_indices = zip(*op_set)

        p_stresses = [stresses[i] for i in p_indices]
        d_stresses = [s.transform(op) for s, op in zip(p_stresses, symmops)]
        d_stress = Stress(np.average(d_stresses, axis=0))

        derived_deforms.append(d_deform)
        derived_stresses.append(d_stress)

    return _generate_fitting_data(derived_deforms, derived_stresses)


def _generate_fitting_data(
    deforms: List[Deformation],
    stresses: List[Stress],
    task_ids: List[MPID] = None,
    dir_names: List[str] = None,
) -> Tuple[
    List[Deformation],
    List[Strain],
    List[Stress],
    List[Stress],
    Union[List[MPID], None],
    Union[List[str], None],
]:
    size = len(deforms)
    assert len(stresses) == size
    if task_ids is not None:
        assert len(task_ids) == size
    if dir_names is not None:
        assert len(dir_names) == size

    strains = [d.green_lagrange_strain for d in deforms]
    second_pk_stress = [s.piola_kirchoff_2(d) for (s, d) in zip(stresses, deforms)]

    return deforms, strains, stresses, second_pk_stress, task_ids, dir_names


def fit_elastic_tensor(
    strains: List[Strain],
    stresses: List[Stress],
    eq_stress: Stress,
    fitting_method: str = "finite_difference",
    order: int = 2,
) -> ElasticTensor:
    """
    Fitting the elastic tensor.

    Args:
        strains: strains to fit the elastic tensor
        stresses: stresses to fit the elastic tensor
        eq_stress: equilibrium stress, i.e. stress on the relaxed structure
        fitting_method: method used to fit the elastic tensor:
            {`finite_difference`, `pseudoinverse`, `independent`}
        order: expansion order of the elastic tensor, 2 or 3

    Returns:
        fitted elastic tensor
    """

    if order > 2 or fitting_method == "finite_difference":

        # force finite diff if order > 2
        result = ElasticTensorExpansion.from_diff_fit(
            strains, stresses, eq_stress=eq_stress, order=order
        )
        if order == 2:
            result = ElasticTensor(result[0])
    elif fitting_method == "pseudoinverse":
        result = ElasticTensor.from_pseudoinverse(strains, stresses)
    elif fitting_method == "independent":
        result = ElasticTensor.from_independent_strains(
            strains, stresses, eq_stress=eq_stress
        )
    else:
        raise ValueError(f"Unsupported elastic fitting method {fitting_method}")

    return result


def get_derived_properties(structure: Structure, tensor: ElasticTensor):

    try:
        prop_dict = tensor.get_structure_property_dict(structure)
        prop_dict.pop("structure")
        structure_prop_computed = True

    except ValueError:
        prop_dict = tensor.property_dict
        structure_prop_computed = False

    dec = 3
    derived_prop = {
        "bulk_modulus": BulkModulus(
            voigt=np.round(prop_dict["k_voigt"], dec),
            reuss=np.round(prop_dict["k_reuss"], dec),
            vrh=np.round(prop_dict["k_vrh"], dec),
        ),
        "shear_modulus": ShearModulus(
            voigt=np.round(prop_dict["g_voigt"], dec),
            reuss=np.round(prop_dict["g_reuss"], dec),
            vrh=np.round(prop_dict["g_vrh"], dec),
        ),
        "young_modulus": np.round(prop_dict["y_mod"], dec),
        "homogeneous_poisson": np.round(prop_dict["homogeneous_poisson"], dec),
        "universal_anisotropy": np.round(prop_dict["universal_anisotropy"], dec),
    }

    if structure_prop_computed:
        derived_prop.update(
            {
                "sound_velocity": SoundVelocity(
                    transverse=prop_dict["trans_v"],
                    longitudinal=prop_dict["long_v"],
                    snyder_acoustic=prop_dict["snyder_ac"],
                    snyder_optical=prop_dict["snyder_opt"],
                    snyder_total=prop_dict["snyder_total"],
                ),
                "thermal_conductivity": ThermalConductivity(
                    clarke=prop_dict["clarke_thermalcond"],
                    cahill=prop_dict["cahill_thermalcond"],
                ),
                "debye_temperature": prop_dict["debye_temperature"],
            }
        )

    return derived_prop


def sanity_check(
    structure: Structure,
    elastic_doc: ElasticTensorDoc,
    strains: List[Strain],
    derived_props: Dict[str, Any],
) -> Tuple[Status, List[str]]:
    """
    Generates all warnings that apply to a fitted elastic tensor.

    Returns:
        state: state of the calculation
        warnings: all warning messages. Messages starting with `Critical` are the
            ones resulting in a `failed` state.
    """
    failed = False
    warnings = []

    # rank of all strains < 6?
    voigt_strains = [s.voigt for s in strains]
    rank = np.linalg.matrix_rank(voigt_strains)
    if rank != 6:
        failed = True
        warnings.append(
            f"Critical: insufficient number of valid strains. Expect the matrix of all "
            f"strains to be of 6, but got {rank}."
        )

    # if any([s.is_rare_earth_metal for s in structure.species]):
    #     warnings.append("Structure contains a rare earth element")

    # elastic tensor component, eigenvalues...
    et = np.asarray(elastic_doc.ieee_format)

    if np.any(et > 1e6):
        warnings.append("Elastic tensor has component larger than 1e6")

    eig_vals, _ = np.linalg.eig(et)
    if np.any(eig_vals < 0.0):
        warnings.append("Elastic tensor has negative eigenvalue")

    # TODO: these should be revisited. Are they complete, or only apply to materials
    #  with certain symmetry?
    c11, c12, c13 = et[0, 0:3]
    c23 = et[1, 2]
    if abs((c11 - c12) / c11) < 0.05 or c11 < c12:
        warnings.append("c11 and c12 are within 5% or c12 is greater than c11")
    if abs((c11 - c13) / c11) < 0.05 or c11 < c13:
        warnings.append("c11 and c13 are within 5% or c13 is greater than c11")
    if abs((c11 - c23) / c11) < 0.05 or c11 < c23:
        warnings.append("c11 and c23 are within 5% or c23 is greater than c11")

    # modulus
    for mod in ["bulk_modulus", "shear_modulus"]:
        doc = derived_props[mod]
        doc = doc.dict()
        for name in ["voigt", "reuss", "vrh"]:
            if doc[name] < 0:
                failed = True
                warnings.append(f"Critical: negative {name} {mod}")
            elif doc[name] < 2:
                warnings.append(f"{name} {mod} below 2 GPa.")
            elif doc[name] > 1000:
                warnings.append(f"{name} {mod} above 1000 GPa.")

    if failed:
        state = Status("failed")
    else:
        state = Status("successful")

    return state, warnings
