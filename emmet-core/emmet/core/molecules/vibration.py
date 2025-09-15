from hashlib import blake2b

from pydantic import Field

from emmet.core.molecules import MolPropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument
from emmet.core.types.pymatgen_types.structure_adapter import MoleculeType

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class VibrationDoc(PropertyDoc):
    property_name: str = "vibrations"

    molecule: MoleculeType = Field(..., description="Molecular structure")

    frequencies: list[float] = Field(
        ..., description="List of molecular vibrational frequencies"
    )

    frequency_modes: list[list[list[float]]] = Field(
        ..., description="Vibrational frequency modes of the molecule"
    )

    ir_intensities: list[float] = Field(
        ...,
        title="IR intensities",
        description="Intensities for IR vibrational spectrum peaks",
    )

    ir_activities: list[bool] = Field(
        ...,
        title="IR activities",
        description="List indicating if frequency-modes are IR-active",
    )

    raman_intensities: list[float] | None = Field(
        None,
        title="Raman intensities",
        description="Intensities for Raman spectrum peaks",
    )

    raman_activities: list[float] | None = Field(
        None,
        title="Raman activities",
        description="List indicating if frequency-modes are Raman-active",
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
        Construct a vibration document from a task document

        :param task: document from which vibrational properties can be extracted
        :param molecule_id: MPculeID
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.frequencies is None:
            raise Exception("No frequencies in task!")

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        frequencies = task.output.frequencies
        frequency_modes = None
        ir_intensities = None
        ir_active = None
        raman_intensities = None
        raman_active = None
        for calc in task.calcs_reversed:
            frequency_modes = calc.get("frequency_mode_vectors")
            ir_intensities = calc.get("IR_intens")
            ir_active = calc.get("IR_active")
            raman_intensities = calc.get("raman_intens")
            raman_active = calc.get("raman_active")

            # IR intensities and activities required
            # Raman intensitives/activities are optional
            if all(
                [x is not None for x in [frequency_modes, ir_intensities, ir_active]]
            ):
                break

        if frequency_modes is None:
            raise Exception("No frequency modes in task!")
        elif ir_intensities is None:
            raise Exception("No IR intensities in task!")
        elif ir_active is None:
            raise Exception("No IR activities in task!")

        ir_active = [True if ira.upper() == "YES" else False for ira in ir_active]
        if raman_active is not None:
            raman_active = [
                True if ra.upper() == "YES" else False for ra in raman_active
            ]

        warnings = list()
        if frequencies[0] < 0.0:
            warnings.append("Imaginary frequencies")

        id_string = f"vibrations-{molecule_id}-{task.task_id}-{task.lot_solvent}"
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
            frequencies=frequencies,
            frequency_modes=frequency_modes,
            ir_intensities=ir_intensities,
            ir_activities=ir_active,
            raman_intensities=raman_intensities,
            raman_activities=raman_active,
            warnings=warnings,
            origins=[MolPropertyOrigin(name="vibrations", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs,
        )
