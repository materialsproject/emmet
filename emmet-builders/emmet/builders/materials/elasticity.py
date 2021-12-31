import itertools
import logging
import warnings
from datetime import datetime
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np
from atomate.vasp.workflows.base.elastic import get_default_strain_states
from maggma.core import Builder, Store
from monty.json import jsanitize
from pydash.objects import get, set_
from pymatgen.analysis.elasticity.elastic import ElasticTensor, ElasticTensorExpansion
from pymatgen.analysis.elasticity.strain import Deformation, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen.core import Structure
from pymatgen.core.tensors import TensorMapping
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.elasticity import (
    ComplianceTensorDoc,
    ElasticityDoc,
    ElasticTensorDoc,
    FittingData,
)

DEFORM_TASK_LABEL = "elastic deformation"
OPTIM_TASK_LABEL = "elastic structure optimization"

STRAIN_COMP_TOL = 0.002  # tolerance for comparing strains
DEFORM_COMP_TOL = 1e-5  # tolerance for comparing deformations
LATTICE_COMP_TOL = 1e-5  # tolerance for comparing lattice
SYMPREC = 0.1


class ElasticityBuilder(Builder):
    def __init__(
        self,
        tasks: Store,
        materials: Store,
        elasticity: Store,
        query: Optional[Dict] = None,
        incremental: bool = None,  # TODO add back later
        **kwargs,
    ):
        """
        Creates a elastic collection for materials

        Args:
            tasks (Store): Store of tasks
            materials (Store): Store of materials properties
            elasticity (Store): Store of elastic properties
            query (dict): dictionary to limit tasks to be analyzed
            incremental (bool): whether or not to use a lu_filter based on the current
                datetime, is set to False if target is empty, but True if not
        """

        self.tasks = tasks
        self.materials = materials
        self.elasticity = elasticity
        self.query = query if query is not None else {}

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

    def get_items(self) -> Iterable[Dict]:
        """
        Gets all items to process into materials documents

        Returns:
            generator of material doc with material_id and task_ids keys
        """

        self.logger.info("Elastic Builder Started")

        self.ensure_index()

        cursor = self.materials.query(
            criteria=self.query, properties=["material_id", "task_ids"]
        )

        for n, doc in enumerate(cursor):
            self.logger.debug(f"Getting material_id {doc['material_id']}; index {n}")
            yield doc

    def process_item(self, item: Dict) -> List[Dict]:
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
            item: a dictionary with key `task_ids`, which gives the ids of the tasks
                that belong to the same material

        Returns:
            an elasticity document, represented as a dict
        """

        # Get elastic tasks
        task_ids = [int(i) for i in item["task_ids"]]
        query = {
            "task_id": {"$in": task_ids},
            "task_label": {"$regex": f"({DEFORM_TASK_LABEL})|({OPTIM_TASK_LABEL})"},
        }
        query.update(self.query)

        props = [
            "output",
            "input",
            "completed_at",
            "transmuter",
            "task_id",
            "task_label",
            "formula_pretty",
            "dir_name",
        ]

        cursor = self.tasks.query(criteria=query, properties=props)

        grouped = group_deform_tasks_by_opt_task(cursor)

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
                doc = doc.dict()
                elastic_docs.append(doc)

            return elastic_docs

    def update_targets(self, items: List[List[Dict]]):
        """
        Insert the new elasticity docs into the elasticity collection.

        Args:
            items: elastic docs
        """
        items = itertools.chain.from_iterable(items)
        items = [jsanitize(doc, strict=True, allow_bson=True) for doc in items]

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
    # TODO what is the difference of `incar` and `orig_incar` for a task? which to use?
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


def analyze_elastic_data(opt_task: Dict, deform_tasks: List[Dict], logger) -> Dict:
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
    strains = [d["strain"] for d in full_data]
    v_strains = [s.zeroed(STRAIN_COMP_TOL).voigt for s in strains]
    if np.linalg.matrix_rank(v_strains) != 6:
        task_ids = [opt_task["task_id"]] + [t["task_id"] for t in deform_tasks]
        logger.info(f"Insufficient valid strains for tasks {task_ids}. Skipped.")
        return None

    pk_stresses = [d["second_pk_stress"] for d in full_data]
    fitting_method = "finite_difference"

    elastic_tensor = fit_elastic_tensor(
        strains, pk_stresses, eq_stress=eq_stress, fitting_method="fitting_method"
    )

    # generate derived property
    derived_props = get_derived_properties(structure, elastic_tensor)

    #
    # prepare data for ElasticityDoc
    #
    fitting_data = FittingData(
        strains=[d["strain"].tolist() for d in primary_data],
        cauchy_stersses=[d["cauchy_stress"].tolist() for d in primary_data],
        second_pk_stersses=[d["second_pk_stress"].tolist() for d in primary_data],
        deformations=[d["deformation"].tolist() for d in primary_data],
        deformation_tasks=[d["task_id"] for d in primary_data],
        deformation_dir_name=[d["dir_name"] for d in primary_data],
        equilibrium_cauchy_stress=eq_stress.tolist(),
        optimization_task=opt_task["task_id"],
        optimization_dir_name=opt_task["dir_name"],
    )

    # elastic tensor, ieee format is symmetrized and rounded
    ieee_et = elastic_tensor.voigt_symmetrized.convert_to_ieee(structure)
    et_doc = ElasticTensorDoc(
        raw=elastic_sanitize(elastic_tensor),
        ieee_format=elastic_sanitize(ieee_et.zeroed(0.01).round(0)),
    )

    ct_doc = ComplianceTensorDoc(
        # *1000 to convert units to TPa^-1, i.e. 10^-12 Pa
        raw=elastic_sanitize(elastic_tensor.compliance_tensor * 1000),
        ieee_format=elastic_sanitize(ieee_et.compliance_tensor * 1000),
    )

    # TODO check warnings
    # # update with state and warnings
    # state, warnings = get_state_and_warnings(elastic_doc)
    # elastic_doc.update({"state": state, "warnings": warnings})

    # TODO, should material_id be something else
    elastic_doc = ElasticityDoc.from_structure_and_elastic_tensor(
        structure=structure,
        material_id=opt_task["task_id"],
        order=2,
        elastic_tensor=et_doc,
        compliance_tensor=ct_doc,
        derived_property=derived_props,
        fitting_data=fitting_data,
        fitting_method=fitting_method,
    )

    return elastic_doc


#
# def analyze_elastic_data(opt_task: Dict, deform_tasks: List[Dict], logger) -> Dict:
#     """
#     Analyze optimization task and deformation tasks to fit elastic tensor.
#
#     This currently only deal with second order elastic tensor.
#
#     Args:
#         opt_task: task doc corresponding to optimization
#         deform_tasks: task docs corresponding to deformations
#         logger:
#
#     Returns:
#         elastic document with fitted elastic tensor and analysis
#     """
#
#     opt_struct = Structure.from_dict(opt_task["output"]["structure"])
#     input_struct = Structure.from_dict(opt_task["input"]["structure"])
#
#     explicit, derived = process_elastic_calcs(opt_task, deform_tasks, logger)
#     all_calcs = explicit + derived
#
#     elastic_doc = {"calculations": all_calcs}
#
#     stresses = [c.get("cauchy_stress") for c in all_calcs]
#     pk_stresses = [c.get("pk_stress") for c in all_calcs]
#     strains = [c.get("strain") for c in all_calcs]
#
#     eq_stress = -0.1 * Stress(opt_task["output"]["stress"])
#
#     vstrains = [s.zeroed(0.002).voigt for s in strains]
#     if np.linalg.matrix_rank(vstrains) != 6:
#         logger.info(
#             f"Insufficient valid strains for {opt_task['formula_pretty']}. Skipped."
#         )
#         return None
#
#     et_fit = fit_elastic_tensor(strains, pk_stresses, eq_stress=eq_stress)
#     et = et_fit.voigt_symmetrized.convert_to_ieee(opt_struct)
#
#     vasp_input = opt_task["input"]
#     if "structure" in vasp_input:
#         vasp_input.pop("structure")
#     # TODO convert to datetime and then compare
#     completed_at = max([d["completed_at"] for d in deform_tasks])
#
#     elastic_doc.update(
#         {
#             "optimization_task_id": opt_task["task_id"],
#             "optimization_dir_name": opt_task["dir_name"],
#             "cauchy_stresses": stresses,
#             "strains": strains,
#             "elastic_tensor": elastic_sanitize(et.zeroed(0.01).round(0)),
#             # Convert compliance to 10^-12 Pa
#             "compliance_tensor": elastic_sanitize(et.compliance_tensor * 1000),
#             "elastic_tensor_original": elastic_sanitize(et_fit),
#             "optimized_structure": opt_struct,
#             "spacegroup": input_struct.get_space_group_info()[0],
#             "input_structure": input_struct,
#             "completed_at": completed_at,
#             "optimization_input": vasp_input,
#             "order": 2,
#             "formula_pretty": opt_struct.composition.reduced_formula,
#         }
#     )
#
#     # Add magnetic type
#     mag = CollinearMagneticStructureAnalyzer(opt_struct).ordering.value
#     # TODO figure out how to get mag
#
#     # elastic_doc["magnetic_type"] = mag_types[mag]
#     try:
#         prop_dict = et.get_structure_property_dict(opt_struct)
#         prop_dict.pop("structure")
#     except ValueError:
#         logger.debug(
#             "Negative K or G found, structure property " "dict not " "computed"
#         )
#         prop_dict = et.property_dict
#
#     for k, v in prop_dict.items():
#         if k in ["homogeneous_poisson", "universal_anisotropy"]:
#             prop_dict[k] = np.round(v, 2)
#         else:
#             prop_dict[k] = np.round(v, 0)
#     elastic_doc.update(prop_dict)
#
#     # Update with state and warnings
#     state, warnings = get_state_and_warnings(elastic_doc)
#     elastic_doc.update({"state": state, "warnings": warnings})
#
#     # TODO: add kpoints params?
#
#     return elastic_doc


