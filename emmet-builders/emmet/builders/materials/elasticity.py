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
            fitting_method: method to fit the elastic tensor: `finite_difference`,
                `pseudoinverse` or `independent`.
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

        # TODO optimization_task_id?
        self.elasticity.ensure_index("optimization_task_id")
        self.elasticity.ensure_index("last_updated")

    def get_items(
        self,
    ) -> Generator[Tuple[str, Dict[str, str], List[Dict]], None, None]:
        """
        Gets all items to process into elastic docs.

        Returns:
            material_id: material id for the tasks
            calc_types: calculation type of the tasks
            tasks: task docs belong to the same material
        """

        self.logger.info("Elastic Builder Started")

        self.ensure_index()

        cursor = self.materials.query(
            criteria=self.query, properties=["material_id", "calc_types", "task_ids"]
        )

        # query for tasks
        query = self.query.copy()

        for n, doc in enumerate(cursor):

            material_id = doc["material_id"]
            calc_types = {str(k): v for k, v in doc["calc_types"].items()}

            self.logger.debug(f"Getting tasks {n} with material_id {material_id}")

            # update query with task_ids
            query["task_id"] = {"$in": [int(i) for i in doc["task_ids"]]}

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
        Process all tasks belong to the same material into elastic doc.

        Args:
            item:
                material_id: material id for the tasks
                calc_types: {task_id: task_type} calculation type of the tasks
                tasks: task docs belong to the same material

        Returns:
            Elastic doc obtained from the list of task docs. `None` if not tasks
            satisfying the needs can be found.
        """

        # TODO Since the material id is assigned as the `smallest` task id of a set
        #  of tasks, the material id may not correspond to the selected optimization
        #  task. What to do here? reassign material id?
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

        # filter by incar
        opt_tasks = filter_by_incar_settings(opt_tasks)
        deform_tasks = filter_by_incar_settings(deform_tasks)

        # select one task for each set of optimization tasks with the same lattice
        opt_grouped = group_by_parent_lattice(opt_tasks, mode="opt")
        opt_grouped = [
            (lattice, filter_opt_tasks_by_time(tasks, self.logger))
            for lattice, tasks in opt_grouped
        ]

        # for deformed tasks with the same lattice, select one if there are multiple
        # tasks with the same deformation
        deform_grouped = group_by_parent_lattice(deform_tasks, mode="deform")
        deform_grouped = [
            (lattice, filter_deform_tasks_by_time(tasks))
            for lattice, tasks in deform_grouped
        ]

        # select the opt and deform tasks for fitting
        final_opt, final_deform = select_final_opt_deform_tasks(
            opt_grouped, deform_grouped, self.logger
        )
        if final_deform is None or final_deform is None:
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
            # -0.1 to convert to GPa from kBar and s
            stresses.append(-0.1 * Stress(doc["output"]["stress"]))
            deform_task_ids.append(doc["task_id"])
            deform_dir_names.append(doc["dir_name"])

        doc = ElasticityDoc.from_deformations_and_stresses(
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
        doc = jsanitize(doc.dict(), allow_bson=True)

        return doc

    def update_targets(self, items: List[Dict]):
        """
        Insert the new elastic docs into the elasticity collection.

        Args:
            items: elastic docs
        """
        self.logger.info(f"Updating {len(items)} elastic documents")

        self.elasticity.update(items, key="material_id")


def filter_opt_tasks(
    tasks: List[Dict],
    calc_types: Dict[str, str],
    target_calc_type: str = CalcType.GGA_Structure_Optimization,
) -> List[Dict]:
    """
    Filter out optimization tasks, by
        - calculation type
    """
    opt_tasks = [t for t in tasks if calc_types[str(t["task_id"])] == target_calc_type]

    # TODO additional check? e.g. max force, stress ...

    return opt_tasks


def filter_deform_tasks(
    tasks: List[Dict],
    calc_types: Dict[str, str],
    target_calc_type: str = CalcType.GGA_Deformation,
) -> List[Dict]:
    """
    Filter out deformation tasks, by
        - calculation type
        - number of deformations (transformations)
    """
    deform_tasks = []
    for t in tasks:
        if calc_types[str(t["task_id"])] == target_calc_type:
            transforms = t["transmuter"]["transformation_params"]
            if len(transforms) == 1:
                deform_tasks.append(t)

    return deform_tasks


def filter_by_incar_settings(
    tasks: List[Dict], incar_settings: Dict[str, Any] = None
) -> List[Dict]:
    """
    Filter the tasks by incar parameters.
    """
    # TODO do we want to check kpoint schema?

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
        tasks: the set of tasks to filer
        logger:

    Returns:
        selected latest task
    """
    if len(tasks) == 0:
        raise RuntimeError("Cannot select latest from 0 tasks")
    elif len(tasks) == 1:
        return tasks[0]
    else:
        completed = [(datetime.fromisoformat(t["completed_at"]), t) for t in tasks]
        sorted_by_completed = sorted(completed, key=lambda pair: pair[0])
        latest_pair = sorted_by_completed[-1]
        selected = latest_pair[1]

        task_ids = [t["task_id"] for t in tasks]
        logger.warning(
            f"Select the latest task {selected['task_id']} completed at "
            f"{selected['completed_at']} from a set of tasks: {task_ids}."
        )

        return selected


