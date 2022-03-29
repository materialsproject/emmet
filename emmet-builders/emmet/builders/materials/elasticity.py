import itertools
from datetime import datetime
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np
from maggma.core import Builder, Store
from pydash.objects import get
from pymatgen.analysis.elasticity.elastic import ElasticTensor, ElasticTensorExpansion
from pymatgen.analysis.elasticity.strain import Deformation, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.core import Structure
from pymatgen.core.tensors import TensorMapping
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.elasticity import (
    ComplianceTensorDoc,
    DerivedProperties,
    ElasticityDoc,
    ElasticTensorDoc,
    FittingData,
)
from emmet.core.material import PropertyOrigin
from emmet.core.math import MatrixVoigt
from emmet.core.utils import jsanitize

# TODO should these be moved to SETTINGS?
STRAIN_COMP_TOL = 0.002  # tolerance for comparing strains
DEFORM_COMP_TOL = 1e-5  # tolerance for comparing deformations
LATTICE_COMP_TOL = 1e-5  # tolerance for comparing lattice
SYMPREC = 0.1  # symmetry precision

DEFORM_TASK_LABEL = "elastic deformation"
OPTIM_TASK_LABEL = "elastic structure optimization"


class ElasticityBuilder(Builder):
    def __init__(
        self,
        tasks: Store,
        materials: Store,
        elasticity: Store,
        query: Optional[Dict] = None,
        incremental: bool = None,
        **kwargs,
    ):
        """
        Creates an elastic collection for materials.

        Args:
            tasks: Store of tasks
            materials: Store of materials properties
            elasticity: Store of elastic properties
            query: dictionary to limit tasks to be analyzed
            incremental: whether to use a lu_filter based on the current datetime.
                Set to False if target is empty, but True if not.
        """

        self.tasks = tasks
        self.materials = materials
        self.elasticity = elasticity
        self.query = query if query is not None else {}
        self.incremental = incremental
        self.kwargs = kwargs

        # TODO enable this
        ## By default, incremental
        # if incremental is None:
        #    self.elasticity.connect()
        #    if self.elasticity.count() > 0:
        #        self.incremental = True
        #    else:
        #        self.incremental = False
        # else:
        #    self.incremental = incremental

        self.start_date = datetime.utcnow()

        super().__init__(sources=[tasks, materials], targets=[elasticity], **kwargs)

    def ensure_index(self):
        self.tasks.ensure_index("nsites")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index("last_updated")

        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")

        self.elasticity.ensure_index("optimization_task_id")
        self.elasticity.ensure_index("last_updated")

    def get_items(self) -> List[Dict]:
        """
        Gets all items to process into materials documents

        Returns:
            generator of task docs of the same material
        """

        self.logger.info("Elastic Builder Started")

        self.ensure_index()

        cursor = self.materials.query(
            criteria=self.query, properties=["material_id", "task_ids"]
        )

        # query for tasks
        query = self.query.copy()
        query["task_label"] = {"$regex": f"({DEFORM_TASK_LABEL})|({OPTIM_TASK_LABEL})"}

        for n, doc in enumerate(cursor):
            self.logger.debug(f"Getting material_id {doc['material_id']}; index {n}")

            # update query with task_ids
            task_ids = [int(i) for i in doc["task_ids"]]
            query["task_id"] = {"$in": task_ids}

            projections = [
                "output",
                "input",
                "completed_at",
                "transmuter",
                "task_id",
                "task_label",
                "formula_pretty",
                "dir_name",
            ]

            task_cursor = self.tasks.query(criteria=query, properties=projections)
            tasks = list(task_cursor)

            yield tasks

    def process_item(self, item: List[Dict]) -> List[Dict]:
        """
        Process all tasks belong to the same material.

        There can be multiple optimization tasks for the same material due to, e.g.
        later fixes of earlier calculations. The optimization task with later completed
        time is selected.

        As a result, there can be multiple deformation tasks corresponding to the
        same deformation, and the deformation tasks are filtered by:
        - VASP INCAR params
        - task completion time

        Args:
            item: a list of tasks doc that belong to the same material

        Returns:
            an elasticity document, represented as a dict
        """

        grouped = group_deform_tasks_by_opt_task(item, self.logger)

        elastic_docs = []
        for opt_tasks, deform_tasks in grouped:

            # filter opt and deform tasks such that there is only one opt task and
            # the deformation tasks are independent
            opt_task = filter_opt_tasks_by_time(opt_tasks, self.logger)
            deform_tasks = filter_deform_tasks_by_incar(opt_task, deform_tasks)
            deform_tasks = filter_deform_tasks_by_time(
                opt_task, deform_tasks, self.logger
            )

            doc = analyze_elastic_data(opt_task, deform_tasks, self.logger)
            if doc:
                doc = jsanitize(doc.dict(), allow_bson=True)
                elastic_docs.append(doc)

            return elastic_docs

    def update_targets(self, items: List[List[Dict]]):
        """
        Insert the new elasticity docs into the elasticity collection.

        Args:
            items: elastic docs
        """
        items = list(itertools.chain.from_iterable(items))

        self.logger.info(f"Updating {len(items)} elastic documents")

        self.elasticity.update(items, key="material_id")


