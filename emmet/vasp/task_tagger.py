import os
import numpy as np
from monty.serialization import loadfn
from maggma.builders import MapBuilder
from pymatgen import Structure
from atomate.utils.utils import load_class


__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))


class TaskTagger(MapBuilder):
    def __init__(self, tasks, task_types, input_sets=None, **kwargs):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
        """
        self.tasks = tasks
        self.task_types = task_types
        self.input_sets = input_sets
        self._task_validation = loadfn(
            os.path.join(module_dir, "settings", "task_validation.yaml")
        )

        self._input_sets = {
            name: load_class("pymatgen.io.vasp.sets", inp_set)
            for name, inp_set in self._task_validation["input_sets"].items()
        }

        self.kwargs = kwargs

        super().__init__(
            source=tasks,
            target=task_types,
            ufn=self.calc,
            projection=["orig_inputs", "output.structure"],
            **kwargs,
        )

    def calc(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        tt = task_type(item["orig_inputs"])
        iv = is_valid(
            item["output"]["structure"],
            item["orig_inputs"],
            self._input_sets,
            self._task_validation.get("kpts_tolerance", 0.9),
        )

        return {"task_type": tt, "is_valid": iv}


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
        if (
            len(list(filter(None.__ne__, inputs.get("kpoints", {}).get("labels", []))))
            > 0
        ):
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


def is_valid(structure, inputs, input_sets, kpts_tolerance=0.9):

    if isinstance(structure, dict):
        structure = Structure.from_dict(structure)
    tt = task_type(inputs)

    if tt in input_sets:
        print("Found a valid input set")
        valid_input_set = input_sets[tt](structure)

        valid_num_kpts = valid_input_set.kpoints.num_kpts or np.prod(
            valid_input_set.kpoints.kpts[0]
        )
        num_kpts = inputs.get("kpoints", {}).get("num_kpts", 0) or np.prod(
            inputs.get("kpoints", {}).get("kpts", [1, 1, 1])
        )
        print(f"Needed Kpts vs Actual Kpts: {valid_num_kpts}, {num_kpts}")
        if (kpts_tolerance * num_kpts) < valid_num_kpts:
            return False

        if inputs.get("incar", {}).get("ENCUT") < valid_input_set.incar["ENCUT"]:
            return False

    return True
