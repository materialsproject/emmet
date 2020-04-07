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
        self,
        tasks,
        task_types,
        input_sets=None,
        kpts_tolerance=0.9,
        LDAU_fields=["LDAUU", "LDAUJ", "LDAUL"],
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
            input_sets (Dict): dictionary of task_type and pymatgen input set to validate against
            kpts_tolerance (float): the minimum kpt density as dictated by the InputSet to require
            LDAU_fields (list(String)): LDAU fields to check for consistency
        """
        self.tasks = tasks
        self.task_types = task_types
        self.input_sets = input_sets or {
            "GGA Structure Optimization": "MPRelaxSet",
            "GGA+U Structure Optimization": "MPRelaxSet",
        }
        self.kpts_tolerance = kpts_tolerance
        self.LDAU_fields = LDAU_fields

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
            self.LDAU_fields,
        )

        d = {"task_type": tt, **iv}
        return d


def is_valid(
    structure,
    inputs,
    input_sets,
    kpts_tolerance=0.9,
    LDAU_fields=["LDAUU", "LDAUJ", "LDAUL"],
):
    """
    Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

    Args:
        structure (dict or Structure): the output structure from the calculation
        inputs (dict): a dict representation of the inputs in traditional pymatgen inputset form
        input_sets (dict): a dictionary of task_types -> pymatgen input set for validation
        kpts_tolerance (float): the tolerance to allow kpts to lag behind the input set settings
        LDAU_fields (list(String)): LDAU fields to check for consistency
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
            # Assemble actual input LDAU params into dictionary to account for possibility
            # of differing order of elements
            structure_set_symbol_set = structure.symbol_set
            inputs_ldau_fields = [structure_set_symbol_set] + [
                inputs.get("incar", {}).get(k, []) for k in LDAU_fields
            ]
            input_ldau_params = {d[0]: d[1:] for d in zip(*inputs_ldau_fields)}

            # Assemble required input_set LDAU params into dictionary
            input_set_symbol_set = valid_input_set.poscar.structure.symbol_set
            input_set_ldau_fields = [input_set_symbol_set] + [
                valid_input_set.incar.get(k) for k in LDAU_fields
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
