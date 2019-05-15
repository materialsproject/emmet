from maggma.builders import MapBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TaskTagger(MapBuilder):
    def __init__(self, tasks, task_types, **kwargs):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
        """
        self.tasks = tasks
        self.task_types = task_types
        self.kwargs = kwargs

        super().__init__(source=tasks, target=task_types, ufn=self.calc, projection=["orig_inputs"], **kwargs)

    def calc(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        tt = task_type(item["orig"])
        return {"task_type": tt}


def task_type(inputs):
    """
    Determines the task_type for a QChem calculations

    Args:
        inputs (dict): inputs dict

    """
    pass
