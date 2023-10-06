"""
Builder to generate elasticity docs.

The build proceeds in the below steps:
1. Use materials builder to group tasks according the formula, space group, and
   structure matching.
2. Filter opt and deform tasks by calc type.
3. Filter opt and deform tasks to match prescribed INCAR params.
4. Group opt tasks by optimized lattice, and, for each group, select the latest task
   (the one with the newest completing time). This result in a {lat, opt_task} dict.
5. Group deform tasks by parent lattice (i.e. lattice before a deformation gradient is
   applied). For each lattice group, then group the tasks by deformation gradient,
   and select the latest task for each deformation gradient. This result in a {lat,
   [deform_task]} dict, where [deform_task] are tasks with unique deformation gradients.
6. Associate opt and deform tasks by matching parent lattice. Then select the one with
   the most deformation tasks as the final data for fitting the elastic tensor.
7. Fit the elastic tensor.
"""

from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import numpy as np
from maggma.core import Builder, Store
from pydash.objects import get
from pymatgen.analysis.elasticity.strain import Deformation
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.core import Structure
from pymatgen.core.tensors import TensorMapping

from emmet.core.elasticity import ElasticityDoc
from emmet.core.mpid import MPID
from emmet.core.utils import jsanitize
from emmet.core.vasp.calc_types import CalcType


class ElasticityBuilder(Builder):
    def __init__(
        self,
        tasks: Store,
        materials: Store,
        elasticity: Store,
        query: Optional[Dict] = None,
        fitting_method: str = "finite_difference",
        **kwargs,
    ):
        """
        Creates an elastic collection for materials.

        Args:
            tasks: Store of tasks
            materials: Store of materials
            elasticity: Store of elasticity
            query: Mongo-like query to limit the tasks to be analyzed
            fitting_method: method to fit the elastic tensor: {`finite_difference`,
                `pseudoinverse`, `independent`}
        """

        self.tasks = tasks
        self.materials = materials
        self.elasticity = elasticity
        self.query = query if query is not None else {}
        self.fitting_method = fitting_method
        self.kwargs = kwargs

        super().__init__(sources=[tasks, materials], targets=[elasticity], **kwargs)

    def ensure_index(self):
        self.tasks.ensure_index("nsites")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index("last_updated")

        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")

        self.elasticity.ensure_index("material_id")
        self.elasticity.ensure_index("last_updated")

    def get_items(
        self,
    ) -> Generator[Tuple[str, Dict[str, str], List[Dict]], None, None]:
        """
        Gets all items to process into elasticity docs.

        Returns:
            material_id: material id for the tasks
            calc_types: calculation types of the tasks
            tasks: task docs belong to the same material
        """

        self.logger.info("Elastic Builder Started")

        self.ensure_index()

        cursor = self.materials.query(
            criteria=self.query, properties=["material_id", "calc_types", "task_ids"]
        )

        # query for tasks
        query = self.query.copy()

        for i, doc in enumerate(cursor):
            material_id = doc["material_id"]
            calc_types = {str(k): v for k, v in doc["calc_types"].items()}

            self.logger.debug(f"Querying tasks for material {material_id} (index {i}).")

            # update query with task_ids
            try:
                ids_list = [int(i) for i in doc["task_ids"]]
            except ValueError:
                ids_list = [i for i in doc["task_ids"]]

            query["task_id"] = {"$in": ids_list}

            projections = [
                "output",
                "orig_inputs",
                "completed_at",
                "transmuter",
                "task_id",
                "dir_name",
            ]

            task_cursor = self.tasks.query(criteria=query, properties=projections)
            tasks = list(task_cursor)

            yield material_id, calc_types, tasks

    def process_item(
        self, item: Tuple[MPID, Dict[str, str], List[Dict]]
    ) -> Union[Dict, None]:
        """
        Process all tasks belong to the same material into an elasticity doc.

        Args:
            item:
                material_id: material id for the tasks
                calc_types: {task_id: task_type} calculation types of the tasks
                tasks: task docs belong to the same material

        Returns:
            Elasticity doc obtained from the list of tasks. `None` if failed to
            obtain the elasticity doc from the tasks.
        """

        material_id, calc_types, tasks = item

        if len(tasks) != len(calc_types):
            self.logger.error(
                f"Number of tasks ({len(tasks)}) is not equal to number of calculation "
                f"types ({len(calc_types)}) for material with material id "
                f"{material_id}. Cannot proceed."
            )
            return None

        # filter by calc type
        opt_tasks = filter_opt_tasks(tasks, calc_types)
        deform_tasks = filter_deform_tasks(tasks, calc_types)
        if not opt_tasks or not deform_tasks:
            return None

        # filter by incar
        opt_tasks = filter_by_incar_settings(opt_tasks)
        deform_tasks = filter_by_incar_settings(deform_tasks)
        if not opt_tasks or not deform_tasks:
            return None

        # select one task for each set of optimization tasks with the same lattice
        opt_grouped_tmp = group_by_parent_lattice(opt_tasks, mode="opt")
        opt_grouped = [
            (lattice, filter_opt_tasks_by_time(tasks, self.logger))
            for lattice, tasks in opt_grouped_tmp
        ]

        # for deformed tasks with the same lattice, select one if there are multiple
        # tasks with the same deformation
        deform_grouped = group_by_parent_lattice(deform_tasks, mode="deform")
        deform_grouped = [
            (lattice, filter_deform_tasks_by_time(tasks, logger=self.logger))
            for lattice, tasks in deform_grouped
        ]

        # select opt and deform tasks for fitting
        final_opt, final_deform = select_final_opt_deform_tasks(
            opt_grouped, deform_grouped, self.logger
        )
        if final_opt is None or final_deform is None:
            return None

        # convert to elasticity doc
        deforms = []
        stresses = []
        deform_task_ids = []
        deform_dir_names = []
        for doc in final_deform:
            deforms.append(
                Deformation(
                    doc["transmuter"]["transformation_params"][0]["deformation"]
                )
            )
            # 0.1 to convert to GPa from kBar, and the minus sign to flip the stress
            # direction from compressive as positive (in vasp) to tensile as positive
            stresses.append(-0.1 * Stress(doc["output"]["stress"]))
            deform_task_ids.append(doc["task_id"])
            deform_dir_names.append(doc["dir_name"])

        elasticity_doc = ElasticityDoc.from_deformations_and_stresses(
            structure=Structure.from_dict(final_opt["output"]["structure"]),
            material_id=material_id,
            deformations=deforms,
            stresses=stresses,
            deformation_task_ids=deform_task_ids,
            deformation_dir_names=deform_dir_names,
            equilibrium_stress=-0.1 * Stress(final_opt["output"]["stress"]),
            optimization_task_id=final_opt["task_id"],
            optimization_dir_name=final_opt["dir_name"],
            fitting_method="finite_difference",
        )
        elasticity_doc = jsanitize(elasticity_doc.model_dump(), allow_bson=True)

        return elasticity_doc

    def update_targets(self, items: List[Dict]):
        """
        Insert the new elasticity docs into the elasticity collection.

        Args:
            items: elasticity docs
        """
        self.logger.info(f"Updating {len(items)} elasticity documents")

        self.elasticity.update(items, key="material_id")


