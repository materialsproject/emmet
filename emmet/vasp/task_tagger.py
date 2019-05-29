import os
import numpy as np
from maggma.builders import MapBuilder
from pymatgen import Structure
from atomate.utils.utils import load_class


__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_validation_settings = os.path.join(
    module_dir, "settings", "task_validation.yaml"
)


class TaskTagger(MapBuilder):
    def __init__(
        self, tasks, task_types, input_sets=None, kpts_tolerance=0.9, **kwargs
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
            input_sets (Dict): dictionary of task_type and pymatgen input set to validate against
            kpts_tolerance (float): the minimum kpt density as dictated by the InputSet to require
        """
        self.tasks = tasks
        self.task_types = task_types
        self.input_sets = input_sets or {
            "GGA Structure Optimization": "MPRelaxSet",
            "GGA+U Structure Optimization": "MPRelaxSet",
        }
        self.kpts_tolerance = kpts_tolerance

        self._input_sets = {
            name: load_class("pymatgen.io.vasp.sets", inp_set)
            for name, inp_set in self.input_sets.items()
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
            self.kpts_tolerance,
        )

        d = {"task_type": tt, **iv}
        return d


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
        num_kpt_labels = len(
            list(filter(None.__ne__, inputs.get("kpoints", {}).get("labels", []) or []))
        )
        if num_kpt_labels > 0:
            return calc_type + "NSCF Line"
        else:
            return calc_type + "NSCF Uniform"

    elif incar.get("LEPSILON", False):
        return calc_type + "Static Dielectric"

    elif incar.get("LCHIMAG", False):
        return calc_type + "NMR Chemical Shielding"

    elif incar.get("LEFG", False):
        return calc_type + "NMR Electric Field Gradient"

    # these criteria for detecting magnetic ordering calculations are slightly
    # arbitrary and may need to be revisited in future, they are included for
    # now to make building cleaner and to better declare the intent of these
    # calculations on the Materials Project website - @mkhorton

    elif (
        incar.get("ISPIN", 1) == 2
        and incar.get("LASPH", False)
        and incar.get("ISYM", False)
        and incar.get("NSW", 1) == 0
    ):
        return calc_type + "Magnetic Ordering Static"

    elif (
        incar.get("ISPIN", 1) == 2
        and incar.get("LASPH", False)
        and incar.get("ISYM", False)
        and incar.get("ISIF", 2) == 3
        and incar.get("IBRION", 0) > 0
    ):
        return calc_type + "Magnetic Ordering Structure Optimization"

    elif incar.get("NSW", 1) == 0:
        return calc_type + "Static"

    elif incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        return calc_type + "Structure Optimization"

    elif incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        return calc_type + "Deformation"

    return ""


def is_valid(structure, inputs, input_sets, kpts_tolerance=0.9):
    """
    Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

    Args:
        structure (dict or Structure): the output structure from the calculation
        inputs (dict): a dict representation of the inputs in traditional pymatgen inputset form
        input_sets (dict): a dictionary of task_types -> pymatgen input set for validation
        kpts_tolerance (float): the tolerance to allow kpts to lag behind the input set settings
    """

    if isinstance(structure, dict):
        structure = Structure.from_dict(structure)
    tt = task_type(inputs)

    d = {"is_valid": True, "_warnings": []}

    if tt in input_sets:
        valid_input_set = input_sets[tt](structure)

        # Checking K-Points
        valid_num_kpts = valid_input_set.kpoints.num_kpts or np.prod(
            valid_input_set.kpoints.kpts[0]
        )
        num_kpts = inputs.get("kpoints", {}).get("nkpoints", 0) or np.prod(
            inputs.get("kpoints", {}).get("kpoints", [1, 1, 1])
        )
        d["kpts_ratio"] = num_kpts / valid_num_kpts
        if d["kpts_ratio"] < kpts_tolerance:
            d["is_valid"] = False
            d["_warnings"].append("Too few KPoints")

        # Checking ENCUT
        encut = inputs.get("incar", {}).get("ENCUT")
        valid_encut = valid_input_set.incar["ENCUT"]
        d["encut_ratio"] = float(encut) / valid_encut
        if d["encut_ratio"] < 1:
            d["is_valid"] = False
            d["_warnings"].append("ENCUT too low")

        # Checking U-values
        if valid_input_set.incar.get("LDAU"):
            ldau_fields = ["LDAUU", "LDAUJ", "LDAUL"]

            # Assemble actual input LDAU params into dictionary to account for possibility
            # of differing order of elements
            structure_set_symbol_set = structure.symbol_set
            inputs_ldau_fields = [structure_set_symbol_set] + [
                inputs.get("incar", {}).get(k) for k in ldau_fields
            ]
            input_ldau_params = {d[0]: d[1:] for d in zip(*inputs_ldau_fields)}

            # Assemble required input_set LDAU params into dictionary
            input_set_symbol_set = valid_input_set.poscar.structure.symbol_set
            input_set_ldau_fields = [input_set_symbol_set] + [
                valid_input_set.incar.get(k) for k in ldau_fields
            ]
            input_set_ldau_params = {d[0]: d[1:] for d in zip(*input_set_ldau_fields)}

            if any(
                input_set_ldau_params[el] != input_params
                for el, input_params in input_ldau_params.items()
            ):
                d["is_valid"] = False
                d["_warnings"].append("LDAU parameters don't match")

    if len(d["_warnings"]) == 0:
        del d["_warnings"]

    return d
