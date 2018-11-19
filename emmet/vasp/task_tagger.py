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
        tt = task_type(item["orig_inputs"])
        return {"task_type": tt}


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

    METAGGA_TYPES = {"TPSS", "RTPSS", "M06L", "MBJL", "SCAN", "MS0", "MS1", "MS2"}

    if include_calc_type:
        if incar.get("LHFCALC", False):
            calc_type += "HSE "
        elif incar.get("METAGGA", "").strip().upper() in METAGGA_TYPES:
            calc_type += incar["METAGGA"].strip().upper()
            calc_type += " "
        elif incar.get("LDAU", False):
            calc_type += "GGA+U "
        else:
            calc_type += "GGA "

    if incar.get("ICHARG", 0) > 10:
        if len(list(filter(None.__ne__, inputs.get("kpoints", {}).get("labels", [])))) > 0:
            return calc_type + "NSCF Line"
        else:
            return calc_type + "NSCF Uniform"

    elif incar.get("LEPSILON", False):
        return calc_type + "Static Dielectric"

    elif incar.get("LCHIMAG", False):
        return calc_type + "NMR Chemical Shielding"

    elif incar.get("LEFG", False):
        return calc_type + "NMR Electric Field Gradient"

    elif incar.get("NSW", 1) == 0:
        return calc_type + "Static"

    elif incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        return calc_type + "Structure Optimization"

    elif incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        return calc_type + "Deformation"

    return ""
