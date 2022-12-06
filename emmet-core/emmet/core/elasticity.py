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

SETTINGS = EmmetSettings()


class ElasticTensorDoc(BaseModel):
    raw: MatrixVoigt = Field(
        None, description="Elastic tensor corresponding to structure orientation (GPa)",
    )
    ieee_format: MatrixVoigt = Field(
        None, description="Elastic tensor corresponding to IEEE orientation (GPa)",
    )


class ComplianceTensorDoc(BaseModel):
    raw: MatrixVoigt = Field(
        None, description="Compliance tensor corresponding to structure orientation (TPa^-1)",
    )
    ieee_format: MatrixVoigt = Field(
        None, description="Compliance tensor corresponding to IEEE orientation (TPa^-1)",
    )


class BulkModulus(BaseModel):
    voigt: float = Field(None, description="Bulk modulus Voigt average (GPa)")
    reuss: float = Field(None, description="Bulk modulus Reuss average (Gpa)")
    vrh: float = Field(None, description="Bulk modulus Voigt-Reuss-Hill average (GPa)")


class ShearModulus(BaseModel):
    voigt: float = Field(None, description="Shear modulus Voigt average (GPa)")
    reuss: float = Field(None, description="Shear modulus Reuss average (GPa)")
    vrh: float = Field(None, description="Shear modulus Voigt-Reuss-Hill average (GPa)")


class SoundVelocity(BaseModel):

    transverse: float = Field(None, description="Transverse sound velocity (SI units)")
    longitudinal: float = Field(None, description="Longitudinal sound velocity (SI units)")
    snyder_acoustic: float = Field(None, description="Snyder's acoustic sound velocity (SI units)")
    snyder_optical: float = Field(None, description="Snyder's optical sound velocity (SI units)")
    snyder_total: float = Field(None, description="Snyder's total sound velocity (SI units)")


class ThermalConductivity(BaseModel):
    clarke: float = Field(None, description="Clarke's thermal conductivity (SI units)")
    cahill: float = Field(None, description="Cahill's thermal conductivity (SI units)")


class FittingData(BaseModel):
    """
    Data used to fit the elastic tensor.

    Note, this only consists of the explicitly calculated primary data.
    With the data here, one can redo the fitting to regenerate the elastic data,
    e.g. using `ElasticityDoc.from_deformations_and_stresses()`.
    """

    # data of strained structures
    deformations: List[Matrix3D] = Field(description="Deformations corresponding to the strained structures")
    strains: List[Matrix3D] = Field(description="Lagrangian strain tensors applied to structures")
    cauchy_stresses: List[Matrix3D] = Field(description="Cauchy stress tensors on strained structures")
    second_pk_stresses: List[Matrix3D] = Field(description="Second Piola–Kirchhoff stress tensors on structures")
    deformation_tasks: List[MPID] = Field(
        None, description="Deformation task ids corresponding to the strained structures",
    )
    deformation_dir_names: List[str] = Field(None, description="Paths to the running directories of deformation tasks")

    # data of equilibrium structure
    equilibrium_cauchy_stress: Matrix3D = Field(None, description="Cauchy stress tensor of the relaxed structure")
    optimization_task: MPID = Field(None, description="Optimization task corresponding to the relaxed structure")
    optimization_dir_name: str = Field(None, description="Path to the running directory of the optimization task")

    # derived strains stresses
    num_total_strain_stress_states: int = Field(
        None,
        description="Number of total strain--stress states used for fitting, i.e. the "
        "sum of explicitly calculated deformations and derived deformations from "
        "symmetry.",
    )


class CriticalMessage(BaseModel):
    FITTING = "Critical: cannot fit elastic tensor. Error: {}."
    COMPLIANCE = "Critical: cannot invert elastic tensor to get compliance tensor. Error: {}."
    STRAIN_RANK = (
        "Critical: insufficient number of valid strains. Expect the matrix of all "
        "strains to be of rank 6; got rank {}."
    )
    N_STATES = "Critical: Expect 24 total (primary plus derived) strain--stress states " "to fit the data; got {}."


class WarningMessage(BaseModel):
    NEGATIVE_EIGVAL = (
        "Elastic tensor has negative eigenvalue(s), indicating that the structure is " "mechanically unstable."
    )  # https://doi.org/10.1103/PhysRevB.90.224104
    NEGATIVE_MODULUS = "Negative modulus: {} {} is {}, indicating that the structure is mechanically " "unstable."
    SMALL_MODULUS = "Small modulus. {} {} is {}; smaller than {}."
    LARGE_MODULUS = "Large modulus. {} {} is {}; larger than {}."
    LARGE_YOUNG_MODULUS = "Large Young's modulus {}; larger than {}."
    LARGE_COMPONENT = "Elastic tensor has component larger than {}."