def filter_opt_tasks(
    tasks: List[Dict],
    calc_types: Dict[str, str],
    target_calc_type: str = CalcType.GGA_Structure_Optimization,
) -> List[Dict]:
    """
    Filter optimization tasks, by
        - calculation type
    """
    opt_tasks = [t for t in tasks if calc_types[str(t["task_id"])] == target_calc_type]

    return opt_tasks


def filter_deform_tasks(
    tasks: List[Dict],
    calc_types: Dict[str, str],
    target_calc_type: str = CalcType.GGA_Deformation,
) -> List[Dict]:
    """
    Filter deformation tasks, by
        - calculation type
        - number of transformations
        - transformation class
    """
    deform_tasks = []
    for t in tasks:
        if calc_types[str(t["task_id"])] == target_calc_type:
            transforms = t["transmuter"]["transformations"]
            if (
                len(transforms) == 1
                and transforms[0] == "DeformStructureTransformation"
            ):
                deform_tasks.append(t)

    return deform_tasks


def filter_by_incar_settings(
    tasks: List[Dict], incar_settings: Optional[Dict[str, Any]] = None
) -> List[Dict]:
    """
    Filter tasks by incar parameters.
    """

    if incar_settings is None:
        incar_settings = {
            "LREAL": False,
            "ENCUT": 700,
            "PREC": "Accurate",
            "EDIFF": 1e-6,
        }

    selected = []
    for t in tasks:
        incar = t["orig_inputs"]["incar"]
        ok = True
        for k, v in incar_settings.items():
            if k not in incar:
                ok = False
                break

            if isinstance(incar[k], str):
                if incar[k].lower() != v.lower():
                    ok = False
                    break

            elif isinstance(incar[k], float):
                if not np.allclose(incar[k], v, atol=1e-10):
                    ok = False
                    break

            else:
                if incar[k] != v:
                    ok = False
                    break

        if ok:
            selected.append(t)

    return selected


def filter_opt_tasks_by_time(tasks: List[Dict], logger) -> Dict:
    """
    Filter a set of tasks to select the latest completed one.

    Args:
        tasks: the set of tasks to filter
        logger:

    Returns:
        selected latest task
    """
    return _filter_tasks_by_time(tasks, "optimization", logger)


