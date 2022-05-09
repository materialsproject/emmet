from typing import List

from pydantic import Field

from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.material import PropertyOrigin
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class VibrationDoc(PropertyDoc):

    property_name = "vibrations"

    molecule: Molecule = Field(..., description="Molecular structure")

    frequencies: List[float] = Field(
        ..., description="List of molecular vibrational frequencies"
    )

    frequency_modes: List[List[List[float]]] = Field(
        ..., description="Vibrational frequency modes of the molecule"
    )

    ir_intensities: List[float] = Field(
        ...,
        title="IR intensities",
        description="Intensities for IR vibrational spectrum peaks",
    )

    ir_activities: List = Field(
        ...,
        title="IR activities",
        description="List indicating if frequency-modes are IR-active",
    )

    @classmethod
    def from_task(
        cls, task: TaskDocument, molecule_id: MPID, deprecated: bool = False, **kwargs
    ):  # type: ignore[override]
        """
        Construct a vibration document from a task document

        :param task: document from which vibrational properties can be extracted
        :param molecule_id: mpid
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
        intensities = None
        active = None
        for calc in task.calcs_reversed:
            if (
                calc.get("frequency_mode_vectors", None) is not None
                and frequency_modes is None
            ):
                frequency_modes = calc.get("frequency_mode_vectors")

            if calc.get("IR_intens", None) is not None and intensities is None:
                intensities = calc.get("IR_intens")

            if calc.get("IR_active", None) is not None and active is None:
                active = calc.get("IR_active")

            if all([x is not None for x in [frequency_modes, intensities, active]]):
                break

        if frequency_modes is None:
            raise Exception("No frequency modes in task!")
        elif intensities is None:
            raise Exception("No IR intensities in task!")
        elif active is None:
            raise Exception("No IR activities in task!")

        warnings = list()
        if frequencies[0] < 0.0:
            warnings.append("Imaginary frequencies")

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            molecule=mol,
            frequencies=frequencies,
            frequency_modes=frequency_modes,
            ir_intensities=intensities,
            ir_activities=active,
            origins=[PropertyOrigin(name="vibrations", task_id=task.task_id)],
            deprecated=deprecated,
            warnings=warnings,
            **kwargs
        )