def filter_opt_tasks_by_time(opt_tasks: List[Dict], logger) -> Dict:
    """
    If there are more than one optimization tasks with the same lattice, select the
    latest completed one.

    Args:
        opt_tasks: the optimization tasks
        logger:

    Returns:
        latest optimization task
    """

    if len(opt_tasks) > 1:

        # TODO what's the difference of `completed_at` and `last_updated` for a
        #  task? Ask Matt or Jason
        completed = [(datetime.fromisoformat(t["completed_at"]), t) for t in opt_tasks]
        sorted_by_completed = sorted(completed, key=lambda pair: pair[0])
        latest_pair = sorted_by_completed[-1]
        result = latest_pair[1]

        task_ids = [t["task_id"] for t in opt_tasks]
        logger.warning(
            f"{len(opt_tasks)} optimization tasks {task_ids} have the same "
            f"lattice; the latest one {result['task_id']} selected."
        )

    else:
        result = opt_tasks[0]

    return result


def filter_deform_tasks_by_incar(
    opt_task: Dict,
    deform_tasks: List[Dict],
    fields: Sequence[str] = ("LREAL", "ENCUT"),
) -> List[Dict]:
    """
    Filter deformation tasks by matching INCAR fields to those of the optimization
    tasks.

    Args:
        opt_task: optimization task
        deform_tasks: deformation tasks
        fields: the INCAR fields to match

    Returns:
        selected deformation tasks
    """
    # TODO what is the difference of `input` and `orig_inputs` for a task? which to use?
    opt_incar_values = {k: opt_task["input"]["incar"][k] for k in fields}

    selected = []
    for task in deform_tasks:
        incar_values = {k: task["input"]["incar"][k] for k in fields}
        if incar_values == opt_incar_values:
            selected.append(task)

    return selected


def filter_deform_tasks_by_time(
    opt_task: Dict, deform_tasks: [List[Dict]], logger
) -> List[Dict]:
    """
    For deformation tasks with the same deformation, select the latest completed one.

    Args:
        opt_task: optimization task
        deform_tasks: the deformation tasks
        logger:

    Returns:
        filtered deformation tasks
    """

    structure = Structure.from_dict(opt_task["output"]["structure"])

    d2t = TensorMapping(tol=DEFORM_COMP_TOL)

    for doc in deform_tasks:
        deformed_structure = Structure.from_dict(doc["output"]["structure"])
        deform = Deformation(get_deformation(structure, deformed_structure))

        # assume only one deformation, should already be checked in
        # `group_by_parent_lattice()`
        stored_deform = doc["transmuter"]["transformation_params"][0]["deformation"]

        if not np.allclose(deform, stored_deform, atol=DEFORM_COMP_TOL):
            opt_task_id = opt_task["task_id"]
            deform_task_id = doc["task_id"]
            logger.debug(
                "Inequivalent calculated and stored deformations for optimization task "
                f"{opt_task_id} and deformation task {deform_task_id}."
            )

        if deform in d2t:
            current = datetime.fromisoformat(doc["completed_at"])
            exist = datetime.fromisoformat(d2t[deform]["completed_at"])
            if current > exist:
                d2t[deform] = doc
        else:
            d2t[deform] = doc

    return list(d2t.values())


