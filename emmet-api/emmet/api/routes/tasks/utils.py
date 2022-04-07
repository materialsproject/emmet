from pymatgen.core import Structure
from pymatgen.core.trajectory import Trajectory
from collections import defaultdict
from typing import List
from fastapi import HTTPException


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
            raise HTTPException(status_code=404, detail="No ionic step data found for task")
        else:
            for step in steps:

                structure_dict = step.get("structure", None)
                structure = Structure.from_dict(structure_dict) if structure_dict is not None else None

                structures.append(structure)

                frame_props["e_fr_energy"].append(step.get("e_fr_energy", None))
                frame_props["e_wo_entrp"].append(step.get("e_wo_entrp", None))
                frame_props["e_0_energy"].append(step.get("e_0_energy", None))
                frame_props["forces"].append(step.get("forces", None))
                frame_props["stresses"].append(step.get("stress", None))

            traj = Trajectory.from_structures(
                structures, frame_properties=frame_props, time_step=None
            ).as_dict()
            trajectories.append(traj)

    return trajectories
