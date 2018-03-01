from maggma.builder import Builder
from pydash import py_

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TaskTagger(Builder):

    def __init__(self, tasks, task_types, **kwargs):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
        """
        self.tasks = tasks
        self.task_types = task_types

        super().__init__(sources=[tasks], targets=[task_types], **kwargs)

    def get_items(self):
        """
        Returns all task docs and tag definitions to process

        Returns:
            generator or list of task docs and tag definitions
        """

        # Determine tasks to process.
        self.logger.info("Determining tasks to process")
        all_task_ids = self.tasks.distinct("task_id", {"state": "successful"})
        previous_task_ids = self.task_types.distinct("task_id")
        to_process = list(set(all_task_ids) - set(previous_task_ids))

        self.logger.info("Yielding task documents")
        for task_id in to_process:
            yield self.tasks.query_one(criteria={"task_id": task_id}, properties=["task_id", "orig_inputs"])

    def process_item(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        tt = task_type(item["orig_inputs"])
        return {"task_id": item["task_id"], "task_type": tt}

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([dict]): task_type dicts to insert into task_types collection
        """
        with_task_type, without_task_type = py_.partition(items, lambda i: i["task_type"])
        if without_task_type:
            self.logger.error("No task type found for {}".format(without_task_type))
        if len(with_task_type) > 0:
            self.task_types.update(with_task_type)


def task_type(inputs, include_calc_type=True):
    """
    Determines the task_type

    Args:
        inputs (dict): inputs dict with an incar, kpoints, potcar, and poscar dictionaries
        include_calc_type (bool): whether to include calculation type
            in task_type such as HSE, GGA, SCAN, etc.
    """

    calc_type = ""

    incar = inputs.get("incar", {})

    if include_calc_type:
        if incar.get("LHFCALC", False):
            calc_type += "HSE "
        elif incar.get("METAGGA", "") == "SCAN":
            calc_type += "SCAN "
        elif incar.get("LDAU", False):
            calc_type += "GGA+U "
        else:
            calc_type += "GGA "

    if incar.get("ICHARG", 0) > 10:
        if len(list(filter(None, inputs.get("kpoints", {}).get("labels", [])))) > 0:
            return calc_type + "NSCF Line"
        else:
            return calc_type + "NSCF Uniform"

    if incar.get("LEPSILON", False):
        return calc_type + "Static Dielectric"

    if incar.get("NSW", 1) == 0:
        return calc_type + "Static"

    if incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        return calc_type + "Structure Optimization"

    if incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        return calc_type + "Deformation"

    return ""