def analyze_elastic_data(
    opt_task: Dict, deform_tasks: List[Dict], logger
) -> ElasticityDoc:
    """
    Analyze optimization task and deformation tasks to fit elastic tensor.

    This currently only deal with second order elastic tensor.

    Args:
        opt_task: task doc corresponding to optimization
        deform_tasks: task docs corresponding to deformations
        logger:

    Returns:
        elastic document with fitted elastic tensor and analysis
    """

    structure = Structure.from_dict(opt_task["output"]["structure"])
    eq_stress = -0.1 * Stress(opt_task["output"]["stress"])

    # prepare fitting data
    primary_data = generate_primary_fitting_data(deform_tasks)
    derived_data = generate_derived_fitting_data(structure, primary_data)
    full_data = primary_data + derived_data

    # fitting elastic tensor
    fitting_method = "finite_difference"
    pk_stresses = [d["second_pk_stress"] for d in full_data]

    strains = [d["strain"] for d in full_data]
    v_strains = [s.zeroed(STRAIN_COMP_TOL).voigt for s in strains]
    if np.linalg.matrix_rank(v_strains) != 6:
        task_ids = [opt_task["task_id"]] + [t["task_id"] for t in deform_tasks]
        logger.info(f"Insufficient valid strains for tasks {task_ids}. Skipped.")
        return None

    elastic_tensor = fit_elastic_tensor(
        strains, pk_stresses, eq_stress=eq_stress, fitting_method=fitting_method
    )

    #
    # Assemble data to ElasticityDoc
    #

    # fitting data for provenance tracking
    fitting_data = FittingData(
        strains=[d["strain"].tolist() for d in primary_data],
        cauchy_stresses=[d["cauchy_stress"].tolist() for d in primary_data],
        second_pk_stresses=[d["second_pk_stress"].tolist() for d in primary_data],
        deformations=[d["deformation"].tolist() for d in primary_data],
        deformation_tasks=[d["task_id"] for d in primary_data],
        deformation_dir_name=[d["dir_name"] for d in primary_data],
        equilibrium_cauchy_stress=eq_stress.tolist(),
        optimization_task=opt_task["task_id"],
        optimization_dir_name=opt_task["dir_name"],
    )
    # origins store the same info as optimization_task and deformation_tasks
    opt_origin = [PropertyOrigin(name="optimization", task_id=opt_task["task_id"])]
    deform_origins = [
        PropertyOrigin(name="deformation", task_id=d["task_id"]) for d in primary_data
    ]
    origins = opt_origin + deform_origins

    # elastic tensor, ieee format is symmetrized and rounded
    ieee_et = elastic_tensor.voigt_symmetrized.convert_to_ieee(structure)
    et_doc = ElasticTensorDoc(
        raw=sanitize_elastic(elastic_tensor),
        ieee_format=sanitize_elastic(ieee_et.zeroed(0.01).round(0)),
    )

    # compliance tensor, *1000 to convert units to TPa^-1, i.e. 10^-12 Pa
    ct_doc = ComplianceTensorDoc(
        raw=sanitize_elastic(elastic_tensor.compliance_tensor * 1000),
        ieee_format=sanitize_elastic(ieee_et.compliance_tensor * 1000),
    )

    # derived property
    derived_props = get_derived_properties(structure, elastic_tensor, logger)

    # state and warnings
    state, warnings = get_state_and_warnings(structure, et_doc, derived_props)

    # TODO, should material_id be something else
    elastic_doc = ElasticityDoc.from_structure_and_elastic_tensor(
        structure=structure,
        material_id=opt_task["task_id"],
        order=2,
        elastic_tensor=et_doc,
        compliance_tensor=ct_doc,
        derived_properties=derived_props,
        fitting_data=fitting_data,
        fitting_method=fitting_method,
        origins=origins,
        # state=state,
        warnings=warnings,
    )

    return elastic_doc


