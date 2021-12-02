"""
This module contains 3 builders for elastic properties.

1.  The ElasticityBuilder builds individual documents
    corresponding to aggregated tasks corresponding to a
    single input structure, e. g. all of the tasks in one
    workflow.  This is where elastic tensors are fitted.
2.  The ElasticAggregateBuilder aggregates elastic documents
    that all correspond to the same structure and also
    assigns a "state" based on the elastic document's validity.
3.  The ElasticCopyBuilder is a simple copy builder that
    transfers all of the aggregated tasks with "successful" states
    into a production collection.  It's not strictly necessary,
    but is currently in use in the production pipeline.
"""
import logging
import warnings
from copy import deepcopy
from datetime import datetime
from itertools import chain, groupby, product
from typing import Dict, Iterable, Iterator, List, Optional, Set, Union

import numpy as np
from atomate.vasp.workflows.base.elastic import get_default_strain_states
from maggma.core import Builder, Store
from monty.json import jsanitize
from monty.serialization import loadfn
from pydash.objects import get, set_
from pymatgen.analysis.elasticity.elastic import ElasticTensor, ElasticTensorExpansion
from pymatgen.analysis.elasticity.strain import Deformation, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher
from pymatgen.core import Structure
from pymatgen.core.tensors import TensorMapping
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

