from fastapi import HTTPException
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core import Structure
from pymatgen.core.trajectory import Trajectory
from pymatgen.entries.computed_entries import ComputedStructureEntry


def calcs_reversed_to_trajectory(calcs_reversed: list[dict]):
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
        frame_props = []

        steps = calculation.get("output", {}).get("ionic_steps", None)

        if steps is None:
            raise HTTPException(
                status_code=404, detail="No ionic step data found for task"
            )
        else:
            for step in steps:
                step_dict = {}

                structure_dict = step.get("structure", None)

                if structure_dict is not None:
                    structure = Structure.from_dict(structure_dict)

                structures.append(structure)

                step_dict["e_fr_energy"] = step.get("e_fr_energy", None)
                step_dict["e_wo_entrp"] = step.get("e_wo_entrp", None)
                step_dict["e_0_energy"] = step.get("e_0_energy", None)
                step_dict["forces"] = step.get("forces", None)
                step_dict["stresses"] = step.get("stress", None)
                step_dict["electronic_steps"] = step.get("electronic_steps", None)

                frame_props.append(step_dict)

            traj = Trajectory.from_structures(
                structures, frame_properties=frame_props, time_step=None
            ).as_dict()
            trajectories.append(traj)

    return trajectories


def task_to_entry(doc: dict, include_structure: bool = True):
    """Turns a Task Doc into a ComputedStructureEntry"""

    input = doc.get("input", {})
    output = doc.get("output", {})

    try:
        # NB: Structure.from_dict({}) raises KeyError
        output_struct = Structure.from_dict(output.get("structure", {}))

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
