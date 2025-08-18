from hashlib import blake2b

from pydantic import Field

from emmet.core.molecules import MolPropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPculeID
from emmet.core.qchem.calc_types import LevelOfTheory
from emmet.core.qchem.task import TaskDocument

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


def get_free_energy(energy, enthalpy, entropy, temperature=298.15, convert_energy=True):
    """
    Helper function to calculate Gibbs free energy from electronic energy, enthalpy, and entropy

    :param energy: Electronic energy in Ha
    :param enthalpy: Enthalpy in kcal/mol
    :param entropy: Entropy in csal/mol-K
    :param temperature: Temperature in K. Default is 298.15, 25C

    returns: Free energy in eV

    """

    if convert_energy:
        e = energy * 27.2114
    else:
        e = energy

    return e + enthalpy * 0.043363 - temperature * entropy * 0.000043363


class MoleculeThermoDoc(PropertyDoc):
    property_name: str = "thermo"

    electronic_energy: float = Field(
        ..., description="Electronic energy of the molecule (units: eV)"
    )

    correction: bool = Field(
        False,
        description="Was a single-point calculation at higher level of "
        "theory used to correct the electronic energy?",
    )

    base_level_of_theory: LevelOfTheory | None = Field(
        None, description="Level of theory used for uncorrected thermochemistry."
    )

    base_solvent: str | None = Field(
        None,
        description="String representation of the solvent "
        "environment used for uncorrected thermochemistry.",
    )

    base_lot_solvent: str | None = Field(
        None,
        description="String representation of the level of theory and solvent "
        "environment used for uncorrected thermochemistry.",
    )

    correction_level_of_theory: LevelOfTheory | None = Field(
        None, description="Level of theory used to correct the electronic energy."
    )

    correction_solvent: str | None = Field(
        None,
        description="String representation of the solvent "
        "environment used to correct the electronic energy.",
    )

    correction_lot_solvent: str | None = Field(
        None,
        description="String representation of the level of theory and solvent "
        "environment used to correct the electronic energy.",
    )

    combined_lot_solvent: str | None = Field(
        None,
        description="String representation of the level of theory and solvent "
        "environment used to generate this ThermoDoc, combining "
        "both the frequency calculation and (potentially) the "
        "single-point energy correction.",
    )

    zero_point_energy: float | None = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    rt: float | None = Field(
        None,
        description="R*T, where R is the gas constant and T is temperature, taken "
        "to be 298.15K (units: eV)",
    )

    total_enthalpy: float | None = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: float | None = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    translational_enthalpy: float | None = Field(
        None,
        description="Translational enthalpy of the molecule at 298.15K (units: eV)",
    )
    translational_entropy: float | None = Field(
        None,
        description="Translational entropy of the molecule at 298.15K (units: eV/K)",
    )
    rotational_enthalpy: float | None = Field(
        None, description="Rotational enthalpy of the molecule at 298.15K (units: eV)"
    )
    rotational_entropy: float | None = Field(
        None, description="Rotational entropy of the molecule at 298.15K (units: eV/K)"
    )
    vibrational_enthalpy: float | None = Field(
        None, description="Vibrational enthalpy of the molecule at 298.15K (units: eV)"
    )
    vibrational_entropy: float | None = Field(
        None, description="Vibrational entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: float | None = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        correction_task: TaskDocument | None = None,
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct a thermodynamics document from a task

        :param task: document from which thermodynamic properties can be extracted
        :param molecule_id: MPculeID
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        if correction_task is None:
            energy = task.output.final_energy
            correction = False
            correction_lot = None
            correction_solvent = None
            correction_lot_solvent = None
            level_of_theory = task.level_of_theory
            solvent = task.solvent
            lot_solvent = task.lot_solvent
            combined_lot_solvent = task.lot_solvent
        else:
            energy = correction_task.output.final_energy
            correction = True
            correction_lot = correction_task.level_of_theory
            correction_solvent = correction_task.solvent
            correction_lot_solvent = correction_task.lot_solvent
            combined_lot_solvent = f"{task.lot_solvent}//{correction_lot_solvent}"
            level_of_theory = correction_lot
            solvent = correction_solvent
            lot_solvent = combined_lot_solvent

        total_enthalpy = task.output.enthalpy
        total_entropy = task.output.entropy

        origins = [MolPropertyOrigin(name="thermo", task_id=task.task_id)]
        id_string = f"thermo-{molecule_id}-{task.task_id}-{task.lot_solvent}"
        if correction and correction_task is not None:
            origins.append(
                MolPropertyOrigin(
                    name="thermo_energy_correction", task_id=correction_task.task_id
                )
            )

            id_string += f"-{correction_task.task_id}-{correction_task.lot_solvent}"

        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        if total_enthalpy is not None and total_entropy is not None:
            free_energy = get_free_energy(energy, total_enthalpy, total_entropy)

            for calc in task.calcs_reversed:
                if all(
                    [
                        calc.get(x) is not None
                        for x in [
                            "ZPE",
                            "trans_enthalpy",
                            "rot_enthalpy",
                            "vib_enthalpy",
                            "gas_constant",
                            "trans_entropy",
                            "rot_entropy",
                            "vib_entropy",
                        ]
                    ]
                ):
                    return super().from_molecule(
                        meta_molecule=mol,
                        property_id=property_id,
                        molecule_id=molecule_id,
                        level_of_theory=level_of_theory,
                        solvent=solvent,
                        lot_solvent=lot_solvent,
                        correction=correction,
                        base_level_of_theory=task.level_of_theory,
                        base_solvent=task.solvent,
                        base_lot_solvent=task.lot_solvent,
                        correction_level_of_theory=correction_lot,
                        correction_solvent=correction_solvent,
                        correction_lot_solvent=correction_lot_solvent,
                        combined_lot_solvent=combined_lot_solvent,
                        electronic_energy=energy * 27.2114,
                        zero_point_energy=calc["ZPE"] * 0.043363,
                        rt=calc["gas_constant"] * 0.043363,
                        total_enthalpy=total_enthalpy * 0.043363,
                        translational_enthalpy=calc["trans_enthalpy"] * 0.043363,
                        rotational_enthalpy=calc["rot_enthalpy"] * 0.043363,
                        vibrational_enthalpy=calc["vib_enthalpy"] * 0.043363,
                        total_entropy=total_entropy * 0.000043363,
                        translational_entropy=calc["trans_entropy"] * 0.000043363,
                        rotational_entropy=calc["rot_entropy"] * 0.000043363,
                        vibrational_entropy=calc["vib_entropy"] * 0.000043363,
                        free_energy=free_energy,
                        deprecated=deprecated,
                        origins=origins,
                        **kwargs,
                    )

        # If all thermodynamic data is not available
        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            correction=correction,
            correction_level_of_theory=correction_lot,
            correction_solvent=correction_solvent,
            correction_lot_solvent=correction_lot_solvent,
            combined_lot_solvent=combined_lot_solvent,
            electronic_energy=energy * 27.2114,
            deprecated=deprecated,
            origins=origins,
            **kwargs,
        )
