from collections import defaultdict
from typing import List

from fastapi import HTTPException
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core import Structure
from pymatgen.core.trajectory import Trajectory
from pymatgen.entries.computed_entries import ComputedStructureEntry


def calcs_reversed_to_trajectory(calcs_reversed: List[dict]):
    """
    Converts data from calc_reversed to pymatgen Trajectory objects
    that contain structure, energy, force and stress data for each
    ionic step.

    Args:
        calcs_reversed: List of dictionaries in calcs_reversed entry
            of a task document.
    """
    trajectories = []

    for calculation in calcs_reversed:
        structures = []
        frame_props = defaultdict(list)  # type: dict

        steps = calculation.get("output", {}).get("ionic_steps", None)

        if steps is None:
            raise HTTPException(
                status_code=404, detail="No ionic step data found for task"
            )
        else:
            for step in steps:

                structure_dict = step.get("structure", None)

                if structure_dict is not None:
                    structure = Structure.from_dict(structure_dict)

                structures.append(structure)

                frame_props["e_fr_energy"].append(step.get("e_fr_energy", None))
                frame_props["e_wo_entrp"].append(step.get("e_wo_entrp", None))
                frame_props["e_0_energy"].append(step.get("e_0_energy", None))
                frame_props["forces"].append(step.get("forces", None))
                frame_props["stresses"].append(step.get("stress", None))
                frame_props["electronic_steps"].append(
                    step.get("electronic_steps", None)
                )

            traj = Trajectory.from_structures(
                structures, frame_properties=frame_props, time_step=None
            ).as_dict()
            trajectories.append(traj)

    return trajectories


def task_to_entry(doc: dict, include_structure: bool = True):
    """Turns a Task Doc into a ComputedStructureEntry"""

    input = doc.get("input", None)
    output = doc.get("output", None)

    try:

        output_struct = Structure.from_dict(output["structure"])

        entry_dict = {
            "correction": 0.0,
            "entry_id": doc["task_id"],
            "composition": output_struct.composition,
            "energy": output.get("energy", None),
            "parameters": {
                "potcar_spec": input.get("potcar_spec", None),
                "is_hubbard": input.get("is_hubbard", None),
                "hubbards": input.get("hubbards", None),
                "run_type": str(doc["run_type"]) if "run_type" in doc else None,
                "task_type": str(doc["task_type"]) if "task_type" in doc else None,
            },
            "data": {
                "oxide_type": oxide_type(output_struct),
                "aspherical": input.get("parameters", {}).get("LASPH", False),
                "last_updated": doc["last_updated"] if "last_updated" in doc else None,
                "completed_at": doc["completed_at"] if "completed_at" in doc else None,
            },
            "structure": output_struct,
        }

        return ComputedStructureEntry.from_dict(entry_dict).as_dict()

    except (AttributeError, KeyError, TypeError):
        return "Problem obtaining entry for {}. It might be missing necessary output structure information.".format(
            doc["task_id"]
        )
