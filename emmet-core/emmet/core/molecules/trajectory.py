from hashlib import blake2b

import numpy as np
from pydantic import Field
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Molecule
from pymatgen.core.trajectory import Trajectory

from emmet.core.molecules import MolPropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class ForcesDoc(PropertyDoc):
    property_name: str = "forces"

    forces: list[list[float]] = Field(..., description="Atomic forces (units: Ha/Bohr)")

    precise_forces: list[list[float] | None] = Field(
        default_factory=list,
        description="High-precision atomic forces (units: Ha/Bohr)",
    )

    pcm_forces: list[list[float]] | None = Field(
        None,
        description="Electrostatic atomic forces from polarizable continuum model (PCM) implicit solvation "
        "(units: Ha/Bohr).",
    )

    cds_forces: list[list[float]] | None = Field(
        None,
        description="Atomic force contributions from cavitation, dispersion, and structural rearrangement in the SMx "
        "family of implicit solvent models (units: Ha/Bohr)",
    )

    average_force_magnitude: float | None = Field(
        None, description="Average magnitude of atomic forces (units: Ha/Bohr)"
    )

    max_force_magnitude: float | None = Field(
        None,
        description="Maximum magnitude of atomic forces (units: Ha/Bohr)",
    )

    min_force_magnitude: float | None = Field(
        None,
        description="Minimum magnitude of atomic forces (units: Ha/Bohr)",
    )

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct a force document from a task document

        :param task: document from which force properties can be extracted
        :param molecule_id: MPculeID
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.task_type.value != "Force":
            raise ValueError(
                "ForcesDoc can only be constructed from force calculations,"
                f"not {task.task_type.value}!"
            )

        mol = task.output.initial_molecule

        forces = task.output.gradients
        precise_forces = task.output.precise_gradients
        pcm_forces = task.output.pcm_gradients
        cds_forces = task.output.CDS_gradients

        calc = task.calcs_reversed[0]

        # Precise forces are either in output or don't exist
        # For PCM and CDS forces, can check "calcs_reversed"
        if pcm_forces is None:
            pcm_forces = calc.get("pcm_gradients")

        if cds_forces is None:
            cds_forces = calc.get("CDS_gradients")

        # Basic stats
        if precise_forces is not None:
            magnitudes = [np.linalg.norm(np.asarray(f)) for f in precise_forces]
        else:
            magnitudes = [np.linalg.norm(np.asarray(f)) for f in forces]

        average_force_magnitude = np.mean(magnitudes)
        max_force_magnitude = max(magnitudes)  # type: ignore[type-var]
        min_force_magnitude = min(magnitudes)  # type: ignore[type-var]

        id_string = f"forces-{molecule_id}-{task.task_id}-{task.lot_solvent}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            forces=forces,
            precise_forces=precise_forces,
            pcm_forces=pcm_forces,
            cds_forces=cds_forces,
            average_force_magnitude=average_force_magnitude,
            max_force_magnitude=max_force_magnitude,
            min_force_magnitude=min_force_magnitude,
            origins=[MolPropertyOrigin(name="forces", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs,
        )


class TrajectoryDoc(PropertyDoc):
    property_name: str = "optimization_trajectory"

    num_trajectories: int = Field(
        ...,
        description="Number of separate optimization trajectories extracted from this task",
    )

    species: list[Element | str] = Field(
        ...,
        description="Element or element name for each atom in the molecule for each optimization step",
    )

    geometries: list[list[list[list[float]]]] = Field(
        ...,
        description="XYZ positions of each atom in the molecule for each optimization step for each optimization "
        "trajectory (units: Angstrom)",
    )

    energies: list[list[float]] = Field(
        ...,
        description="Electronic energies for each optimization step for each optimization trajectory (units: Hartree)",
    )

    forces: list[list[list[list[float]]]] = Field(
        ...,
        description="Forces on each atom for each optimization step for each optimization trajectory (units: Ha/Bohr)",
    )

    pcm_forces: list[list[list[list[float]]] | None] = Field(
        default_factory=list,
        description="Electrostatic atomic forces from polarizable continuum model (PCM) implicit solvation "
        "for each optimization step for each optimization trajectory (units: Ha/Bohr).",
    )

    cds_forces: list[list[list[list[float]]] | None] = Field(
        default_factory=list,
        description="Atomic force contributions from cavitation, dispersion, and structural rearrangement in the SMx "
        "family of implicit solvent models, for each optimization step for each optimization trajectory "
        "(units: Ha/Bohr)",
    )

    mulliken_partial_charges: list[list[list[float]] | None] = Field(
        default_factory=list,
        description="Partial charges of each atom for each optimization step for each optimization trajectory, using "
        "the Mulliken method",
    )

    mulliken_partial_spins: list[list[list[float]] | None] = Field(
        default_factory=list,
        description="Partial spins of each atom for each optimization step for each optimization trajectory, using "
        "the Mulliken method",
    )

    resp_partial_charges: list[list[list[float]] | None] = Field(
        default_factory=list,
        description="Partial charges of each atom for each optimization step for each optimization trajectory, using "
        "the restrained electrostatic potential (RESP) method",
    )

    dipole_moments: list[list[list[float]] | None] = Field(
        default_factory=list,
        description="Molecular dipole moment for each optimization step for each optimization trajectory, "
        "(units: Debye)",
    )

    resp_dipole_moments: list[list[list[float]] | None] = Field(
        default_factory=list,
        description="Molecular dipole moment for each optimization step for each optimization trajectory, "
        "using the restrainted electrostatic potential (RESP) method (units: Debye)",
    )

    @property
    def molecules(self) -> list[list[Molecule]]:
        """
        Geometries along the optimization trajectory, represented as pymatgen Molecule objects.

        Args:
            self

        Returns:
            list[Molecule]: the optimization trajectory as a list of Molecules

        """

        return [
            [
                Molecule(
                    self.species,
                    geom,
                    charge=self.charge,
                    spin_multiplicity=self.spin_multiplicity,
                )
                for geom in trajectory
            ]
            for trajectory in self.geometries
        ]

    def as_trajectories(self) -> list[Trajectory]:
        """
        Represent this TrajectoryDoc as a list of pymatgen Trajectory objects.

        Args:
            self

        Returns:
            trajectories (list[Trajectory]): TrajectoryDoc represented as a collection of pymatgen Trajectory objects

        """

        trajectories = list()

        mol_trajectories = self.molecules

        for ii, mols in enumerate(mol_trajectories):
            num_steps = len(mols)

            # Frame (structure) properties
            frame_props = {"energies": self.energies[ii]}
            for prop in (
                "dipole_moments",
                "resp_dipole_moments",
            ):
                frame_props[prop] = []
                if (vals := getattr(self, prop, None)) is not None:
                    frame_props[prop] = vals[ii]

            # Site (atomic) properties
            site_props = {"forces": self.forces[ii]}
            for prop in (
                "pcm_forces",
                "cds_forces",
                "mulliken_partial_charges",
                "mulliken_partial_spins",
                "resp_partial_charges",
            ):
                site_props[prop] = []
                if (vals := getattr(self, prop, None)) is not None:
                    site_props[prop] = vals[ii]

            # Convert into a Trajectory object
            traj_frame_props = list()
            traj_mols = list()
            for jj in range(num_steps):
                step_dict = dict()

                for k, v in frame_props.items():
                    if v is not None:
                        step_dict[k] = v[jj]  # type: ignore

                step_mol = mols[jj]
                for k, v in site_props.items():  # type: ignore
                    if v is not None:
                        step_mol.add_site_property(property_name=k, values=v[jj])  # type: ignore[arg-type]

                traj_mols.append(step_mol)

                traj_frame_props.append(step_dict)

            traj = Trajectory.from_molecules(
                traj_mols, frame_properties=traj_frame_props, time_step=None
            )  # type: ignore[arg-type]
            trajectories.append(traj)

        return trajectories

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct a trajectory document from a task document

        :param task: document from which force properties can be extracted
        :param molecule_id: MPculeID
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.task_type.value not in [
            "Geometry Optimization",
            "Frequency Flattening Geometry Optimization",
            "Transition State Geometry Optimization",
            "Frequency Flattening Transition State Geometry Optimization",
        ]:
            raise ValueError(
                "TrajectoryDoc can only be constructed from geometry optimization calculations,"
                f"not {task.task_type.value}!"
            )

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        multiplicity = mol.spin_multiplicity

        species = None
        geometries = list()  # type: ignore
        energies = list()
        total_gradients = list()
        pcm_gradients = list()
        cds_gradients = list()
        mulliken_partial_charges = list()
        mulliken_partial_spins = list()
        resp_partial_charges = list()
        dipole_moments = list()
        resp_dipole_moments = list()

        for calculation in task.calcs_reversed:
            species = calculation.get("species", species)

            this_geometries = calculation.get("geometries")
            this_energies = calculation.get("energy_trajectory")
            this_total_gradients = calculation.get("gradients")
            this_pcm_gradients = calculation.get("pcm_gradients")
            this_cds_gradients = calculation.get("CDS_gradients")

            this_mulliken = calculation.get("Mulliken")
            this_resp = calculation.get("RESP")
            this_dipoles = calculation.get("dipoles")

            valid_trajectory = True
            if this_geometries is None or this_energies is None:
                # No valid geometry optimization found
                valid_trajectory = False
            elif len(this_energies) != len(this_total_gradients):
                # Energies and forces cannot be trivially mapped
                valid_trajectory = False
            elif len(this_geometries) != len(this_energies):
                # Initial geometry not included - common because of how parsing is done
                if len(this_geometries) == len(this_energies) - 1:
                    this_geometries = [
                        calculation["initial_geometry"]
                    ] + this_geometries
                # Other issue - no one-to-one mapping of molecule structure and energy
                else:
                    valid_trajectory = False

            if not valid_trajectory:
                continue

            if isinstance(calculation["initial_molecule"], Molecule):
                init_mol = calculation["initial_molecule"]  # type: ignore
            else:
                init_mol = Molecule.from_dict(calculation["initial_molecule"])  # type: ignore

            if species is None:
                species = init_mol.species  # type: ignore

            # Number of steps
            # All data in this (sub)-trajectory must have the same length
            num_steps = len(geometries)

            this_dipole_moments = None
            this_resp_dipole_moments = None

            # electric dipoles
            if this_dipoles is not None:
                if (
                    this_dipoles.get("dipole") is not None
                    and len(this_dipoles["dipole"]) > 0
                ):
                    if (
                        isinstance(this_dipoles["dipole"][0], list)
                        and len(this_dipoles["dipole"]) == num_steps
                    ):
                        this_dipole_moments = this_dipoles["dipole"]
                if (
                    this_dipoles.get("RESP_dipole") is not None
                    and len(this_dipoles["RESP_dipole"]) > 0
                ):
                    if (
                        isinstance(this_dipoles["RESP_dipole"][0], list)
                        and len(this_dipoles["RESP_dipole"]) == num_steps
                    ):
                        this_resp_dipole_moments = this_dipoles["RESP_dipole"]

            this_mulliken_partial_charges = None
            this_mulliken_partial_spins = None
            this_resp_partial_charges = None

            # Partial charges/spins
            if this_mulliken is not None:
                if len(this_mulliken) == num_steps:
                    if int(multiplicity) == 1:
                        this_mulliken_partial_charges = this_mulliken
                    else:
                        # For open-shell molecules, need to split mulliken charges and spins
                        charges = list()
                        spins = list()

                        for step in this_mulliken:
                            step_charges = list()
                            step_spins = list()
                            for atom in step:
                                step_charges.append(atom[0])
                                step_spins.append(atom[1])
                            charges.append(step_charges)
                            spins.append(step_spins)

                        this_mulliken_partial_charges = charges
                        this_mulliken_partial_spins = spins
                elif len(this_mulliken) == num_steps + 1:
                    last = np.asarray(this_mulliken[-1])
                    seclast = np.asarray(this_mulliken[-2])
                    if np.allclose(last, seclast):
                        if int(multiplicity) == 1:
                            this_mulliken_partial_charges = this_mulliken[:-1]

                        else:
                            charges = list()
                            spins = list()

                            for step in this_mulliken[::-1]:
                                step_charges = list()
                                step_spins = list()
                                for atom in step:
                                    step_charges.append(atom[0])
                                    step_spins.append(atom[1])
                                charges.append(step_charges)
                                spins.append(step_spins)

                            this_mulliken_partial_charges = charges
                            this_mulliken_partial_spins = spins

            if this_resp is not None:
                if len(this_resp) == num_steps:
                    this_resp_partial_charges = this_resp
                elif len(this_resp) == num_steps + 1:
                    last = np.asarray(this_resp[-1])
                    seclast = np.asarray(this_resp[-2])
                    if np.allclose(last, seclast):
                        this_resp_partial_charges = this_resp[:-1]

            geometries.append(this_geometries)
            energies.append(this_energies)
            total_gradients.append(this_total_gradients)
            pcm_gradients.append(this_pcm_gradients)
            cds_gradients.append(this_cds_gradients)
            mulliken_partial_charges.append(this_mulliken_partial_charges)
            mulliken_partial_spins.append(this_mulliken_partial_spins)
            resp_partial_charges.append(this_resp_partial_charges)
            dipole_moments.append(this_dipole_moments)
            resp_dipole_moments.append(this_resp_dipole_moments)

        num_trajectories = len(geometries)

        id_string = f"trajectory-{molecule_id}-{task.task_id}-{task.lot_solvent}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            num_trajectories=num_trajectories,
            species=species,
            geometries=geometries,
            energies=energies,
            forces=total_gradients,
            pcm_forces=pcm_gradients,
            cds_forces=cds_gradients,
            mulliken_partial_charges=mulliken_partial_charges,
            mulliken_partial_spins=mulliken_partial_spins,
            resp_partial_charges=resp_partial_charges,
            dipole_moments=dipole_moments,
            resp_dipole_moments=resp_dipole_moments,
            origins=[MolPropertyOrigin(name="trajectory", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs,
        )
