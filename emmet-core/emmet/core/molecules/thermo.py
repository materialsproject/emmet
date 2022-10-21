from pydantic import Field

from emmet.core.mpid import MPID
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


def get_free_energy(energy, enthalpy, entropy, temperature=298.15):
    """
    Helper function to calculate Gibbs free energy from electronic energy, enthalpy, and entropy

    :param energy: Electronic energy in Ha
    :param enthalpy: Enthalpy in kcal/mol
    :param entropy: Entropy in cal/mol-K
    :param temperature: Temperature in K. Default is 298.15, 25C

    returns: Free energy in eV

    """
    return energy * 27.2114 + enthalpy * 0.043363 - temperature * entropy * 0.000043363


class ThermoDoc(PropertyDoc):

    property_name = "thermo"

    task_id: MPID = Field(..., description="ID of TaskDocument from which these properties were derived")

    electronic_energy: float = Field(..., description="Electronic energy of the molecule (units: eV)")

    zero_point_energy: float = Field(None, description="Zero-point energy of the molecule (units: eV)")

    rt: float = Field(
        None, description="R*T, where R is the gas constant and T is temperature, taken " "to be 298.15K (units: eV)",
    )

    total_enthalpy: float = Field(None, description="Total enthalpy of the molecule at 298.15K (units: eV)")
    total_entropy: float = Field(None, description="Total entropy of the molecule at 298.15K (units: eV/K)")

    translational_enthalpy: float = Field(
        None, description="Translational enthalpy of the molecule at 298.15K (units: eV)",
    )
    translational_entropy: float = Field(
        None, description="Translational entropy of the molecule at 298.15K (units: eV/K)",
    )
    rotational_enthalpy: float = Field(None, description="Rotational enthalpy of the molecule at 298.15K (units: eV)")
    rotational_entropy: float = Field(None, description="Rotational entropy of the molecule at 298.15K (units: eV/K)")
    vibrational_enthalpy: float = Field(None, description="Vibrational enthalpy of the molecule at 298.15K (units: eV)")
    vibrational_entropy: float = Field(None, description="Vibrational entropy of the molecule at 298.15K (units: eV/K)")

    free_energy: float = Field(None, description="Gibbs free energy of the molecule at 298.15K (units: eV)")

    @classmethod
    def from_task(
        cls, task: TaskDocument, molecule_id: MPID, deprecated: bool = False, **kwargs
    ):  # type: ignore[override]

        """
        Construct a thermodynamics document from a task

        :param task: document from which thermodynamic properties can be extracted
        :param molecule_id: mpid
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        energy = task.output.final_energy
        total_enthalpy = task.output.enthalpy
        total_entropy = task.output.entropy

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
                        molecule_id=molecule_id,
                        task_id=task.task_id,
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
                        origins=[PropertyOrigin(name="thermo", task_id=task.task_id)],
                        free_energy=free_energy,
                        deprecated=deprecated,
                        **kwargs
                    )

        # If all thermodynamic data is not available
        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            task_id=task.task_id,
            electronic_energy=energy * 27.2114,
            deprecated=deprecated,
            **kwargs
        )