logger = logging.getLogger(__name__)


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

        # search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")

        # search index for elasticity
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
            logger.debug(f"Getting material_id {doc['material_id']}; index {n}")
            yield doc

    def process_item(self, item: Dict) -> Union[Dict, None]:
        """
        Process the tasks to get the

        Args:
            item: a dictionary with a key `task_ids`, which gives the ids of the
                tasks belonging to the same material

        Returns:
            an elasticity document
        """

        # Get elastic tasks
        task_ids = item["task_ids"]
        query = {
            "task_id": {"$in": task_ids},
            "task_label": {
                "$regex": "(elastic deformation)|(elastic structure optimization)"
            },
        }
        query.update(self.query)
        cursor = self.tasks.query(criteria=query)

        # Separate optimization and
        opt_tasks = []
        deform_tasks = []
        for task in cursor:
            if "optimization" in task["task_label"]:
                opt_tasks.append(task)
            else:
                deform_tasks.append(task)

        # TODO, for robustness, we probably should not assert, by log an error or
        #  warning ?
        # assert (
        #     len(opt_tasks) == 1
        # ), f"Expect 1 structure optimization task, got {len(opt_tasks)}"

        if len(opt_tasks) != 1:
            self.logger.warning(
                f"Expect 1 structure optimization task, but find {len(opt_tasks)} in "
                f"task_ids = {task_ids}. Skipping!"
            )
            return None

        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                elastic_doc = get_elastic_analysis(opt_tasks[0], deform_tasks)
                if elastic_doc:
                    elastic_doc["last_updated"] = datetime.utcnow()

            return elastic_doc

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new elasticity documents into the elasticity collection

        Args:
            items: list of elasticity docs
        """
        items = filter(bool, items)
        items = [jsanitize(doc, strict=True, allow_bson=True) for doc in items]

        self.logger.info(f"Updating {len(items)} elastic documents")

        # TODO what is key?
        self.elasticity.update(items, key="optimization_dir_name")


def get_elastic_analysis(opt_task, defo_tasks):
    """
    Performs the analysis of opt_tasks and defo_tasks necessary for
    an elastic analysis

    Args:
        opt_task: task doc corresponding to optimization
        defo_tasks: task_doc corresponding to deformations

    Returns:
        elastic document with fitted elastic tensor and analysis

    """
    elastic_doc = {"warnings": []}
    opt_struct = Structure.from_dict(opt_task["output"]["structure"])
    input_struct = Structure.from_dict(opt_task["input"]["structure"])

    # For now, discern order (i.e. TOEC) using parameters from optimization
    # TODO: figure this out more intelligently
    diff = get(opt_task, "input.incar.EDIFFG", 0)
    order = 3 if np.isclose(diff, -0.001) else 2

    explicit, derived = process_elastic_calcs(opt_task, defo_tasks)
    all_calcs = explicit + derived
    stresses = [c.get("cauchy_stress") for c in all_calcs]
    pk_stresses = [c.get("pk_stress") for c in all_calcs]
    strains = [c.get("strain") for c in all_calcs]
    elastic_doc["calculations"] = all_calcs
    vstrains = [s.zeroed(0.002).voigt for s in strains]
    if np.linalg.matrix_rank(vstrains) == 6:
        if order == 2:
            et_fit = legacy_fit(strains, stresses)
        elif order == 3:
            # Test for TOEC
            if len(strains) < 70:
                logger.info(
                    "insufficient valid strains for {} TOEC".format(
                        opt_task["formula_pretty"]
                    )
                )
                return None
            eq_stress = -0.1 * Stress(opt_task["output"]["stress"])
            # strains = [s.zeroed(0.0001) for s in strains]
            # et_expansion = pdb_function(ElasticTensorExpansion.from_diff_fit,
            #     strains, pk_stresses, eq_stress=eq_stress, tol=1e-5)
            et_exp_raw = ElasticTensorExpansion.from_diff_fit(
                strains, pk_stresses, eq_stress=eq_stress, tol=1e-6
            )
            et_exp = et_exp_raw.voigt_symmetrized.convert_to_ieee(opt_struct)
            et_exp = et_exp.round(1)
            et_fit = ElasticTensor(et_exp[0])
            # Update elastic doc with TOEC stuff
            tec = et_exp.thermal_expansion_coeff(opt_struct, 300)
            elastic_doc.update(
                {
                    "elastic_tensor_expansion": elastic_sanitize(et_exp),
                    "elastic_tensor_expansion_original": elastic_sanitize(et_exp_raw),
                    "thermal_expansion_tensor": tec,
                    "average_linear_thermal_expansion": np.trace(tec) / 3,
                }
            )
        et = et_fit.voigt_symmetrized.convert_to_ieee(opt_struct)
        vasp_input = opt_task["input"]
        if "structure" in vasp_input:
            vasp_input.pop("structure")
        completed_at = max([d["completed_at"] for d in defo_tasks])
        elastic_doc.update(
            {
                "optimization_task_id": opt_task["task_id"],
                "optimization_dir_name": opt_task["dir_name"],
                "cauchy_stresses": stresses,
                "strains": strains,
                "elastic_tensor": elastic_sanitize(et.zeroed(0.01).round(0)),
                # Convert compliance to 10^-12 Pa
                "compliance_tensor": elastic_sanitize(et.compliance_tensor * 1000),
                "elastic_tensor_original": elastic_sanitize(et_fit),
                "optimized_structure": opt_struct,
                "spacegroup": input_struct.get_space_group_info()[0],
                "input_structure": input_struct,
                "completed_at": completed_at,
                "optimization_input": vasp_input,
                "order": order,
                "formula_pretty": opt_struct.composition.reduced_formula,
            }
        )
        # Add magnetic type
        mag = CollinearMagneticStructureAnalyzer(opt_struct).ordering.value
        # TODO figure out how to get mag
        # elastic_doc["magnetic_type"] = mag_types[mag]
        try:
            prop_dict = et.get_structure_property_dict(opt_struct)
            prop_dict.pop("structure")
        except ValueError:
            logger.debug(
                "Negative K or G found, structure property " "dict not computed"
            )
            prop_dict = et.property_dict
        for k, v in prop_dict.items():
            if k in ["homogeneous_poisson", "universal_anisotropy"]:
                prop_dict[k] = np.round(v, 2)
            else:
                prop_dict[k] = np.round(v, 0)
        elastic_doc.update(prop_dict)
        # Update with state and warnings
        state, warnings = get_state_and_warnings(elastic_doc)
        elastic_doc.update({"state": state, "warnings": warnings})
        # TODO: add kpoints params?
        return elastic_doc
    else:
        logger.info(
            "insufficient valid strains for {}".format(opt_task["formula_pretty"])
        )
        return None


def get_distinct_rotations(structure, symprec=0.1, atol=1e-6):
    """
    Get distinct rotations from structure spacegroup operations

    Args:
        structure (Structure): structure object to analyze and
            get corresponding rotations for
        symprec (float): symprec for SpacegroupAnalyzer
        atol (float): absolute tolerance for relative indices
    """
    sga = SpacegroupAnalyzer(structure, symprec)
    symmops = sga.get_symmetry_operations(cartesian=True)
    rotations = [s.rotation_matrix for s in symmops]
    if len(rotations) == 1:
        return rotations
    unique_rotations = [np.array(rotations[0])]
    for rotation in rotations[1:]:
        if not any(
            [np.allclose(urot, rotation, atol=atol) for urot in unique_rotations]
        ):
            unique_rotations.append(rotation)
    return unique_rotations


def get_strain_state(strain):
    """
    Helper function to get strain state

    Args:
        strain (Strain): Input strain

    Returns:
        6-tuple corresponding to strain state
    """
    vstrain = strain.zeroed(5e-5).voigt
    vstrain[vstrain == 0] = np.inf
    min_nonzero = np.argmin(np.abs(vstrain))
    vstrain[vstrain == np.inf] = 0
    strain_state = vstrain / vstrain[min_nonzero]
    return strain_state.round(4)


allowed_strain_states = get_default_strain_states(3)
# TODO: make it so opt_doc not necessary?
def process_elastic_calcs(opt_doc, defo_docs, add_derived=True, tol=0.002):
    """
    Generates the list of calcs from deformation docs, along with 'derived
    stresses', i. e. stresses derived from symmop transformations of existing
    calcs from transformed strains resulting in an independent strain
    not in the input list

    Args:
        opt_doc (dict): document for optimization task
        defo_docs ([dict]) list of documents for deformation tasks
        add_derived (bool): flag for whether or not to add derived
            stress-strain pairs based on symmetry
        tol (float): tolerance for assigning equivalent stresses/strains

    Returns ([dict], [dict]):
        Two lists of summary documents corresponding to strains
        and stresses, one explicit and one derived
    """
    structure = Structure.from_dict(opt_doc["output"]["structure"])
    input_structure = Structure.from_dict(opt_doc["input"]["structure"])

    # Process explicit calcs, store in dict keyed by strain
    explicit_calcs = TensorMapping()
    for doc in defo_docs:
        calc = {
            "type": "explicit",
            "input": doc["input"],
            "output": doc["output"],
            "task_id": doc["task_id"],
            "completed_at": doc["completed_at"],
        }
        deformed_structure = Structure.from_dict(doc["output"]["structure"])
        defo = Deformation(calculate_deformation(structure, deformed_structure))
        # Warning if deformation is not equivalent to stored deformation
        stored_defo = doc["transmuter"]["transformation_params"][0]["deformation"]
        if not np.allclose(defo, stored_defo, atol=1e-5):
            wmsg = "Inequivalent stored and calc. deformations."
            logger.debug(wmsg)
            calc["warnings"] = wmsg
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
                for s, strain_state in product(stencil, strain_states)
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


def group_by_material_id(
    materials_dict,
    docs,
    structure_key="structure",
    tol=1e-6,
    loosen=True,
    structure_matcher=None,
):
    """
    Groups a collection of documents by material id
    as found in a materials collection

    Args:
        materials_dict (dict): dictionary of structures keyed by task_id
        docs ([dict]): list of documents
        tol (float): tolerance for lattice grouping
        loosen (bool): whether or not to loosen criteria if no matches are
            found
        structure_key (string): mongo-style key of documents where structures
            are contained (e. g. input.structure or output.structure)
        structure_matcher (StructureMatcher): structure
            matcher for finding equivalent structures

    Returns:
        documents grouped by task_id from the materials
        collection
    """
    # Structify all input structures
    materials_dict = {
        mp_id: Structure.from_dict(struct) for mp_id, struct in materials_dict.items()
    }
    # Get magnetic phases
    mags = {}
    # TODO: refactor this with data from materials collection?
    for mp_id, structure in materials_dict.items():
        mag = CollinearMagneticStructureAnalyzer(structure).ordering.value
        # TODO figure out how to get mag_types
        # mags[mp_id] = mag_types[mag]
    docs_by_mp_id = {}
    for doc in docs:
        sm = structure_matcher or StructureMatcher(comparator=ElementComparator())
        structure = Structure.from_dict(get(doc, structure_key))
        input_sg_symbol = SpacegroupAnalyzer(structure, 0.1).get_space_group_symbol()
        # Iterate over all candidates until match is found
        matches = {
            c_id: candidate
            for c_id, candidate in materials_dict.items()
            if sm.fit(candidate, structure)
        }
        niter = 0
        if not matches:
            # First try with conventional structure then loosen match criteria
            convs = {
                c_id: SpacegroupAnalyzer(
                    candidate, 0.1
                ).get_conventional_standard_structure()
                for c_id, candidate in materials_dict.items()
            }
            matches = {
                c_id: candidate
                for c_id, candidate in materials_dict.items()
                if sm.fit(convs[c_id], structure)
            }
            while len(matches) < 1 and niter < 4 and loosen:
                logger.debug("Loosening sm criteria")
                sm = StructureMatcher(
                    sm.ltol * 2, sm.stol * 2, sm.angle_tol * 2, primitive_cell=False
                )
                matches = {
                    c_id: candidate
                    for c_id, candidate in materials_dict.items()
                    if sm.fit(convs[c_id], structure)
                }
                niter += 1
        if matches:
            # Get best match by spacegroup, then mag phase, then closest density
            mag = doc["magnetic_type"]

            def sort_criteria(m_id):
                dens_diff = abs(matches[m_id].density - structure.density)
                sg = matches[m_id].get_space_group_info(0.1)[0]
                mag_id = mags[m_id]
                # prefer explicit matches, allow non-mag materials match with FM tensors
                if mag_id == mag:
                    mag_match = 0
                elif mag_id == "Non-magnetic" and mag == "FM":
                    mag_match = 1
                else:
                    mag_match = 2
                return (sg != input_sg_symbol, mag_match, dens_diff)

            sorted_ids = sorted(list(matches.keys()), key=sort_criteria)
            mp_id = sorted_ids[0]
            if mp_id in docs_by_mp_id:
                docs_by_mp_id[mp_id].append(doc)
            else:
                docs_by_mp_id[mp_id] = [doc]
        else:
            logger.debug(
                "No material match found for formula {}".format(
                    structure.composition.reduced_formula
                )
            )
    return docs_by_mp_id


def group_deformations_by_optimization_task(docs, tol=1e-6):
    """
    Groups a set of deformation tasks by equivalent lattices
    to an optimization task.  Basically the same as
    group_by_parent_lattice, except does an additional
    step of finding the optimization and using that
    as the grouping parameter.  Also filters document
    sets that don't include an optimization and deformations.

    Args:
        docs ([{}]): list of documents
        tol (float): tolerance for lattice equivalence
    """
    # TODO: this could prolly be refactored to be more generally useful
    tasks_by_lattice = group_by_parent_lattice(docs, tol)
    tasks_by_opt_task = []
    for _, task_set in tasks_by_lattice:
        opt_struct_tasks = [
            task for task in task_set if "structure optimization" in task["task_label"]
        ]
        deformation_tasks = [
            task for task in task_set if "elastic deformation" in task["task_label"]
        ]
        opt_struct_tasks.reverse()
        if opt_struct_tasks and deformation_tasks:
            tasks_by_opt_task.append((opt_struct_tasks[-1], deformation_tasks))
        else:
            logger.debug("No structure opt matching tasks")
    return tasks_by_opt_task


def group_by_parent_lattice(docs, tol=1e-5):
    """
    Groups a set of documents by parent lattice equivalence

    Args:
        docs ([{}]): list of documents e. g. dictionaries or cursor
        tol (float): tolerance for equivalent lattice finding using,
            np.allclose, default 1e-5
    """
    docs_by_lattice = []
    for doc in docs:
        sim_lattice = get(doc, "output.structure.lattice.matrix")
        if "deformation" in doc["task_label"]:
            # Note that this assumes only one transformation, deformstructuretransformation
            defo = doc["transmuter"]["transformation_params"][0]["deformation"]
            parent_lattice = np.dot(sim_lattice, np.transpose(np.linalg.inv(defo)))
        else:
            parent_lattice = np.array(sim_lattice)
        match = False
        for unique_lattice, lattice_docs in docs_by_lattice:
            match = np.allclose(unique_lattice, parent_lattice, atol=tol)
            if match:
                lattice_docs.append(doc)
                break
        if not match:
            docs_by_lattice.append([parent_lattice, [doc]])
    return docs_by_lattice


def legacy_fit(strains, stresses):
    """
    Legacy fitting method for mpworks documents, intended to be temporary

    Args:
        strains: strains
        stresses: stresses

    Returns:
        elastic tensor fit using the legacy functionality

    """
    strains = [s.zeroed(0.002) for s in strains]
    return ElasticTensor.from_independent_strains(strains, stresses)


def calculate_deformation(undeformed_structure, deformed_structure):
    """

    Args:
        undeformed_structure (Structure): undeformed structure
        deformed_structure (Structure): deformed structure

    Returns:
        deformation matrix
    """
    ulatt = undeformed_structure.lattice.matrix
    dlatt = deformed_structure.lattice.matrix
    return np.transpose(np.dot(np.linalg.inv(ulatt), dlatt))


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


def generate_formula_dict(materials_store, query=None):
    """
    Function that generates a nested dictionary of structures
    keyed first by formula and then by task_id using
    mongo aggregation pipelines

    Args:
        materials_store (Store): store of materials

    Returns:
        Nested dictionary keyed by formula-mp_id with structure values.

    """
    props = ["formula_pretty", "structure", "task_id", "magnetic_type"]
    results = materials_store.groupby(
        "formula_pretty", properties=props, criteria=query
    )
    formula_dict = {}
    for id_doc, docs in results:
        formula = id_doc["formula_pretty"]
        task_ids = [d["task_id"] for d in docs]
        structures = [d["structure"] for d in docs]
        formula_dict[formula] = dict(zip(task_ids, structures))
    return formula_dict


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