def generate_primary_fitting_data(deform_tasks: List[Dict]) -> List[Dict]:
    """
    Get the fitting data from primary deformation tasks, i.e. the explicitly computed
        tasks.

    Args:
        deform_tasks: the deformation tasks

    Returns:
       deformation, strain, and stresses for the deformation tasks.
    """

    primary_data = []
    for doc in deform_tasks:
        deform = Deformation(
            doc["transmuter"]["transformation_params"][0]["deformation"]
        )
        strain = deform.green_lagrange_strain
        cauchy_stress = -0.1 * Stress(doc["output"]["stress"])
        second_pk_stress = cauchy_stress.piola_kirchoff_2(deform)

        data = {
            "deformation": deform,
            "strain": strain,
            "cauchy_stress": cauchy_stress,
            "second_pk_stress": second_pk_stress,
            "task_id": doc["task_id"],
            "dir_name": doc["dir_name"],
        }

        primary_data.append(data)

    return primary_data


def generate_derived_fitting_data(
    structure: Structure, primary_data: List[Dict]
) -> List[Dict]:
    """
    Generate implicit calculations from symmetry operations.

    Multiple primary calculations can be mapped to the same derived deformation from
    different symmetry operations, and the stress for a derived deformation is the
    average of all derived stresses, each corresponding to a primary calculation.

    Args:
        structure:
        primary_data:

    Returns:
    """

    primary_calcs_by_strain = TensorMapping(tol=STRAIN_COMP_TOL)
    for calc in primary_data:
        primary_calcs_by_strain[calc["strain"]] = calc

    sga = SpacegroupAnalyzer(structure, symprec=SYMPREC)
    symmops = sga.get_symmetry_operations(cartesian=True)

    # generate all derived calculations by symmetry operations on primary calculations
    derived_calcs_by_strain = TensorMapping(tol=STRAIN_COMP_TOL)
    for p_strain, calc in primary_calcs_by_strain.items():
        p_task_id = calc["task_id"]

        for op in symmops:
            d_strain = p_strain.transform(op)

            # filter strains by those which are independent and not in primary calcs
            if (
                d_strain.get_deformation_matrix().is_independent(tol=STRAIN_COMP_TOL)
                and not d_strain in primary_calcs_by_strain
            ):
                # derived strain seen before
                if d_strain in derived_calcs_by_strain:
                    curr_set = derived_calcs_by_strain[d_strain]
                    curr_task_ids = [c[1] for c in curr_set]
                    if p_task_id not in curr_task_ids:
                        curr_set.append((op, p_task_id))
                else:
                    derived_calcs_by_strain[d_strain] = [(op, p_task_id)]

    # process derived calcs
    primary_calcs_by_id = {calc["task_id"]: calc for calc in primary_data}

    derived_data = []
    for d_strain, calc_set in derived_calcs_by_strain.items():
        symmops, task_ids = zip(*calc_set)

        p_strains = [Strain(primary_calcs_by_id[i]["strain"]) for i in task_ids]
        p_stresses = [primary_calcs_by_id[i]["cauchy_stress"] for i in task_ids]

        derived_strains = [s.transform(op) for s, op in zip(p_strains, symmops)]
        derived_stresses = [s.transform(op) for s, op in zip(p_stresses, symmops)]

        # check derived strains are the same
        for derived_strain in derived_strains:
            if not np.allclose(derived_strain, d_strain, atol=STRAIN_COMP_TOL):
                raise ValueError("Issue with derived strains")

        # primary information that lead to the derived calculations
        input_tasks = [
            {
                "task_id": i,
                "strain": task_strain,
                "cauchy_stress": task_stress,
                "symmop": op,
            }
            for i, task_strain, task_stress, op in zip(
                task_ids, p_strains, p_stresses, symmops
            )
        ]

        deform = d_strain.get_deformation_matrix()

        # average stresses
        cauchy_stress = Stress(np.average(derived_stresses, axis=0))
        pk_stress = cauchy_stress.piola_kirchoff_2(deform)

        data = {
            "deformation": deform,
            "strain": d_strain,
            "cauchy_stress": cauchy_stress,
            "second_pk_stress": pk_stress,
            "input_tasks": input_tasks,
        }

        derived_data.append(data)

    return derived_data