def generate_primary_fitting_data(deform_tasks: List[Dict]) -> List[Dict]:
    """
    Get the fitting data from primary deformation tasks (i.e. the explicitly computed
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
    primary_calcs_by_id = {calc["task_id"] for calc in primary_data}

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


def process_elastic_calcs(opt_tasks, deform_tasks, logger, add_derived=True, tol=0.002):
    """
    Generates the list of calcs from deformation docs, along with 'derived
    stresses', i.e. stresses derived from symmop transformations of existing
    calcs from transformed strains resulting in an independent strain
    not in the input list

    Args:
        opt_tasks (dict): document for optimization task
        deform_tasks ([dict]) list of documents for deformation tasks
        add_derived (bool): flag for whether or not to add derived
            stress-strain pairs based on symmetry
        tol (float): tolerance for assigning equivalent stresses/strains

    Returns ([dict], [dict]):
        Two lists of summary documents corresponding to strains
        and stresses, one explicit and one derived
    """
    structure = Structure.from_dict(opt_tasks["output"]["structure"])

    # Process explicit calcs, store in dict keyed by strain
    explicit_calcs = TensorMapping()
    for doc in deform_tasks:
        calc = {
            "type": "explicit",
            "input": doc["input"],
            "output": doc["output"],
            "task_id": doc["task_id"],
            "completed_at": doc["completed_at"],
        }
        deformed_structure = Structure.from_dict(doc["output"]["structure"])
        defo = Deformation(get_deformation(structure, deformed_structure))
        # Warning if deformation is not equivalent to stored deformation
        stored_defo = doc["transmuter"]["transformation_params"][0]["deformation"]
        if not np.allclose(defo, stored_defo, atol=1e-5):
            msg = "Inequivalent stored and calc. deformations."
            logger.debug(msg)
            calc["warnings"] = msg
        cauchy_stress = -0.1 * Stress(doc["output"]["stress"])
        pk_stress = cauchy_stress.piola_kirchoff_2(defo)
        strain = defo.green_lagrange_strain
        calc.update(
            {
                "deformation": defo,
                "cauchy_stress": cauchy_stress,
                "strain": strain,
                "pk_stress": pk_stress,
            }
        )
        if strain in explicit_calcs:
            existing_value = explicit_calcs[strain]
            if doc["completed_at"] > existing_value["completed_at"]:
                explicit_calcs[strain] = calc
        else:
            explicit_calcs[strain] = calc

    if not add_derived:
        return explicit_calcs.values(), None

    # Determine all of the implicit calculations to include
    sga = SpacegroupAnalyzer(structure, symprec=0.1)
    symmops = sga.get_symmetry_operations(cartesian=True)
    derived_calcs_by_strain = TensorMapping(tol=0.002)
    for strain, calc in explicit_calcs.items():
        # Generate all transformed strains
        task_id = calc["task_id"]
        tstrains = [(symmop, strain.transform(symmop)) for symmop in symmops]
        # Filter strains by those which are independent and new
        # For second order
        if len(explicit_calcs) < 30:
            tstrains = [
                (symmop, tstrain)
                for symmop, tstrain in tstrains
                if tstrain.get_deformation_matrix().is_independent(tol)
                and not tstrain in explicit_calcs
            ]
        # For third order
        else:
            strain_states = get_default_strain_states(3)
            # Default stencil in atomate, this maybe shouldn't be hard-coded
            stencil = np.linspace(-0.075, 0.075, 7)
            valid_strains = [
                Strain.from_voigt(s * np.array(strain_state))
                for s, strain_state in itertools.product(stencil, strain_states)
            ]
            valid_strains = [v for v in valid_strains if not np.allclose(v, 0)]
            valid_strains = TensorMapping(valid_strains, [True] * len(valid_strains))
            tstrains = [
                (symmop, tstrain)
                for symmop, tstrain in tstrains
                if tstrain in valid_strains and not tstrain in explicit_calcs
            ]
        # Add surviving tensors to derived_strains dict
        for symmop, tstrain in tstrains:
            # curr_set = derived_calcs_by_strain[tstrain]
            if tstrain in derived_calcs_by_strain:
                curr_set = derived_calcs_by_strain[tstrain]
                curr_task_ids = [c[1] for c in curr_set]
                if task_id not in curr_task_ids:
                    curr_set.append((symmop, calc["task_id"]))
            else:
                derived_calcs_by_strain[tstrain] = [(symmop, calc["task_id"])]

    # Process derived calcs
    explicit_calcs_by_id = {d["task_id"]: d for d in explicit_calcs.values()}
    derived_calcs = []
    for strain, calc_set in derived_calcs_by_strain.items():
        symmops, task_ids = zip(*calc_set)
        task_strains = [
            Strain(explicit_calcs_by_id[task_id]["strain"]) for task_id in task_ids
        ]
        task_stresses = [
            explicit_calcs_by_id[task_id]["cauchy_stress"] for task_id in task_ids
        ]
        derived_strains = [
            tstrain.transform(symmop) for tstrain, symmop in zip(task_strains, symmops)
        ]
        for derived_strain in derived_strains:
            if not np.allclose(derived_strain, strain, atol=2e-3):
                logger.info("Issue with derived strains")
                raise ValueError("Issue with derived strains")
        derived_stresses = [
            tstress.transform(sop) for sop, tstress in zip(symmops, task_stresses)
        ]
        input_docs = [
            {
                "task_id": task_id,
                "strain": task_strain,
                "cauchy_stress": task_stress,
                "symmop": symmop,
            }
            for task_id, task_strain, task_stress, symmop in zip(
                task_ids, task_strains, task_stresses, symmops
            )
        ]
        calc = {
            "strain": strain,
            "cauchy_stress": Stress(np.average(derived_stresses, axis=0)),
            "deformation": strain.get_deformation_matrix(),
            "input_tasks": input_docs,
            "type": "derived",
        }
        calc["pk_stress"] = calc["cauchy_stress"].piola_kirchoff_2(calc["deformation"])
        derived_calcs.append(calc)

    return list(explicit_calcs.values()), derived_calcs


#
# def group_by_material_id(
#     materials_dict,
#     docs,
#     structure_key="structure",
#     tol=1e-6,
#     loosen=True,
#     structure_matcher=None,
# ):
#     """
#     Groups a collection of documents by material id
#     as found in a materials collection
#
#     Args:
#         materials_dict (dict): dictionary of structures keyed by task_id
#         docs ([dict]): list of documents
#         tol (float): tolerance for lattice grouping
#         loosen (bool): whether or not to loosen criteria if no matches are
#             found
#         structure_key (string): mongo-style key of documents where structures
#             are contained (e. g. input.structure or output.structure)
#         structure_matcher (StructureMatcher): structure
#             matcher for finding equivalent structures
#
#     Returns:
#         documents grouped by task_id from the materials
#         collection
#     """
#     # Structify all input structures
#     materials_dict = {
#         mp_id: Structure.from_dict(struct) for mp_id, struct in materials_dict.items()
#     }
#     # Get magnetic phases
#     mags = {}
#     # TODO: refactor this with data from materials collection?
#     for mp_id, structure in materials_dict.items():
#         mag = CollinearMagneticStructureAnalyzer(structure).ordering.value
#         # TODO figure out how to get mag_types
#         # mags[mp_id] = mag_types[mag]
#     docs_by_mp_id = {}
#     for doc in docs:
#         sm = structure_matcher or StructureMatcher(comparator=ElementComparator())
#         structure = Structure.from_dict(get(doc, structure_key))
#         input_sg_symbol = SpacegroupAnalyzer(structure, 0.1).get_space_group_symbol()
#         # Iterate over all candidates until match is found
#         matches = {
#             c_id: candidate
#             for c_id, candidate in materials_dict.items()
#             if sm.fit(candidate, structure)
#         }
#         niter = 0
#         if not matches:
#             # First try with conventional structure then loosen match criteria
#             convs = {
#                 c_id: SpacegroupAnalyzer(
#                     candidate, 0.1
#                 ).get_conventional_standard_structure()
#                 for c_id, candidate in materials_dict.items()
#             }
#             matches = {
#                 c_id: candidate
#                 for c_id, candidate in materials_dict.items()
#                 if sm.fit(convs[c_id], structure)
#             }
#             while len(matches) < 1 and niter < 4 and loosen:
#                 logger.debug("Loosening sm criteria")
#                 sm = StructureMatcher(
#                     sm.ltol * 2, sm.stol * 2, sm.angle_tol * 2, primitive_cell=False
#                 )
#                 matches = {
#                     c_id: candidate
#                     for c_id, candidate in materials_dict.items()
#                     if sm.fit(convs[c_id], structure)
#                 }
#                 niter += 1
#         if matches:
#             # Get best match by spacegroup, then mag phase, then closest density
#             mag = doc["magnetic_type"]
#
#             def sort_criteria(m_id):
#                 dens_diff = abs(matches[m_id].density - structure.density)
#                 sg = matches[m_id].get_space_group_info(0.1)[0]
#                 mag_id = mags[m_id]
#                 # prefer explicit matches, allow non-mag materials match with FM tensors
#                 if mag_id == mag:
#                     mag_match = 0
#                 elif mag_id == "Non-magnetic" and mag == "FM":
#                     mag_match = 1
#                 else:
#                     mag_match = 2
#                 return (sg != input_sg_symbol, mag_match, dens_diff)
#
#             sorted_ids = sorted(list(matches.keys()), key=sort_criteria)
#             mp_id = sorted_ids[0]
#             if mp_id in docs_by_mp_id:
#                 docs_by_mp_id[mp_id].append(doc)
#             else:
#                 docs_by_mp_id[mp_id] = [doc]
#         else:
#             logger.debug(
#                 "No material match found for formula {}".format(
#                     structure.composition.reduced_formula
#                 )
#             )
#     return docs_by_mp_id


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


