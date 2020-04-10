from typing import Dict, List, Union
import numpy as np

from maggma.core import Store
from maggma.builders import MapBuilder

from pymatgen import Structure

from emmet.core.utils import run_type, task_type
from emmet.builders import SETTINGS

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TaskTagger(MapBuilder):
    def __init__(
        self,
        tasks: Store,
        task_types: Store,
        kpts_tolerance: float = SETTINGS.kpts_tolerance,
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks: Store of task documents
            task_types: Store of task_types for tasks
            input_sets: dictionary of task_type and pymatgen input set to validate against
            kpts_tolerance: the minimum kpt density as dictated by the InputSet to require
            LDAU_fields: LDAU fields to check for consistency
        """
        self.tasks = tasks
        self.task_types = task_types
        self.kpts_tolerance = kpts_tolerance

        self.kwargs = kwargs

        super().__init__(
            source=tasks,
            target=task_types,
            projection=["orig_inputs", "output.structure", "input.parameters"],
            **kwargs,
        )

    def unary_function(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        _task_type = task_type(item.get("orig_inputs", {}))
        _run_type = run_type(item.get("input", {}).get("parameters", {}))

        iv = is_valid(
            item["output"]["structure"],
            item["orig_inputs"],
            SETTINGS.default_input_sets,
            self.kpts_tolerance,
            SETTINGS.ldau_fields,
        )

        d = {"task_type": _task_type, "run_type": _run_type, **iv}
        return d


def is_valid(
    structure: Union[dict, Structure],
    inputs: Dict,
    input_sets: Dict,
    kpts_tolerance: float = 0.9,
    LDAU_fields: List[str] = ["LDAUU", "LDAUJ", "LDAUL"],
):
    """
    Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

    Args:
        structure the output structure from the calculation
        inputs : a dict representation of the inputs in traditional pymatgen inputset form
        input_sets (dict): a dictionary of task_types -> pymatgen input set for validation
        kpts_tolerance (float): the tolerance to allow kpts to lag behind the input set settings
        LDAU_fields (list(String)): LDAU fields to check for consistency
    """

    if isinstance(structure, dict):
        structure = Structure.from_dict(structure)
    tt = task_type(inputs)

    d = {"is_valid": True, "warnings": []}

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
            d["warnings"].append("Too few KPoints")

        # Checking ENCUT
        encut = inputs.get("incar", {}).get("ENCUT")
        valid_encut = valid_input_set.incar["ENCUT"]
        d["encut_ratio"] = float(encut) / valid_encut
        if d["encut_ratio"] < 1:
            d["is_valid"] = False
            d["warnings"].append("ENCUT too low")

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
                d["warnings"].append("LDAU parameters don't match")

    if len(d["warnings"]) == 0:
        del d["warnings"]

    return d