def group_deform_tasks_by_opt_task(
    docs: Union[Iterator[Dict], List[Dict]], logger
) -> List[Tuple[List[Dict], List[Dict]]]:
    """
    Group deformation tasks by equivalent lattices to optimization task(s).

    Because of repeated calculations, multiple optimization tasks may be grouped
    together.

    Basically the same as group_by_parent_lattice(), except two additional steps:
        - find the optimization and using that as the grouping parameter
        - filter docs that don't include an optimization and deformations

    Args:
        docs: task docs
        logger:

    Returns:
        [([optimization_task], [deformation_task])]
    """

    tasks_by_lattice = group_by_parent_lattice(docs, logger)

    tasks_by_opt_task = []
    for _, task_set in tasks_by_lattice:
        opt_tasks = [t for t in task_set if OPTIM_TASK_LABEL in t["task_label"]]
        deform_tasks = [t for t in task_set if DEFORM_TASK_LABEL in t["task_label"]]

        if opt_tasks and deform_tasks:
            tasks_by_opt_task.append((opt_tasks, deform_tasks))
        else:
            task_ids = [t["task_id"] for t in task_set]
            if not opt_tasks:
                logger.debug(f"No structure optimization task among tasks {task_ids}")
            else:
                logger.debug(f"No deformation tasks among tasks {task_ids}")

    return tasks_by_opt_task


def group_by_parent_lattice(docs: Union[Iterator[Dict], List[Dict]], logger):
    """
    Groups a set of task documents by parent lattice equivalence.

    Args:
        docs: task docs
        logger:

    Returns:
        [(lattice, List[tasks])], tuple of lattice and a list of tasks with the same
        lattice before deformation
    """

    docs_by_lattice = []
    for doc in docs:

        sim_lattice = get(doc, "output.structure.lattice.matrix")

        if DEFORM_TASK_LABEL in doc["task_label"]:
            transform_params = doc["transmuter"]["transformation_params"]
            if len(transform_params) != 1:
                logger.warning(
                    f"Expect only one transformations; got {len(transform_params)} "
                    f"for task {doc['task_id']}."
                )
            deform = transform_params[0]["deformation"]
            parent_lattice = np.dot(sim_lattice, np.transpose(np.linalg.inv(deform)))
        else:
            parent_lattice = np.array(sim_lattice)

        match = False
        for unique_lattice, lattice_docs in docs_by_lattice:
            match = np.allclose(unique_lattice, parent_lattice, atol=LATTICE_COMP_TOL)
            if match:
                lattice_docs.append(doc)
                break
        if not match:
            docs_by_lattice.append((parent_lattice, [doc]))

    return docs_by_lattice


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
        strains: all strains
        stresses: all stresses
        eq_stress: equilibrium stress, i.e. stress on the relaxed structure
        fitting_method: method used to fit the elastic tensor, `finite_difference` |
            `pseudoinverse` | `independent`.
        order: expansion order of the elastic tensor, 2 | 3.

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


def get_deformation(structure, deformed_structure) -> np.ndarray:
    """
    Args:
        structure (Structure): undeformed structure
        deformed_structure (Structure): deformed structure

    Returns:
        deformation matrix
    """
    ulatt = structure.lattice.matrix
    dlatt = deformed_structure.lattice.matrix
    return np.transpose(np.dot(np.linalg.inv(ulatt), dlatt))