def get_deformation(structure, deformed_structure):
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


def get_derived_properties(structure: Structure, tensor: ElasticTensor, logger):
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

    return prop_dict


def get_state_and_warnings(elastic_doc):
    """
    Generates all warnings that apply to a fitted elastic tensor

    Args:
        elastic_tensor (ElasticTensor): elastic tensor for which
            to determine warnings
        structure (Structure): structure for which elastic tensor
            is determined

    Returns:
        list of warnings

    """
    structure = elastic_doc["optimized_structure"]
    warnings = []
    if any([s.is_rare_earth_metal for s in structure.species]):
        warnings.append("Structure contains a rare earth element")
    vet = np.array(elastic_doc["elastic_tensor"])
    eigs, eigvecs = np.linalg.eig(vet)
    if np.any(eigs < 0.0):
        warnings.append("Elastic tensor has a negative eigenvalue")
    c11, c12, c13 = vet[0, 0:3]
    c23 = vet[1, 2]

    # TODO: these should be revisited at some point, are they complete?
    #       I think they might only apply to cubic systems
    if abs((c11 - c12) / c11) < 0.05 or c11 < c12:
        warnings.append("c11 and c12 are within 5% or c12 is greater than c11")
    if abs((c11 - c13) / c11) < 0.05 or c11 < c13:
        warnings.append("c11 and c13 are within 5% or c13 is greater than c11")
    if abs((c11 - c23) / c11) < 0.05 or c11 < c23:
        warnings.append("c11 and c23 are within 5% or c23 is greater than c11")

    moduli = ["k_voigt", "k_reuss", "k_vrh", "g_voigt", "g_reuss", "g_vrh"]
    moduli_array = np.array([get(elastic_doc, m) for m in moduli])
    if np.any(moduli_array < 2):
        warnings.append("One or more K, G below 2 GPa")

    if np.any(moduli_array > 1000):
        warnings.append("One or more K, G above 1000 GPa")

    if elastic_doc["order"] == 3:
        if elastic_doc.get("average_linear_thermal_expansion", 0) < -0.1:
            warnings.append("Negative thermal expansion")
        if len(elastic_doc["strains"]) < 80:
            warnings.append("Fewer than 80 strains, TOEC may be deficient")

    failure_states = [moduli_array[2] < 0]
    if any(failure_states):
        state = "failed"
    elif warnings:
        state = "warning"
    else:
        state = "successful"
        warnings = None

    return state, warnings


def elastic_sanitize(tensor):
    """
    Simple method to sanitize elastic tensor objects

    Args:
        tensor (ElasticTensor or ElasticTensorExpansion):
            elastic tensor to be sanitized

    Returns:
        voigt-notation elastic tensor as a list of lists
    """
    if isinstance(tensor, ElasticTensorExpansion):
        return [e.voigt.tolist() for e in tensor]
    else:
        return tensor.voigt.tolist()
