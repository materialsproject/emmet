import itertools
from datetime import datetime
from typing import (
    Any,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

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

DEFORM_TASK_LABEL = "elastic deformation"
OPTIM_TASK_LABEL = "elastic structure optimization"

DEFORM_COMP_TOL = 1e-5
LATTICE_COMP_TOL = 1e-5


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

    def get_items(self) -> Generator[Tuple[str, List[str], List[Dict]], None, None]:
        """
        Gets all items to process into elastic docs.

        Returns:
            material_id: material id for the tasks
            calc_type: calculation type of the tasks
            tasks: a list task docs belong to the same material
        """

        self.logger.info("Elastic Builder Started")

        self.ensure_index()

        cursor = self.materials.query(
            criteria=self.query, properties=["material_id", "calc_type", "task_ids"]
        )

        # query for tasks
        query = self.query.copy()
        # query["task_label"] = {"$regex": f"({DEFORM_TASK_LABEL})|({OPTIM_TASK_LABEL})"}

        for n, doc in enumerate(cursor):

            material_id = doc["material_id"]
            calc_type = doc["calc_type"]

            self.logger.debug(f"Getting tasks {n} with material_id {material_id}")

            # update query with task_ids
            query["task_id"] = {"$in": [int(i) for i in doc["task_ids"]]}

            projections = [
                "output",
                "input",
                "completed_at",
                "transmuter",
                "task_id",
                # "task_label",
                "formula_pretty",
                "dir_name",
            ]

            task_cursor = self.tasks.query(criteria=query, properties=projections)
            tasks = list(task_cursor)

            yield material_id, calc_type, tasks

    def process_item(self, item: Tuple[str, List[str], List[Dict]]) -> Dict:
        """
        Process all tasks belong to the same material into elastic docs

        There can be multiple optimization tasks for the same material due to, e.g.
        later fixes of earlier calculations. The optimization task with later completed
        time is selected. As a result, there can be multiple deformation tasks
        corresponding to the same deformation, and the deformation tasks are filtered:
        - VASP INCAR params (ensure key INCAR params of optimization tasks are the
          same as the optimization task)
        - task completion time (if INCAR params cannot distinguish them, they are
          filtered by completion time)

        Args:
            item:
                material id:
                calc_type:
                tasks: list of task docs that belong to the same material

        Returns:
            elastic doc obtained from the list of task docs
        """

        # TODO Since the material id is assigned as the `smallest` task id of a set
        #  of tasks, the material id may not correspond to the selected optimization
        #  task. What to do here? reassign material id?
        material_id, calc_type, tasks = item

        if len(tasks) != len(calc_type):
            self.logger.error(
                f"Number of tasks ({len(tasks)}) is not equal to number of calculation "
                f"types ({len(calc_type)}) for material with material id "
                f"{material_id}. Cannot proceed."
            )
            return None

        opt_tasks = filter_opt_tasks(tasks, calc_type)
        deform_tasks = filter_deform_tasks(tasks, calc_type)

        opt_tasks = filter_incar_settings(opt_tasks)
        deform_tasks = filter_incar_settings(deform_tasks)

        #
        #
        #
        #
        #

        # # group tasks having the same lattice
        # grouped = group_deform_tasks_by_opt_task(tasks, self.logger)
        #
        # # TODO, this for loop is a bit suscipious: for the same material (i.e.
        # #  material with the same material_id) there would only be one elastic doc;
        # #  then why we end up with multiple?
        # #  Basically, this is a question about `group_deform_tasks_by_opt_task`,
        # #  which groups the reactions by lattices. Although these lattice values can be
        # #  different, they are the same material upon symmetry operation.
        # #  Check the atomate1 implementation to see whether there is misunderstanding.
        # #  NOTE, the grouping by lattice achieved above should be used as filter to
        # #  decide which set of
        #
        # elastic_docs = []
        # for opt_tasks, deform_tasks in grouped:
        #
        #     # filter opt and deform tasks such that there is only one opt task and
        #     # the deformation tasks are independent
        #     opt_task = filter_opt_tasks_by_time(opt_tasks, self.logger)
        #     deform_tasks = filter_deform_tasks_by_incar(opt_task, deform_tasks)
        #     deform_tasks = filter_deform_tasks_by_time(
        #         opt_task, deform_tasks, self.logger
        #     )
        #
        #     structure = Structure.from_dict(opt_task["output"]["structure"])
        #
        #     deformations = []
        #     stresses = []
        #     deformation_task_ids = []
        #     deformation_dir_names = []
        #     for doc in deform_tasks:
        #         deformations.append(
        #             Deformation(
        #                 doc["transmuter"]["transformation_params"][0]["deformation"]
        #             )
        #         )
        #         # -0.1 to convert to GPa from kBar and s
        #         stresses.append(-0.1 * Stress(doc["output"]["stress"]))
        #         deformation_task_ids.append(doc["task_id"])
        #         deformation_dir_names.append(doc["dir_name"])
        #
        #     doc = ElasticityDoc.from_deformations_and_stresses(
        #         structure=structure,
        #         material_id=MPID(np.random.randint(1, 10000)),  # TODO
        #         deformations=deformations,
        #         stresses=stresses,
        #         deformation_task_ids=deformation_task_ids,
        #         deformation_dir_names=deformation_dir_names,
        #         equilibrium_stress=-0.1 * Stress(opt_task["output"]["stress"]),
        #         optimization_task_id=opt_task["task_id"],
        #         optimization_dir_name=opt_task["dir_name"],
        #         fitting_method="finite_difference",
        #     )
        #
        #     if doc:
        #         doc = jsanitize(doc.dict(), allow_bson=True)
        #         elastic_docs.append(doc)
        #
        # return elastic_docs

    def update_targets(self, items: List[List[Dict]]):
        """
        Insert the new elastic docs into the elasticity collection.

        Args:
            items: elastic docs
        """
        items_flatten = list(itertools.chain.from_iterable(items))

        self.logger.info(f"Updating {len(items_flatten)} elastic documents")

        self.elasticity.update(items_flatten, key="material_id")


def filter_opt_tasks(
    tasks: List[Dict],
    calc_type: List[str],
    target_calc_type: str = CalcType.GGA_Structure_Optimization,
) -> List[Dict]:
    """
    Filter out optimization tasks, by
        - calculation type
    """
    opt_tasks = [t for t, c in zip(tasks, calc_type) if c == target_calc_type]

    # TODO additional check? e.g. max force, stress ...

    return opt_tasks


def filter_deform_tasks(
    tasks: List[Dict],
    calc_type: List[str],
    target_calc_type: str = CalcType.GGA_Deformation,
) -> List[Dict]:
    """
    Filter out deformation tasks, by
        -  calculation type
        - number of deformations (transformations)
    """
    deform_tasks = []
    for t, c in zip(tasks, calc_type):
        transforms = t["transmuter"]["transformation_params"]
        if c == target_calc_type and len(transforms) == 1:
            deform_tasks.append(t)

    return deform_tasks


def filter_incar_settings(
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
        incar = t["orig_input"]["incar"]
        ok = True
        for k, v in incar_settings.items():
            if k not in incar:
                ok = False
                break

            if isinstance(incar[k], str):
                if incar[k].lower() != v.lower():
                    ok = False
                    break
            else:
                if incar[k].lower() != v.lower():
                    ok = False
                    break

        if ok:
            selected.append(t)

    return selected


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
        #  task? Use which one?
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
    opt_task: Dict, deform_tasks: List[Dict], logger
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
                "Non-equivalent calculated and stored deformations for optimization "
                f"task {opt_task_id} and deformation task {deform_task_id}."
            )

        if deform in d2t:
            current = datetime.fromisoformat(doc["completed_at"])
            exist = datetime.fromisoformat(d2t[deform]["completed_at"])
            if current > exist:
                d2t[deform] = doc
        else:
            d2t[deform] = doc

    return list(d2t.values())


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


def group_by_parent_lattice(
    docs: Union[Iterator[Dict], List[Dict]], logger
) -> List[Tuple[np.ndarray, List[Dict]]]:
    """
    Groups a set of task documents by parent lattice equivalence.

    Args:
        docs: task docs
        logger:

    Returns:
        [(lattice, List[tasks])], tuple of lattice and a list of tasks with the same
        lattice before deformation
    """

    docs_by_lattice: List[Tuple[np.ndarray, List[Dict]]] = []
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
