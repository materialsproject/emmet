from maggma.builders import MapBuilder

__author__ = "Sam Blau, Shyam Dwaraknath"


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

        super().__init__(source=tasks, target=task_types, ufn=self.calc, projection=["orig","output"], **kwargs)

    def calc(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        tt = task_type(inputs=item["orig"],output=item["output"])
        return {"task_type": tt}


def task_type(inputs,output):
    """
    Determines the task_type of a QChem task doc

    Args:
        inputs (dict): task orig dict
        outputs (dict): task output dict

    """

    job_type = inputs["rem"]["job_type"]
    if job_type == "opt" or job_type == "optimization":
        if output["job_type"] == "freq" or output["job_type"] == "frequency":
            job_type = "Frequency Flattening Optimization"
        else:
            job_type = "Optimization"
    elif job_type == "freq" or job_type == "frequency":
        job_type = "Frequency"
    elif job_type == "force":
        job_type = "Force"
    elif job_type == "sp":
        job_type = "Single Point"

    env = "Vacuum"
    if "solvent_method" in inputs["rem"]:
        env = inputs["rem"]["solvent_method"]
        if env == "pcm":
            env = "PCM"
        elif env == "smd":
            env = "SMD"

    return env + " " + job_type
