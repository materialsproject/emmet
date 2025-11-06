from fastapi import HTTPException
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core import Structure
from pymatgen.entries.computed_entries import ComputedStructureEntry

from emmet.core.vasp.calculation import Calculation, get_trajectories_from_calculations
from emmet.core.trajectory import Trajectory


def calcs_reversed_to_trajectory(calcs_reversed: list[dict]):
    """
    Converts data from calc_reversed to emmet-core Trajectory objects
    that contain structure, energy, force and stress data for each
    ionic step.

    Args:
        calcs_reversed: List of dictionaries in calcs_reversed entry
            of a task document.
    """
    trajectories = []

    for calculation in calcs_reversed:

        if calculation.get("output", {}).get("ionic_steps"):
            trajectories.extend(
                get_trajectories_from_calculations(
                    [Calculation(**calculation)],
                    traj_class=Trajectory,  # type: ignore[arg-type]
                )
            )
        else:
            raise HTTPException(
                status_code=404, detail="No ionic step data found for task"
            )

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