class ElasticityDoc(PropertyDoc):

    property_name: str = "elasticity"

    structure: Structure = Field(None, description="Structure to compute the elasticity")

    order: int = Field(default=2, description="Order of the expansion of the elastic tensor")

    elastic_tensor: ElasticTensorDoc = Field(None, description="Elastic tensor")

    compliance_tensor: ComplianceTensorDoc = Field(None, description="Compliance tensor")

    # derived properties
    bulk_modulus: BulkModulus = Field(None, description="Bulk modulus")
    shear_modulus: ShearModulus = Field(None, description="Shear modulus")
    sound_velocity: SoundVelocity = Field(None, description="Sound velocity")
    thermal_conductivity: ThermalConductivity = Field(None, description="Thermal conductivity")
    young_modulus: float = Field(None, description="Young's modulus (SI units)")
    universal_anisotropy: float = Field(None, description="Universal elastic anisotropy")
    homogeneous_poisson: float = Field(None, description="Homogeneous Poisson ratio")
    debye_temperature: float = Field(None, description="Debye temperature (SI units)")

    fitting_data: FittingData = Field(None, description="Data used to fit the elastic tensor")

    fitting_method: str = Field(None, description="Method used to fit the elastic tensor")

    state: Status = Field(
        None, description="State of the fitting/analysis: `successful` or `failed`",
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
        """
        Fitting the elastic tensor from deformation and stresses.

        Note, the elastic tensor are obtained by fitting to the Lagrangian strains
        and second Piola-Kirchhoff stresses. In continuum mechanics nomenclature,
        it's the `material elasticity tensor`. For more, see Section 6.5 of
        `Continuum Mechanics and Thermodynamics -- From Fundamental Concepts to
        Governing Equations` Tadmor, Miller, and Elliott, Cambridge University Press,
        2012.

        Args:
            structure: relaxed structure.
            material_id: material id.
            deformations: deformations applied to the relaxed structure that generate
                the strained structures.
            stresses: Cauchy stresses on the deformed structures. Expected units: GPa.
            deformation_task_ids: id of the deformation tasks.
            deformation_dir_names: directories where the deformation tasks are run.
            equilibrium_stress: Cauchy stress on the relaxed structure.
            optimization_task_id: id of the optimization task to relax the structure.
            optimization_dir_name: directory where the optimization task run.
            fitting_method: method used to fit the elastic tensor:
                {`finite_difference`, `pseudoinverse`, `independent`}.
        """

        CM = CriticalMessage()

        # primary fitting data
        p_deforms = deformations
        p_stresses = stresses
        (p_strains, p_pk_stresses, p_task_ids, p_dir_names,) = generate_primary_fitting_data(
            p_deforms, p_stresses, deformation_task_ids, deformation_dir_names
        )

        # derived fitting data
        (d_deforms, d_strains, d_stresses, d_pk_stresses,) = generate_derived_fitting_data(
            structure, p_strains, p_stresses
        )

        # fitting elastic tensor
        try:
            elastic_tensor = fit_elastic_tensor(
                p_strains + d_strains,
                p_pk_stresses + d_pk_stresses,
                eq_stress=equilibrium_stress,
                fitting_method=fitting_method,
            )

            # elastic and compliance tensors, only round ieee format ones
            ieee_et = elastic_tensor.voigt_symmetrized.convert_to_ieee(structure)
            et_doc = ElasticTensorDoc(raw=elastic_tensor.voigt.tolist(), ieee_format=ieee_et.round(0).voigt.tolist(),)

        except np.linalg.LinAlgError as e:
            et_doc = None
            ct_doc = None
            derived_props = {}
            state = Status("failed")
            warnings = [CM.FITTING.format(e)]

        else:
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
                all_strains = p_strains + d_strains
                state, warnings = sanity_check(
                    structure, et_doc, all_strains, derived_props  # type: ignore
                )

            except np.linalg.LinAlgError as e:
                ct_doc = None
                derived_props = {}
                state = Status("failed")
                warnings = [CM.COMPLIANCE.format(e)]

        # fitting data
        eq_stress = None if equilibrium_stress is None else equilibrium_stress.tolist()
        n_states = len(p_deforms) + len(d_deforms)
        if n_states != 24:
            warnings.append(CM.N_STATES.format(n_states))
            state = Status("failed")

        fitting_data = FittingData(
            deformations=[x.tolist() for x in p_deforms],  # type: ignore
            strains=[x.tolist() for x in p_strains],  # type: ignore
            cauchy_stresses=[x.tolist() for x in p_stresses],  # type: ignore
            second_pk_stresses=[x.tolist() for x in p_pk_stresses],  # type: ignore
            deformation_tasks=p_task_ids,
            deformation_dir_names=p_dir_names,
            equilibrium_cauchy_stress=eq_stress,
            optimization_task=optimization_task_id,
            optimization_dir_name=optimization_dir_name,
            num_total_strain_stress_states=n_states,
        )

        return cls.from_structure(
            structure,
            material_id,
            structure=structure,
            order=2,
            elastic_tensor=et_doc,
            compliance_tensor=ct_doc,
            fitting_data=fitting_data,
            fitting_method=fitting_method,
            warnings=warnings,
            state=state,
            deprecated=state == Status("failed"),
            **derived_props,
            **kwargs,
        )


def generate_primary_fitting_data(
    deforms: List[Deformation],
    stresses: List[Stress],
    task_ids: Optional[List[MPID]] = None,
    dir_names: Optional[List[str]] = None,
) -> Tuple[
    List[Strain], List[Stress], Union[List[MPID], None], Union[List[str], None],
]:
    """
    Get the primary fitting data, i.e. data obtained from a calculation.

    Args:
        deforms: primary deformations
        stresses: primary stresses
        task_ids: ids of the tasks that generate the data
        dir_names: directories where the calculations are performed

    Returns:
        strains: primary strains
        second_pk_stresses: primary second Piola-Kirchhoff stresses
        task_ids: ids of the tasks that generate the data
        dir_names: directories where the calculations are performed
    """
    size = len(deforms)
    assert len(stresses) == size
    if task_ids is not None:
        assert len(task_ids) == size
    if dir_names is not None:
        assert len(dir_names) == size

    strains = [d.green_lagrange_strain for d in deforms]
    second_pk_stresses = [s.piola_kirchoff_2(d) for (s, d) in zip(stresses, deforms)]

    return strains, second_pk_stresses, task_ids, dir_names


def generate_derived_fitting_data(
    structure: Structure, strains: List[Strain], stresses: List[Stress], symprec=SETTINGS.SYMPREC, tol: float = 0.002,
) -> Tuple[List[Deformation], List[Strain], List[Stress], List[Stress]]:
    """
    Get the derived fitting data from symmetry operations on the primary fitting data.

    It can happen that multiple primary deformations can be mapped to the same derived
    deformation from different symmetry operations. In such cases, the stress for a
    derived deformation is the average of all derived stresses, each corresponding to a
    primary calculation. In doing so, we also check to ensure that:
    1. only independent derived deformations are used
    2. for a specific derived strain, a primary deformation is only used (mapped)
       once to obtain the average

    Args:
        structure: relaxed structure
        strains: primary strains
        stresses: primary stresses
        symprec: symmetry operation precision
        tol: tolerance for comparing strains and also for determining whether the
            deformation corresponds to the train is independent. The elastic workflow
            use a minimum strain of 0.005, so the default tolerance of 0.002 should be
            able to distinguish different strain states.

    Returns:
        derived_deforms: derived deformations
        derived_strains: derived strains
        derived_stresses: derived Cauchy stresses
        derived_pk_stresses: derived second Piola-Kirchhoff stresses
    """

    sga = SpacegroupAnalyzer(structure, symprec=symprec)
    symmops = sga.get_symmetry_operations(cartesian=True)

    # primary strain mapping (used only for checking purpose below)
    p_mapping = TensorMapping(strains, strains, tol=tol)

    # Warnings:
    # Do not use deformations to replace strains in generating the derived fitting
    # data. More specifically, do not create TensorMapping using deformation. This is
    # because the Lagrangian strain is symmetric, but the deformation gradient is not.
    # Then, more derived data can be generated than enough/necessary, due to the
    # asymmetry of the deformation gradient.

    # generated derived deforms
    mapping = TensorMapping(tol=tol, tensors=[], values=[])
    for i, p_strain in enumerate(strains):
        for op in symmops:
            d_strain = p_strain.transform(op)

            # sym op generates another primary strain
            if d_strain in p_mapping:
                continue

            # sym op generates a non-independent deform
            if not d_strain.get_deformation_matrix().is_independent(tol=tol):
                continue

            # seen this derived deform before
            if d_strain in mapping:

                # all the existing `i`
                current = [t[1] for t in mapping[d_strain]]

                if i not in current:
                    mapping[d_strain].append((op, i))

            # not seen this derived deform before
            else:
                mapping[d_strain] = [(op, i)]

    # get average stress from derived deforms
    derived_strains = []
    derived_stresses = []
    derived_deforms = []
    derived_pk_stresses = []

    for d_strain, op_set in mapping.items():
        symmops, p_indices = zip(*op_set)

        p_stresses = [stresses[i] for i in p_indices]
        d_stresses = [s.transform(op) for s, op in zip(p_stresses, symmops)]
        d_stress = Stress(np.average(d_stresses, axis=0))

        derived_strains.append(d_strain)
        derived_stresses.append(d_stress)

        deform = d_strain.get_deformation_matrix()
        derived_deforms.append(deform)
        derived_pk_stresses.append(d_stress.piola_kirchoff_2(deform))

    return derived_deforms, derived_strains, derived_stresses, derived_pk_stresses


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
        strains: strains (primary and derived) to fit the elastic tensor
        stresses: stresses (primary and derived) to fit the elastic tensor
        eq_stress: equilibrium stress, i.e. stress on the relaxed structure
        fitting_method: method used to fit the elastic tensor:
            {`finite_difference`, `pseudoinverse`, `independent`}
        order: expansion order of the elastic tensor, 2 or 3

    Returns:
        fitted elastic tensor
    """

    if order > 2 or fitting_method == "finite_difference":

        # force finite diff if order > 2
        result = ElasticTensorExpansion.from_diff_fit(strains, stresses, eq_stress=eq_stress, order=order)
        if order == 2:
            result = ElasticTensor(result[0])
    elif fitting_method == "pseudoinverse":
        result = ElasticTensor.from_pseudoinverse(strains, stresses)
    elif fitting_method == "independent":
        result = ElasticTensor.from_independent_strains(strains, stresses, eq_stress=eq_stress)
    else:
        raise ValueError(f"Unsupported elastic fitting method {fitting_method}")

    return result


def get_derived_properties(structure: Structure, tensor: ElasticTensor) -> Dict[str, Any]:
    """
    Get derived elasticity properties.

    Args:
        structure: relaxed structure
        tensor: elastic tensor corresponding to the structure

    Returns:
        a dict of derived elasticity properties
    """

    try:
        prop_dict = tensor.get_structure_property_dict(structure)
        prop_dict.pop("structure")
        structure_prop_computed = True

    except ValueError:
        prop_dict = tensor.property_dict
        structure_prop_computed = False

    decimals = 3
    derived_prop = {
        "bulk_modulus": BulkModulus(
            voigt=np.round(prop_dict["k_voigt"], decimals),
            reuss=np.round(prop_dict["k_reuss"], decimals),
            vrh=np.round(prop_dict["k_vrh"], decimals),
        ),
        "shear_modulus": ShearModulus(
            voigt=np.round(prop_dict["g_voigt"], decimals),
            reuss=np.round(prop_dict["g_reuss"], decimals),
            vrh=np.round(prop_dict["g_vrh"], decimals),
        ),
        "young_modulus": np.round(prop_dict["y_mod"], 0),
        "homogeneous_poisson": np.round(prop_dict["homogeneous_poisson"], decimals),
        "universal_anisotropy": np.round(prop_dict["universal_anisotropy"], decimals),
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
                    clarke=prop_dict["clarke_thermalcond"], cahill=prop_dict["cahill_thermalcond"],
                ),
                "debye_temperature": prop_dict["debye_temperature"],
            }
        )

    return derived_prop


def sanity_check(
    structure: Structure, elastic_doc: ElasticTensorDoc, strains: List[Strain], derived_props: Dict[str, Any],
) -> Tuple[Status, List[str]]:
    """
    Post analysis to generate warnings if any.

    Returns:
        state: state of the calculation
        warnings: all warning messages. Messages starting with `Critical` are the
            ones resulting in a `failed` state.
    """
    failed = False
    warnings = []
    CM = CriticalMessage()
    WM = WarningMessage()

    # rank of all strains < 6?
    voigt_strains = [s.voigt for s in strains]
    rank = np.linalg.matrix_rank(voigt_strains)
    if rank != 6:
        failed = True
        warnings.append(CM.STRAIN_RANK.format(rank))

    # elastic tensor eigenvalues
    eig_vals, _ = np.linalg.eig(elastic_doc.raw)
    if np.any(eig_vals < 0.0):
        warnings.append(WM.NEGATIVE_EIGVAL)

    # elastic tensor individual components
    et = np.asarray(elastic_doc.ieee_format)

    tol = 1e6
    if np.any(et > tol):
        warnings.append(WM.LARGE_COMPONENT.format(tol))

    # modulus
    low = 2.0
    high = 1000.0
    for p in ["bulk_modulus", "shear_modulus"]:
        doc = derived_props[p]
        doc = doc.dict()
        p = p.replace("_", " ")
        for name in ["voigt", "reuss", "vrh"]:
            v = doc[name]
            if v < 0:
                failed = True
                warnings.append(WM.NEGATIVE_MODULUS.format(name, p, v))
            elif v < low:
                warnings.append(WM.SMALL_MODULUS.format(name, p, v, low))
            elif v > high:
                warnings.append(WM.LARGE_MODULUS.format(name, p, v, high))

    # young's modulus (note it is in Pa, not GPa)
    high = 1e12
    v = derived_props["young_modulus"]
    if v > high:
        warnings.append(WM.LARGE_YOUNG_MODULUS.format(v, high))

    if failed:
        state = Status("failed")
    else:
        state = Status("successful")

    return state, warnings