def get_derived_properties(
    structure: Structure, tensor: ElasticTensor, logger
) -> DerivedProperties:
    """
    Get derived properties.
    """

    try:
        prop_dict = tensor.get_structure_property_dict(structure)
        prop_dict.pop("structure")

    except ValueError:
        logger.warning("Negative K or G found, structure property dict not computed")
        prop_dict = tensor.property_dict

    for k, v in prop_dict.items():
        if k in ["homogeneous_poisson", "universal_anisotropy"]:
            prop_dict[k] = np.round(v, 2)
        else:
            prop_dict[k] = np.round(v, 0)

    derived_props = DerivedProperties(**prop_dict)

    return derived_props


def get_state_and_warnings(
    structure: Structure,
    elastic_doc: ElasticTensorDoc,
    derived_props: DerivedProperties,
) -> [str, List[str]]:
    """
    Generates all warnings that apply to a fitted elastic tensor.

    Args:
        structure: structure for which elastic tensor is determined
        elastic_doc: elastic tensor for which to determine state and warnings
        derived_props: derived elastic properties

    Returns:
        state: state of the calculations: `successful`|`warning`|`failed`
        warnings: list of warning messages
    """

    elastic_doc = elastic_doc.dict()
    derived_props = derived_props.dict()

    warnings = []

    if any([s.is_rare_earth_metal for s in structure.species]):
        warnings.append("Structure contains a rare earth element")

    et = np.asarray(elastic_doc["ieee_format"])
    eig_vals, _ = np.linalg.eig(et)
    if np.any(eig_vals < 0.0):
        warnings.append("Elastic tensor has a negative eigenvalue")

    # TODO: these should be revisited at some point, are they complete?
    #  I think they might only apply to cubic systems
    c11, c12, c13 = et[0, 0:3]
    c23 = et[1, 2]
    if abs((c11 - c12) / c11) < 0.05 or c11 < c12:
        warnings.append("c11 and c12 are within 5% or c12 is greater than c11")
    if abs((c11 - c13) / c11) < 0.05 or c11 < c13:
        warnings.append("c11 and c13 are within 5% or c13 is greater than c11")
    if abs((c11 - c23) / c11) < 0.05 or c11 < c23:
        warnings.append("c11 and c23 are within 5% or c23 is greater than c11")

    moduli = ["k_voigt", "k_reuss", "k_vrh", "g_voigt", "g_reuss", "g_vrh"]
    moduli_dict = {s: derived_props[s] for s in moduli}
    moduli_vals = np.asarray(list(moduli_dict.values()))
    if np.any(moduli_vals < 2.0):
        warnings.append("One or more K, G below 2 GPa")
    if np.any(moduli_vals > 1000.0):
        warnings.append("One or more K, G above 1000 GPa")

    # if elastic_doc["order"] == 3:
    #     if elastic_doc.get("average_linear_thermal_expansion", 0) < -0.1:
    #         warnings.append("Negative thermal expansion")
    #     if len(elastic_doc["strains"]) < 80:
    #         warnings.append("Fewer than 80 strains, TOEC may be deficient")

    if moduli_dict["k_vrh"] < 0 or moduli_dict["g_vrh"] < 0:
        state = "failed"
    elif warnings:
        state = "warning"
    else:
        state = "successful"

    return state, warnings


def sanitize_elastic(
    tensor: Union[ElasticTensor, ElasticTensorExpansion]
) -> MatrixVoigt:
    """
    Sanitize elastic tensor objects.

    Args:
        tensor: elastic tensor to be sanitized

    Returns:
        voigt-notation elastic tensor as a list of lists
    """
    if isinstance(tensor, ElasticTensorExpansion):
        return [e.voigt.tolist() for e in tensor]
    else:
        return tensor.voigt.tolist()
