import numpy as np
from fastapi import HTTPException
from pymatgen.core import Molecule
from pymatgen.core.trajectory import Trajectory


def calcs_reversed_to_trajectory(calcs_reversed: list[dict]):
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
        dipoles = calculation.get("dipoles")
        multipoles = calculation.get("multipoles")

        valid_trajectory = True
        if geometries is None or energies is None:
            # No valid geometry optimization found
            print("NO GEOM OR NO ENERGIES!")
            valid_trajectory = False
        elif len(geometries) != len(energies):
            # Ambiguous - no one-to-one mapping of molecule structure and energy
            print("GEOMS NOT EQUAL ENERGIES")
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

        # Frame (molecule) properties
        frame_props = {"electronic_energy": energies}
        num_steps = len(mols)

        # electric dipoles
        if dipoles is not None:
            if (
                isinstance(dipoles.get("total"), list)
                and len(dipoles["total"]) == num_steps
            ):
                frame_props["total_dipole"] = dipoles["total"]
            if (
                isinstance(dipoles.get("RESP_total"), list)
                and len(dipoles["RESP_total"]) == num_steps
            ):
                frame_props["resp_total_dipole"] = dipoles["RESP_total"]
            if dipoles.get("dipole") is not None and len(dipoles["dipole"]) > 0:
                if (
                    isinstance(dipoles["dipole"][0], list)
                    and len(dipoles["dipole"]) == num_steps
                ):
                    frame_props["dipole_moment"] = dipoles["dipole"]
            if (
                dipoles.get("RESP_dipole") is not None
                and len(dipoles["RESP_dipole"]) > 0
            ):
                if (
                    isinstance(dipoles["RESP_dipole"][0], list)
                    and len(dipoles["RESP_dipole"]) == num_steps
                ):
                    frame_props["resp_dipole_moment"] = dipoles["RESP_dipole"]

        # electric multipoles
        if multipoles is not None:
            if (
                isinstance(multipoles.get("quadrupole"), list)
                and len(multipoles["quadrupole"]) == num_steps
            ):
                frame_props["quadrupole_moment"] = multipoles["quadrupole"]
            if (
                isinstance(multipoles.get("octopole"), list)
                and len(multipoles["octopole"]) == num_steps
            ):
                frame_props["octopole_moment"] = multipoles["octopole"]
            if (
                isinstance(multipoles.get("hexadecapole"), list)
                and len(multipoles["hexadecapole"]) == num_steps
            ):
                frame_props["hexadecapole_moment"] = multipoles["hexadecapole"]

        # Site (atomic) properties
        site_props = dict()

        # Gradients
        if total_gradients is not None and len(total_gradients) == num_steps:
            site_props["total_gradient"] = total_gradients
        if pcm_gradients is not None and len(pcm_gradients) == num_steps:
            site_props["pcm_gradient"] = pcm_gradients
        if cds_gradients is not None and len(cds_gradients) == num_steps:
            site_props["cds_gradient"] = cds_gradients

        # Partial charges/spins
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

        # Convert into a Trajectory object
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
