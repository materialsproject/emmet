from typing import List

import numpy as np

from fastapi import HTTPException
from pymatgen.core import Molecule
from pymatgen.core.trajectory import Trajectory


def calcs_reversed_to_trajectory(calcs_reversed: List[dict]):
    """
    Converts data from calc_reversed to pymatgen Trajectory objects
    that contain structure, energy, and gradient data for each
    geometry optimization step.

    Args:
        calcs_reversed: List of dictionaries in calcs_reversed entry
            of a task document.
    """
    trajectories = list()

    for calculation in calcs_reversed:
        species = calculation.get("species")
        charge = calculation.get("charge")
        multiplicity = calculation.get("multiplicity")
        geometries = calculation.get("geometries")
        energies = calculation.get("energy_trajectory")
        total_gradients = calculation.get("gradients")
        pcm_gradients = calculation.get("pcm_gradients")
        cds_gradients = calculation.get("CDS_gradients")
        mulliken = calculation.get("Mulliken")
        resp = calculation.get("RESP")

        valid_trajectory = True
        if geometries is None or energies is None:
            # No valid geometry optimization found
            valid_trajectory = False
        elif len(geometries) != len(energies):
            # Ambiguous - no one-to-one mapping of molecule structure and energy
            valid_trajectory = False

        if not valid_trajectory:
            continue

        if isinstance(calculation["initial_molecule"], Molecule):
            init_mol = calculation["initial_molecule"]  # type: ignore
        else:
            init_mol = Molecule.from_dict(calculation["initial_molecule"])  # type: ignore

        if charge is None:
            charge = init_mol.charge  # type: ignore
        if species is None:
            species = init_mol.species  # type: ignore

        mols = [Molecule(species, g, charge=charge, spin_multiplicity=multiplicity) for g in geometries]  # type: ignore

        frame_props = {"electronic_energy": energies}
        num_steps = len(mols)

        site_props = dict()

        if total_gradients is not None and len(total_gradients) == num_steps:
            site_props["total_gradient"] = total_gradients
        if pcm_gradients is not None and len(pcm_gradients) == num_steps:
            site_props["pcm_gradient"] = pcm_gradients
        if cds_gradients is not None and len(cds_gradients) == num_steps:
            site_props["cds_gradient"] = cds_gradients

        if mulliken is not None:
            if len(mulliken) == num_steps:
                site_props["mulliken"] = mulliken
            elif len(mulliken) == num_steps + 1:
                last = np.asarray(mulliken[-1])
                seclast = np.asarray(mulliken[-2])
                if np.allclose(last, seclast):
                    site_props["mulliken"] = mulliken[:-1]

        if resp is not None:
            if len(resp) == num_steps:
                site_props["resp"] = resp
            elif len(resp) == num_steps + 1:
                last = np.asarray(resp[-1])
                seclast = np.asarray(resp[-2])
                if np.allclose(last, seclast):
                    site_props["resp"] = resp[:-1]

        traj_frame_props = list()
        traj_mols = list()
        for i in range(num_steps):
            step_dict = dict()

            for k, v in frame_props.items():
                step_dict[k] = v[i]  # type: ignore

            step_mol = mols[i]
            for k, v in site_props.items():
                step_mol.add_site_property(property_name=k, values=v[i])

            traj_mols.append(step_mol)

            traj_frame_props.append(step_dict)

        traj = Trajectory.from_molecules(
            traj_mols, frame_properties=traj_frame_props, time_step=None
        ).as_dict()
        trajectories.append(traj)

    if len(trajectories) == 0:
        raise HTTPException(
            status_code=404, detail="No geometry optimization data found for this task"
        )

    return trajectories