def filter_deform_tasks_by_time(
    tasks: List[Dict], deform_comp_tol: float = 1e-5
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

    for doc in tasks:

        # assume only one deformation, should be checked in `filter_deform_tasks()`
        deform = doc["transmuter"]["transformation_params"][0]["deformation"]

        if deform in mapping:
            current = datetime.fromisoformat(doc["completed_at"])
            exist = datetime.fromisoformat(mapping[deform]["completed_at"])
            if current > exist:
                mapping[deform] = doc
        else:
            mapping[deform] = doc

    selected = list(mapping.values())

    return selected


def select_final_opt_deform_tasks(
    opt_tasks: List[Tuple[np.ndarray, Dict]],
    deform_tasks: List[Tuple[np.ndarray, List[Dict]]],
    logger,
    lattice_comp_tol: float = 1e-5,
) -> Tuple[Dict, List[Dict]]:
    """
    Select the final opt and deform tasks.

    This is achieved by selecting the opt--deform pairs with the same lattice,
    and also with the most number of deform tasks.

    Args:
        opt_tasks:
        deform_tasks:
        lattice_comp_tol:

    Returns:
        final_opt_task:
        final_deform_tasks:
    """

    # group by lattice
    mapping = TensorMapping(tol=lattice_comp_tol)
    for lat, t in opt_tasks:
        mapping[lat] = {"opt_task": t}

    for lat, t in deform_tasks:
        if lat in mapping:
            mapping[lat]["deform_tasks"] = t
        else:
            mapping[lat] = {"deform_tasks": t}

    # select the opt deform paris with the most number of deform tasks
    selected = None
    num_deform_tasks = -1
    for lat, tasks in mapping.items():
        if "deform_tasks" not in tasks:
            logger.debug(
                f"No deformation tasks found for optimization task "
                f"{tasks['opt_task']['task_id']}"
            )
        elif "opt_task" not in tasks:
            pass
        else:
            n = len(tasks["deform_tasks"])
            if n > num_deform_tasks:
                selected = (tasks["opt_task"], tasks["deform_tasks"])
                num_deform_tasks = n

    if selected is None:
        tasks = [pair[1] for pair in opt_tasks]
        for pair in deform_tasks:
            tasks.extend(pair[1])
        ids = [t["task_id"] for t in tasks]
        logger.error(
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
        [(lattice, List[tasks])]. Each tuple gives the lattice and a list of tasks
            with the same lattice before deformation.
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