def filter_deform_tasks_by_time(
    tasks: List[Dict], deform_comp_tol: float = 1e-5, logger=None
) -> List[Dict]:
    """
    For deformation tasks with the same deformation, select the latest completed one.

    Args:
        tasks: the deformation tasks
        deform_comp_tol: tolerance for comparing deformation equivalence

    Returns:
        filtered deformation tasks
    """

    mapping = TensorMapping(tol=deform_comp_tol)

    # group tasks by deformation
    for doc in tasks:
        # assume only one deformation, should be checked in `filter_deform_tasks()`
        deform = doc["transmuter"]["transformation_params"][0]["deformation"]

        if deform in mapping:
            mapping[deform].append(doc)
        else:
            mapping[deform] = [doc]

    # select the latest task for each deformation
    selected = []
    for docs in mapping.values():
        t = _filter_tasks_by_time(docs, "deformation", logger)
        selected.append(t)

    return selected


def _filter_tasks_by_time(tasks: List[Dict], mode: str, logger) -> Dict:
    """
    Helper function to filter a set of tasks to select the latest completed one.
    """
    if len(tasks) == 0:
        raise RuntimeError(f"Cannot filter {mode} task from 0 input tasks")
    elif len(tasks) == 1:
        return tasks[0]

    completed = [(datetime.fromisoformat(t["completed_at"]), t) for t in tasks]
    sorted_by_completed = sorted(completed, key=lambda pair: pair[0])
    latest_pair = sorted_by_completed[-1]
    selected = latest_pair[1]

    task_ids = [t["task_id"] for t in tasks]
    logger.info(
        f"Found multiple {mode} tasks {task_ids}; selected the latest task "
        f"{selected['task_id']} that is completed at {selected['completed_at']}."
    )

    return selected


def select_final_opt_deform_tasks(
    opt_tasks: List[Tuple[np.ndarray, Dict]],
    deform_tasks: List[Tuple[np.ndarray, List[Dict]]],
    logger,
    lattice_comp_tol: float = 1e-5,
) -> Tuple[Union[Dict, None], Union[List[Dict], None]]:
    """
    Select the final opt task and deform tasks for fitting.

    This is achieved by selecting the opt--deform pairs with the same lattice,
    and also with the most deform tasks.

    Returns:
        final_opt_task: selected opt task
        final_deform_tasks: selected deform tasks
    """

    # group opt and deform tasks by lattice
    mapping = TensorMapping(tol=lattice_comp_tol)
    for lat, opt_t in opt_tasks:
        mapping[lat] = {"opt_task": opt_t}

    for lat, dt in deform_tasks:
        if lat in mapping:
            mapping[lat]["deform_tasks"] = dt
        else:
            mapping[lat] = {"deform_tasks": dt}

    # select opt--deform paris with the most deform tasks
    selected = None
    num_deform_tasks = -1
    for lat, tasks in mapping.items():
        if "opt_task" in tasks and "deform_tasks" in tasks:
            n = len(tasks["deform_tasks"])
            if n > num_deform_tasks:
                selected = (tasks["opt_task"], tasks["deform_tasks"])
                num_deform_tasks = n

    if selected is None:
        tasks = [pair[1] for pair in opt_tasks]
        for pair in deform_tasks:
            tasks.extend(pair[1])

        ids = [t["task_id"] for t in tasks]
        logger.warning(
            f"Cannot find optimization and deformation tasks that match by lattice "
            f"for tasks {ids}"
        )

        final_opt_task = None
        final_deform_tasks = None
    else:
        final_opt_task, final_deform_tasks = selected

    return final_opt_task, final_deform_tasks


def group_by_parent_lattice(
    tasks: List[Dict], mode: str, lattice_comp_tol: float = 1e-5
) -> List[Tuple[np.ndarray, List[Dict]]]:
    """
    Groups a set of task docs by parent lattice equivalence.

    Args:
        tasks: task docs
        mode: determines which lattice to use. If `opt`, use the lattice of the
            output structure, and this is intended for optimization tasks. If
            `deform`, use the lattice of the output structure and transform it by the
            deformation in transmuter, and this is intended for deformation tasks.
        lattice_comp_tol: tolerance for comparing lattice equivalence.

    Returns:
        [(lattice, List[tasks])]: each tuple gives the common parent lattice of a
            list of the structures before deformation (if any), and the list tasks
            from which the structures are taken.
    """
    docs_by_lattice: List[Tuple[np.ndarray, List[Dict]]] = []

    for doc in tasks:
        sim_lattice = get(doc, "output.structure.lattice.matrix")

        if mode == "deform":
            transform_params = doc["transmuter"]["transformation_params"]
            deform = transform_params[0]["deformation"]
            parent_lattice = np.dot(sim_lattice, np.transpose(np.linalg.inv(deform)))
        elif mode == "opt":
            parent_lattice = np.array(sim_lattice)
        else:
            raise ValueError(f"Unsupported mode {mode}")

        match = False
        for unique_lattice, lattice_docs in docs_by_lattice:
            match = np.allclose(unique_lattice, parent_lattice, atol=lattice_comp_tol)
            if match:
                lattice_docs.append(doc)
                break
        if not match:
            docs_by_lattice.append((parent_lattice, [doc]))

    return docs_by_lattice
