from hashlib import blake2b

from pydantic import Field

from emmet.core.molecules import MolPropertyOrigin
from emmet.core.math import Vector3D
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class ElectricMultipoleDoc(PropertyDoc):
    """Electric multipole (dipole, etc.) properties of a molecule"""

    property_name: str = "multipole_moments"

    total_dipole: float = Field(
        ...,
        description="Total molecular dipole moment (Debye)",
    )

    dipole_moment: Vector3D = Field(
        ...,
        description="Molecular dipole moment vector (Debye)",
    )

    resp_total_dipole: float | None = Field(
        None,
        description="Total dipole moment, calculated via restrained electrostatic potential (RESP) (Debye)",
    )

    resp_dipole_moment: Vector3D | None = Field(
        None,
        description="Molecular dipole moment vector, calculated via RESP (Debye)",
    )

    quadrupole_moment: dict[str, float] | None = Field(
        None,
        description="Quadrupole moment components (Debye Ang)",
    )

    octopole_moment: dict[str, float] | None = Field(
        None,
        description="Octopole moment components (Debye Ang^2)",
    )

    hexadecapole_moment: dict[str, float] | None = Field(
        None,
        description="Hexadecapole moment tensor components (Debye Ang^2)",
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
        Construct an electric multipole doc
        """

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        task_type = task.task_type.value

        # For SP and force calcs, dipoles stored in output
        dipoles = task.output.dipoles
        if dipoles is None:
            if task_type in ["Single Point", "Force"]:
                raise Exception("No dipoles in task!")
            total_dipole = None
            dipole_moment = None
            resp_total_dipole = None
            resp_dipole_moment = None
        else:
            total_dipole = dipoles.get("total")
            dipole_moment = dipoles.get("dipole")
            resp_total_dipole = dipoles.get("RESP_total")
            resp_dipole_moment = dipoles.get("RESP_dipole")

        # Look for multipole moment in calcs_reversed
        calcs_reversed = task.calcs_reversed

        # FFOpt/FFTSOpt: grab final multipole moments from final optimization
        if task_type in [
            "Frequency Flattening Geometry Optimization",
            "Frequency Flattening Transition State Geometry Optimization",
        ]:
            calc = calcs_reversed[1]
            grab_index = -1
        # Frequency calc: grab first multipole moments
        # This is necessary if finite difference is used, in which case multipole moments will be generated for each
        # perturbation
        elif task_type == "Frequency Analysis":
            calc = calcs_reversed[0]
            grab_index = 0
        # Otherwise, grab final available multipole moments
        else:
            calc = calcs_reversed[0]
            grab_index = -1

        dipoles = calc.get("dipoles", dict())

        if total_dipole is None:
            total_dipole = dipoles.get("total")
            if isinstance(total_dipole, list):
                total_dipole = total_dipole[grab_index]
        if dipole_moment is None:
            dipole_moment = dipoles.get("dipole")
            if isinstance(dipole_moment, list) and len(dipole_moment) == 0:
                dipole_moment = None
            elif isinstance(dipole_moment[0], list):
                dipole_moment = dipole_moment[grab_index]
        if resp_total_dipole is None:
            resp_total_dipole = dipoles.get("RESP_total")
            if isinstance(resp_total_dipole, list):
                resp_total_dipole = resp_total_dipole[grab_index]
        if resp_dipole_moment is None:
            resp_dipole_moment = dipoles.get("RESP_dipole")
            if isinstance(resp_dipole_moment, list) and len(resp_dipole_moment) == 0:
                resp_dipole_moment = None
            elif isinstance(resp_dipole_moment[0], list):
                resp_dipole_moment = resp_dipole_moment[grab_index]

        if total_dipole is None or dipole_moment is None:
            raise Exception("Total dipole or dipole moment vector missing!")

        multipoles = calc.get("multipoles", dict())
        quadrupoles = multipoles.get("quadrupole")
        octopoles = multipoles.get("octopole")
        hexadecapoles = multipoles.get("hexadecapole")

        quadrupole_moment = None
        octopole_moment = None
        hexadecapole_moment = None

        if quadrupoles is not None:
            if isinstance(quadrupoles, dict):
                quadrupole_moment = quadrupoles
            else:
                quadrupole_moment = quadrupoles[grab_index]

        if octopoles is not None:
            if isinstance(octopoles, dict):
                octopole_moment = octopoles
            else:
                octopole_moment = octopoles[grab_index]

        if hexadecapoles is not None:
            if isinstance(hexadecapoles, dict):
                hexadecapole_moment = hexadecapoles
            else:
                hexadecapole_moment = hexadecapoles[grab_index]

        id_string = f"electricmultipole-{molecule_id}-{task.task_id}-{task.lot_solvent}"
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
            molecule=mol,
            total_dipole=total_dipole,
            dipole_moment=dipole_moment,
            resp_total_dipole=resp_total_dipole,
            resp_dipole_moment=resp_dipole_moment,
            quadrupole_moment=quadrupole_moment,
            octopole_moment=octopole_moment,
            hexadecapole_moment=hexadecapole_moment,
            warnings=list(),  # No warnings currently available
            origins=[MolPropertyOrigin(name="multipole_moments", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs,
        )
